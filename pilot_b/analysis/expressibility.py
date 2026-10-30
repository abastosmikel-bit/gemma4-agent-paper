"""Steps 3+4: which gold patches are expressible as symbol edits, and does the skill replay them?

For every task: apply the gold patch in a checkout to get old/new file pairs. Diff each modified
.py file line by line; attribute each changed region to the innermost symbol (def / async def /
class, nested included) that contains it on BOTH sides, otherwise to module level. Then build a
replay plan (edit_symbol on outermost touched symbols, insert_symbol for new top-level
definitions), execute it with the skill's own code on a clean checkout, and compare the result
with the gold post-patch file (exact text, then AST equality).

Writes aggregate results to results/expressibility.json and per-task categories (ids + labels,
no code) to results/expressibility_tasks.jsonl.

usage: python -m pilot_b.analysis.expressibility [--tests]   (--tests: also run FAIL tests on replay)
"""
from __future__ import annotations

import ast
import collections
import difflib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pilot_b", "skill", "graph-edit", "scripts"))
import _symlib as sl  # noqa: E402
from common.patches import file_diffs  # noqa: E402
from common.tasks import checkout, load_graph, load_tasks, reset_checkout, short_repo  # noqa: E402
from common.graphnames import graph_names  # noqa: E402

DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def syms_of(src: str, rel: str):
    """List of (qname, kind, start, end, node) with start including decorators (1-based)."""
    try:
        return [(s.qname, s.kind, s.start, s.end, s.node) for s in sl.index_file("", rel, src)]
    except SyntaxError:
        return None


def import_lines(src: str) -> set[int]:
    out = set()
    for n in ast.parse(src).body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            out.update(range(n.lineno, n.end_lineno + 1))
        elif isinstance(n, ast.If) and "TYPE_CHECKING" in ast.unparse(n.test):
            for m in n.body:
                if isinstance(m, (ast.Import, ast.ImportFrom)):
                    out.update(range(m.lineno, m.end_lineno + 1))
    return out


def blank_or_comment(lines) -> bool:
    return all((not ln.strip()) or ln.strip().startswith("#") for ln in lines)


def ranked(syms):
    """[(key=(qname, rank among same-named), kind, start, end, node)] in file order."""
    seen = collections.Counter()
    out = []
    for q, k, s, e, n in syms:
        out.append(((q, seen[q]), k, s, e, n))
        seen[q] += 1
    return out


def classify_file(old: str, new: str, rel: str, graph_def_names: set[str] | None):
    """Return (list of op dicts, replay plan) for one modified file."""
    osy, nsy = syms_of(old, rel), syms_of(new, rel)
    if osy is None or nsy is None:
        return [{"cat": "unparseable"}], None
    osy, nsy = ranked(osy), ranked(nsy)
    ol, nl = old.split("\n"), new.split("\n")
    nmap = {key: (k, s, e, n) for key, k, s, e, n in nsy}
    old_keys = {key for key, *_ in osy}
    new_only = [x for x in nsy if x[0] not in old_keys]
    new_only_lines = set()
    for key, k, s, e, n in new_only:
        new_only_lines.update(range(s, e + 1))
    imp_old, imp_new = import_lines(old), import_lines(new)
    ops, touched = [], {}
    sm = difflib.SequenceMatcher(None, ol, nl, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        # innermost symbol containing the change on both sides (1-based inclusive spans)
        best = None
        for key, k, s, e, n in osy:
            if key not in nmap:
                continue
            ns, ne = nmap[key][1], nmap[key][2]
            old_in = (s - 1 <= i1 and i2 <= e) if i2 > i1 else (s - 1 < i1 <= e)
            new_in = (ns - 1 <= j1 and j2 <= ne) if j2 > j1 else (ns - 1 < j1 <= ne)
            if old_in and new_in and (best is None or (e - s) < (best[3] - best[2])):
                best = (key, k, s, e, n)
        old_chunk, new_chunk = ol[i1:i2], nl[j1:j2]
        if best is not None:
            key, k, s, e, n = best
            if k == "class":
                # change in the class body outside any method
                nonblank_new = {j for j in range(j1 + 1, j2 + 1) if nl[j - 1].strip()}
                if i2 == i1 and nonblank_new and nonblank_new <= new_only_lines:
                    cat = "class.new_method"
                elif blank_or_comment(old_chunk) and blank_or_comment(new_chunk):
                    cat = "class.blank_comment"
                else:
                    cat = "class.body_stmt"     # attributes, decorators, bases, docstring
            else:
                cat = "async_def" if k == "async def" else "def"
                if k == "def" and graph_def_names is not None and key[0] not in graph_def_names:
                    cat = "def.not_graph_node"   # nested / renamed / collapsed in the graph
            ops.append({"cat": cat, "sym": key[0]})
            touched[key] = (s, e)
            continue
        # module level
        nonblank_new = {j for j in range(j1 + 1, j2 + 1) if nl[j - 1].strip()}
        nonblank_old = {i for i in range(i1 + 1, i2 + 1) if ol[i - 1].strip()}
        if blank_or_comment(old_chunk) and blank_or_comment(new_chunk):
            cat = "module.blank_comment"
        elif not nonblank_old and nonblank_new and nonblank_new <= new_only_lines:
            cat = "module.new_symbol"
        elif (nonblank_old <= imp_old) and (nonblank_new <= imp_new):
            cat = "module.imports"
        elif nonblank_new and nonblank_new <= new_only_lines | imp_new and not (nonblank_old - imp_old):
            cat = "module.new_symbol+imports"
        else:
            cat = "module.statement"
        ops.append({"cat": cat})
    # replay plan: outermost touched symbols, + inserts for new definitions not inside a replaced one
    spans = {key: touched[key] for key in touched}
    outer = [key for key in touched
             if not any(o != key and spans[o][0] <= spans[key][0] and spans[key][1] <= spans[o][1] for o in touched)]
    plan = [("edit", key) for key in sorted(outer, key=lambda x: -spans[x][0])]   # bottom-up
    replaced_new = [(nmap[key][1], nmap[key][2]) for key in outer]
    new_spans = [(s, e) for _, _, s, e, _ in new_only]
    for key, k, s, e, n in new_only:
        if any(a <= s and e <= b for a, b in replaced_new):
            continue        # comes in with a replaced parent
        if any((a, b) != (s, e) and a <= s and e <= b for a, b in new_spans):
            continue        # nested in another new symbol
        plan.append(("insert", key))
    return ops, plan


def execute_plan(root, rel, new, plan):
    """Apply plan with the skill library; return (status, n_calls, payload_lines)."""
    nsy = {key: (k, s, e) for key, k, s, e, _ in ranked(syms_of(new, rel))}
    nl = new.split("\n")
    calls, payload = 0, 0
    present = {key[0] for key in nsy} - {key[0] for op, key in plan if op == "insert"}
    for op, key in plan:
        q = key[0]
        k, s, e = nsy[key]
        src = "\n".join(nl[s - 1:e])
        payload += e - s + 1
        calls += 1
        if op == "edit":
            sym = f"{rel}:{_local(rel, q)}"
            r = _call(sl.edit_symbol, root, symbol=sym, new_source=src, allow_rename="false")
            if r.get("error_type") == "AmbiguousSymbol":     # same-named defs: address by line, as a model would
                cur = [x for x in sl.index_file(root, rel) if x.qname == q]
                line = cur[min(key[1], len(cur) - 1)].node.lineno
                r = _call(sl.edit_symbol, root, symbol=f"{sym}@{line}", new_source=src, allow_rename="false")
        else:
            prev, nxt = _neighbours(new, rel, q, present)
            present.add(q)
            if prev:
                r = _call(sl.insert_symbol, root, new_source=src, after=f"{rel}:{prev}")
            elif nxt:
                r = _call(sl.insert_symbol, root, new_source=src, before=f"{rel}:{nxt}")
            else:
                parent = q.rsplit(".", 1)[0]
                into = rel if parent == sl.module_name(rel) else f"{rel}:{_local(rel, parent)}"
                r = _call(sl.insert_symbol, root, new_source=src, into=into)
        if r.get("status") != "ok":
            return f"tool_error:{r.get('error_type')}", calls, payload
    return "ok", calls, payload


def _local(rel, q):
    mod = sl.module_name(rel)
    return q[len(mod) + 1:] if mod and q.startswith(mod + ".") else q


def _neighbours(new, rel, q, present):
    """(previous, next) sibling definitions of q in the new file that already exist (local names)."""
    tree = ast.parse(new)
    parent_q = q.rsplit(".", 1)[0]
    mod = sl.module_name(rel)
    body = tree.body
    if parent_q != mod:
        for s in sl.index_file("", rel, new):
            if s.qname == parent_q:
                body = s.node.body
                break
    names = [n.name for n in body if isinstance(n, DEF_TYPES)]
    i = names.index(q.rsplit(".", 1)[1])
    ok = lambda n: f"{parent_q}.{n}" in present  # noqa: E731
    loc = lambda n: _local(rel, f"{parent_q}.{n}")  # noqa: E731
    prev = next((loc(n) for n in reversed(names[:i]) if ok(n)), None)
    nxt = next((loc(n) for n in names[i + 1:] if ok(n)), None)
    return prev, nxt


def _call(fn, root, **kw):
    try:
        return fn(root, **kw)
    except sl.SymError as e:
        return {"status": "error", "error_type": e.error_type, "error_message": e.message}


def git(root, *args, check=True, inp=None):
    return subprocess.run(["git", "-C", root, *args], check=check, capture_output=True, text=True, input=inp)


def analyse(task, run_tests=False):
    root = checkout(task)
    reset_checkout(root)
    g = load_graph(task)
    graph_defs = None
    if g is not None:
        graph_defs = set()
        # map graph names back to true qnames via the emulator (per file)
        names = {n["name"] for n in g["nodes"]}
        for rel in sl.iter_py(root):
            try:
                tree = ast.parse(sl.read(root, rel))
            except SyntaxError:
                continue
            tq = {(s.node.lineno, s.node.col_offset): s.qname for s in sl.index_file(root, rel)}
            for gn, node in graph_names(tree, sl.module_name(rel)):
                if gn in names and isinstance(node, ast.FunctionDef):
                    graph_defs.add(tq.get((node.lineno, node.col_offset)))
    fds = file_diffs(task["patch"])
    files = []
    old_files = {}
    for fd in fds:
        if fd["old_path"] and fd["old_path"] != "/dev/null" and os.path.exists(os.path.join(root, fd["old_path"])):
            old_files[fd["old_path"]] = sl.read(root, fd["old_path"])
    r = git(root, "apply", "--whitespace=nowarn", "-", check=False, inp=task["patch"] + "\n")
    if r.returncode != 0:
        reset_checkout(root)
        return {"instance_id": task["instance_id"], "error": "gold patch does not apply"}
    new_files = {}
    for fd in fds:
        p = fd["new_path"]
        if p and p != "/dev/null" and os.path.exists(os.path.join(root, p)):
            new_files[p] = sl.read(root, p)
    reset_checkout(root)

    rec = {"instance_id": task["instance_id"], "repo": short_repo(task), "files": []}
    for fd in fds:
        op, np_ = fd["old_path"], fd["new_path"]
        path = np_ if np_ != "/dev/null" else op
        fr = {"path_kind": "py" if path.endswith(".py") else os.path.splitext(path)[1] or "noext",
              "test_file": sl.is_test_path(path)}
        if op == "/dev/null" or op not in old_files:
            fr["status"] = "new_file"
        elif np_ == "/dev/null":
            fr["status"] = "deleted_file"
        elif not path.endswith(".py"):
            fr["status"] = "non_python"
        else:
            ops, plan = classify_file(old_files[op], new_files[np_], np_, graph_defs)
            fr["status"] = "modified_py"
            fr["ops"] = collections.Counter(o["cat"] for o in ops)
            fr["plan"] = plan
            fr["gold_changed_lines"] = fd["added"] + fd["removed"]
            if plan is not None and not any(o["cat"].startswith("module.") and o["cat"] not in (
                    "module.blank_comment", "module.new_symbol") for o in ops) and "unparseable" not in fr["ops"]:
                st, calls, payload = execute_plan(root, np_, new_files[np_], plan)
                fr["replay"] = st
                fr["replay_calls"], fr["replay_payload_lines"] = calls, payload
                if st == "ok":
                    got = sl.read(root, np_)
                    if got == new_files[np_]:
                        fr["replay_match"] = "exact"
                    elif ast.dump(ast.parse(got)) == ast.dump(ast.parse(new_files[np_])):
                        fr["replay_match"] = "ast_equal"
                    elif sorted(map(ast.dump, ast.parse(got).body)) == sorted(map(ast.dump, ast.parse(new_files[np_]).body)):
                        fr["replay_match"] = "reordered_toplevel"
                    else:
                        fr["replay_match"] = "differs"
        rec["files"].append(fr)
    if run_tests:
        rec["tests"] = run_replay_tests(task, root)
    reset_checkout(root)
    return rec


def run_replay_tests(task, root):
    """Placeholder hook: tests run in pilot_b/analysis/replay_tests.py (needs a per-repo venv)."""
    return None


TOOL_LEVELS = [
    ("L0_graph_def_nodes", {"def"}),
    ("L1_+any_def_by_ast", {"def", "def.not_graph_node", "async_def"}),
    ("L2_+whole_class_replace", {"def", "def.not_graph_node", "async_def", "class.body_stmt", "class.new_method", "class.blank_comment"}),
    ("L3_+insert_new_symbol", {"def", "def.not_graph_node", "async_def", "class.body_stmt", "class.new_method", "class.blank_comment",
                               "module.new_symbol"}),
]


def summarise(recs):
    out = {"tasks": len(recs)}
    cats = collections.Counter()
    task_level = collections.Counter()
    blockers = collections.Counter()
    replay = collections.Counter()
    payload_ratio = []
    for r in recs:
        src_files = [f for f in r.get("files", []) if not f["test_file"]]
        py_mod = [f for f in src_files if f["status"] == "modified_py"]
        other = [f for f in src_files if f["status"] != "modified_py"]
        task_ops = collections.Counter()
        for f in py_mod:
            task_ops.update(f["ops"])
        cats.update(task_ops)
        ignorable = {"module.blank_comment"}
        needed = set(task_ops) - ignorable
        r["needs"] = sorted(needed)
        other_kinds = sorted({f["status"] + ("" if f["status"] != "non_python" else ":" + f["path_kind"]) for f in other})
        r["other_files"] = other_kinds
        py_other = [f for f in other if f["path_kind"] == "py"]
        level = None
        for name, allowed in TOOL_LEVELS:
            if needed and needed <= allowed and not py_other:
                level = name
                break
        if not py_mod and not py_other:
            level = "no_python_change"
        r["level"] = level or "not_expressible"
        task_level[r["level"]] += 1
        if level is None:
            for c in needed - TOOL_LEVELS[-1][1]:
                blockers[c] += 1
            for f in py_other:
                blockers["py." + f["status"]] += 1
        r["has_non_py_files"] = bool([f for f in other if f["path_kind"] != "py"])
        for f in py_mod:
            if "replay" in f:
                replay[f["replay"] + ("/" + f.get("replay_match", "") if f["replay"] == "ok" else "")] += 1
                if f["gold_changed_lines"]:
                    payload_ratio.append(f["replay_payload_lines"] / f["gold_changed_lines"])
    out["op_categories"] = dict(cats.most_common())
    out["task_levels"] = dict(task_level)
    cum, running = {}, 0
    for name, _ in TOOL_LEVELS:
        running += task_level.get(name, 0)
        cum[name] = running
    out["task_levels_cumulative"] = cum
    out["blockers_for_not_expressible"] = dict(blockers.most_common())
    out["tasks_with_non_python_files"] = sum(r["has_non_py_files"] for r in recs)
    out["replay_files"] = dict(replay)
    if payload_ratio:
        pr = sorted(payload_ratio)
        out["payload_lines_over_gold_changed_lines"] = {"median": pr[len(pr) // 2], "p90": pr[int(len(pr) * 0.9)],
                                                        "max": pr[-1], "n_files": len(pr)}
    return out


def main():
    run_tests = "--tests" in sys.argv
    recs = []
    for t in load_tasks():
        r = analyse(t, run_tests)
        recs.append(r)
        print(t["instance_id"], [(f["status"], dict(f.get("ops", {})), f.get("replay"), f.get("replay_match")) for f in r.get("files", []) if not f["test_file"]], flush=True)
    s = summarise(recs)
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "expressibility.json"), "w") as f:
        json.dump(s, f, indent=1)
    with open(os.path.join(ROOT, "results", "expressibility_tasks.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps({k: r.get(k) for k in ("instance_id", "repo", "level", "needs", "other_files", "error")}) + "\n")
    print(json.dumps(s, indent=1))


if __name__ == "__main__":
    main()
