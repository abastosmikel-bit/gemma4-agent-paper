"""Information-ladder probe: per-task records, canonical actions, rung texts, controls, classification.

Pure CPU code (no harness imports). Implements docs/PLAN.md §3-§5 and the Level B record of
docs/PROBE_INPUT.md (paper/main). Outputs derived from task data stay private (on Kaggle).
"""
from __future__ import annotations

import json
import re
import tarfile
from pathlib import Path
from typing import Any

from common.diffs import FileDiff, is_test_path, parse_unified_diff, required_test_names
from common.locate import collect_scopes, module_path, report_scope
from pilot_c.hints import _HEADER as LOC_HEADER

MAX_READ_LINES = 150
MAX_READ_CHARS = 10000
TEST_SOURCE_MAX_LINES = 60

LADDER = ("L0", "L1", "L2", "L3", "L4", "L5")
FIND_CONDS = ("L0", "L1", "L2", "T", "W", "G-json", "G-edges", "G-adj", "X-file", "X-func", "X-graph")
USE_CONDS = ("L0", "L1", "L2", "L3", "L4", "L5", "T", "W", "G-json", "G-edges", "G-adj",
             "X-file", "X-func", "X-graph", "X-test", "X-words")
D2_FIND = ("L0", "L1", "L2", "G-json", "G-edges", "X-func")
D2_USE = ("L0", "L2", "L3", "L4", "L5", "T", "W", "G-json", "X-func", "X-test")
GRAPH_CONDS = {"G-json": "json", "G-edges": "edges", "G-adj": "adj", "X-graph": "json"}
WORDS_CONDS = {"L4", "L5", "W", "X-words"}


# --------------------------------------------------------------------------- snapshot access

def snapshot_scan(tgz: str | Path, wanted: set[str]) -> tuple[dict[str, str], list[str]]:
    """One pass over the archive: text of `wanted` files + list of all non-test .py paths."""
    texts: dict[str, str] = {}
    py: list[str] = []
    with tarfile.open(tgz, mode="r|gz") as tf:
        for m in tf:
            name = m.name[2:] if m.name.startswith("./") else m.name
            if not m.isfile() or name.startswith(".git/"):
                continue
            if name.endswith(".py") and not is_test_path(name):
                py.append(name)
            if name in wanted:
                fh = tf.extractfile(m)
                if fh is not None:
                    texts[name] = fh.read().decode("utf-8", errors="replace")
    return texts, sorted(py)


def harness_read_output(filepath: str, text: str, start: int, end: int) -> str:
    """Exact swegemma 0.2.11 read_file response (tools/workspace.py) for a line range."""
    lines = text.splitlines()
    total = len(lines)
    s, e = max(start, 1), min(end, total)
    trunc = False
    if e - s + 1 > MAX_READ_LINES:
        e, trunc = s + MAX_READ_LINES - 1, True
    snippet = "\n".join(lines[s - 1:e])
    if len(snippet) > MAX_READ_CHARS:
        snippet, trunc = snippet[:MAX_READ_CHARS], True
    return json.dumps({"status": "ok", "filepath": filepath, "content": snippet, "start_line": s, "end_line": e,
                       "total_lines": total, "is_truncated": trunc}, ensure_ascii=False)


# --------------------------------------------------------------------------- canonical edit

def _new_region(lines: list[str], fd: FileDiff, a: int, b: int) -> list[str]:
    removed = set(fd.removed_old_lines)
    ins: dict[int, list[str]] = {}
    for x in fd.insertions:
        ins.setdefault(x.after_old, []).extend(x.lines)
    out: list[str] = []
    for ln in range(a, b + 1):
        if ln not in removed:
            out.append(lines[ln - 1])
        out.extend(ins.get(ln, []))
    return out


def canonical_edit(base: str, fd: FileDiff, fs: int, fe: int) -> dict[str, Any] | None:
    """old/new strings for the gold change inside lines [fs, fe] of the base file (PLAN §4.3)."""
    lines = base.splitlines()
    rem = [ln for ln in fd.removed_old_lines if fs <= ln <= fe]
    ins = [x for x in fd.insertions if fs <= x.after_old <= fe and any(l.strip() for l in x.lines)]
    if not rem and not ins:
        return None
    pts = rem + [x.after_old for x in ins]
    a, b = max(1, min(pts)), min(len(lines), max(pts))
    for _ in range(12):
        old = "\n".join(lines[a - 1:b])
        if old.strip() and base.count(old) == 1:
            break
        if b < min(len(lines), fe + 3):
            b += 1
        elif a > max(1, fs - 3):
            a -= 1
        else:
            return None
    else:
        return None
    new = "\n".join(_new_region(lines, fd, a, b))
    while not new.strip() and (a > 1 or b < len(lines)):  # pure deletion: keep a neighbouring anchor line
        if a > 1:
            a -= 1
        else:
            b += 1
        old = "\n".join(lines[a - 1:b])
        new = "\n".join(_new_region(lines, fd, a, b))
    if new == old or base.count(old) != 1:
        return None
    changed = sorted(set(rem) | {x.after_old for x in ins})
    outside = sum(1 for ln in fd.removed_old_lines if not fs <= ln <= fe) + \
        sum(1 for x in fd.insertions if not fs <= x.after_old <= fe and any(l.strip() for l in x.lines))
    return {"old_string": old, "new_string": new, "old_start": a, "old_end": b,
            "changed_lines": [min(changed), max(changed)], "outside_edits": outside}


def apply_edit(base: str, old: str, new: str) -> tuple[str | None, str]:
    """Apply an edit_file call. Uses the harness's own 4-tier apply_replacement (adk-eval-core) when it is
    installed (Kaggle, dry runs); otherwise a local exact + whitespace-flexible approximation."""
    try:
        from adk_eval_core.editing.edit import apply_replacement
    except ImportError:
        apply_replacement = None
    if apply_replacement is not None:
        r = apply_replacement(base, old, new)
        ok = not getattr(r, "error_message", None) and getattr(r, "occurrences", 0) == 1
        return (r.new_content if ok else None), (getattr(r, "strategy", "harness") if ok else "none")
    if old and base.count(old) == 1:
        return base.replace(old, new, 1), "exact"
    bl = base.splitlines()
    ol = [x.strip() for x in old.splitlines()]
    if not ol:
        return None, "none"
    hits = [i for i in range(len(bl) - len(ol) + 1) if [x.strip() for x in bl[i:i + len(ol)]] == ol]
    if len(hits) != 1:
        return None, "none"
    i = hits[0]
    ind = len(bl[i]) - len(bl[i].lstrip())
    nl = new.splitlines()
    nind = (len(nl[0]) - len(nl[0].lstrip())) if nl else 0
    shifted = [(" " * max(0, ind + len(x) - len(x.lstrip()) - nind) + x.lstrip()) if x.strip() else x for x in nl]
    return "\n".join(bl[:i] + shifted + bl[i + len(ol):]) + ("\n" if base.endswith("\n") else ""), "flexible"


def _norm(text: str) -> str:
    return "\n".join(l.rstrip() for l in text.strip().splitlines())


# --------------------------------------------------------------------------- test source / diff

def test_source(test_patch: str, names: list[str] | None = None, max_lines: int = TEST_SOURCE_MAX_LINES) -> str:
    """The reproduction-test rung: test_patch as it reads AFTER applying it (context + added lines,
    no removed lines), per file and hunk, capped at `max_lines`. Uniform for new test functions and
    for changes to test data/parametrization (where the scorer's test name may not enclose the change)."""
    out: list[str] = []
    for fd_block in re.split(r"(?m)^(?=--- )", test_patch):
        if not fd_block.strip():
            continue
        m = re.search(r"(?m)^\+\+\+ b/(.+)$", fd_block)
        out.append(f"# {m.group(1) if m else '?'}")
        for hunk in re.split(r"(?m)^(?=@@ )", fd_block)[1:]:
            body = [l[1:] for l in hunk.splitlines()[1:] if l[:1] in ("+", " ")]
            out += body + ["# ..."]
    return "\n".join(out[:max_lines]).rstrip()


def file_diff_text(patch: str, path: str) -> str:
    for block in re.split(r"(?m)^(?=--- )", patch):
        if block.startswith(f"--- a/{path}\n") or f"\n+++ b/{path}\n" in block[:400]:
            return block.rstrip("\n")
    return ""


# --------------------------------------------------------------------------- Level B record

def build_probe_record(task: dict, gold: dict, snapshot_tgz: str | Path) -> tuple[dict | None, str]:
    """Return (record, reason). record is None when the task is excluded (PLAN §9, rule 3)."""
    if len(gold.get("src_files") or []) != 1 or gold.get("new_src_files") or not gold.get("functions"):
        return None, "not eligible"
    path = gold["src_files"][0]
    texts, py = snapshot_scan(snapshot_tgz, {path})
    base = texts.get(path)
    if base is None:
        return None, "gold file missing in snapshot"
    fd = next(f for f in parse_unified_diff(task["patch"]) if f.path == path)
    scopes = {s.qualname: s for s in collect_scopes(base)}
    edit = fn = None
    for f in sorted(gold["functions"], key=lambda f: f["def_line"]):
        sc = scopes.get(f["qualname"])
        if sc is None:
            continue
        e = canonical_edit(base, fd, sc.start, sc.end)
        if e is not None:
            edit, fn = e, (f, sc)
            break
    if edit is None:
        return None, "no canonical edit"
    f, sc = fn
    total = len(base.splitlines())
    rs, re_ = sc.start, min(sc.end, sc.start + MAX_READ_LINES - 1)
    if edit["changed_lines"][1] > re_:
        return None, "change outside read span"
    names = required_test_names(task["test_patch"])
    tfiles = [fd2.path for fd2 in parse_unified_diff(task["test_patch"]) if fd2.new_path]
    rec = {
        "instance_id": task["instance_id"], "repo": task["repo"], "base_commit": task["base_commit"],
        "problem_statement": task["problem_statement"], "hints_text": task.get("hints_text") or "",
        "gold": {"file": path, "qualname": f["qualname"], "dotted": f["dotted"], "kind": f["kind"],
                 "start_line": sc.start, "def_line": sc.def_line, "end_line": sc.end, "file_total_lines": total},
        "find_target": {"tool": "read_file", "args": {"filepath": path, "start_line": rs, "end_line": re_}},
        "read_output": harness_read_output(path, base, rs, re_),
        "edit_target": {"tool": "edit_file", "args": {"filepath": path, "old_string": edit["old_string"],
                                                      "new_string": edit["new_string"]}},
        "edit_region": [edit["old_start"], edit["old_end"]], "changed_lines": edit["changed_lines"],
        "outside_edits": edit["outside_edits"],
        "diff": file_diff_text(task["patch"], path),
        "test": {"files": tfiles, "names": names, "files_exist": not (set(gold.get("new_test_files") or []) >= set(tfiles)),
                 "source": test_source(task["test_patch"])},
        "graph": None, "words": None, "wrong": {},
        "_base_text": base, "_py_files": py,  # private helpers, dropped before saving
    }
    rec["wrong"].update(_wrong_location(rec, base, py))
    return rec, "ok"


# --------------------------------------------------------------------------- rung texts

def loc_file_text(path: str) -> str:
    return f"{LOC_HEADER}\n- The fix changes `{path}`."


def loc_func_text(path: str, dotted: str, kind: str, def_line: int) -> str:
    what = "class body of" if kind == "class" else "function"
    return f"{loc_file_text(path)}\n- In `{path}`: {what} `{dotted}` (defined at line {def_line})."


def test_text(rec: dict, source: str | None = None, files: list[str] | None = None, exists: bool | None = None) -> str:
    files = rec["test"]["files"] if files is None else files
    exists = rec["test"]["files_exist"] if exists is None else exists
    status = "exists" if exists else "does not exist yet; it is added when your fix is verified"
    src = rec["test"]["source"] if source is None else source
    return (f"## Reproduction test (verified)\nThe fix is verified by this test from `{', '.join(files)}` "
            f"(the file {status}):\n```python\n{src}\n```")


def words_text(words: str) -> str:
    return f"## The change, in words\n{words}"


def diff_text(diff: str) -> str:
    return f"## The exact change\n```diff\n{diff}\n```"


def rung_text(rec: dict, cond: str) -> str | None:
    """Text appended to the problem statement for `cond` (None = graph-only or none). None if unavailable."""
    g, w = rec["gold"], rec["wrong"]
    words = rec.get("words")
    parts: list[str] = []
    if cond in ("L1", "L2", "L3", "L4", "L5"):
        parts.append(loc_file_text(g["file"]) if cond == "L1" else loc_func_text(g["file"], g["dotted"], g["kind"], g["def_line"]))
    if cond in ("L3", "L4", "L5", "T"):
        parts.append(test_text(rec))
    if cond in ("L4", "L5", "W"):
        if not words:
            return None
        parts.append(words_text(words))
    if cond == "L5":
        parts.append(diff_text(rec["diff"]))
    if cond == "X-file":
        parts.append(loc_file_text(w["file"]))
    if cond == "X-func":
        parts.append(loc_func_text(g["file"], w["dotted"], w["kind"], w["def_line"]))
    if cond == "X-test":
        if not w.get("test_source"):
            return None
        parts += [loc_func_text(g["file"], g["dotted"], g["kind"], g["def_line"]),
                  test_text(rec, w["test_source"], w["test_files"], w["test_exists"])]
    if cond == "X-words":
        if not w.get("words") or not words:
            return None
        parts += [loc_func_text(g["file"], g["dotted"], g["kind"], g["def_line"]), test_text(rec), words_text(w["words"])]
    return "\n\n".join(parts) if parts else ""


def insert_hint(user_text: str, problem_statement: str, hint: str) -> tuple[str, str]:
    """Append `hint` to the problem statement inside the harness task prompt, exactly as
    pilot_c.hints.rewrite_task would have produced it. Returns (text, method)."""
    if not hint:
        return user_text, "none"
    new_ps = problem_statement.rstrip() + "\n\n" + hint + "\n"
    if problem_statement in user_text:
        return user_text.replace(problem_statement, new_ps, 1), "exact"
    m = re.search(r"\n\n## ", user_text[user_text.find("Problem Statement:"):])
    if m:
        k = user_text.find("Problem Statement:") + m.start()
        return user_text[:k] + "\n\n" + hint + user_text[k:], "before-next-section"
    return user_text + "\n\n" + hint, "append"


# --------------------------------------------------------------------------- graph encodings

def encode_graph(focal: str, nodes: list[str], edges: list[dict], fmt: str) -> str:
    """Same content, three layouts (PLAN §4.2). nodes/edges as from get_code_subgraph."""
    nodes = [focal] + [n for n in nodes if n != focal]
    if fmt == "json":
        return json.dumps({"status": "ok", "nodes": nodes, "edges": edges, "node_count": len(nodes),
                           "edge_count": len(edges), "is_truncated": False}, ensure_ascii=False)
    if fmt == "edges":
        lines = [f"{e['from']} -[{e.get('type', 'calls')}]-> {e['to']}" for e in edges]
        return "\n".join(lines) if lines else f"{focal} (no edges)"
    if fmt == "adj":
        out = []
        for n in nodes:
            calls = [e["to"] for e in edges if e["from"] == n]
            by = [e["from"] for e in edges if e["to"] == n]
            out.append(f"{n}: calls {', '.join(calls) or '-'}; called by {', '.join(by) or '-'}")
        return "\n".join(out)
    raise ValueError(fmt)


# --------------------------------------------------------------------------- wrong controls

def _closest(target_len: int, cands: list[tuple[str, Any]], render) -> tuple[Any, float] | None:
    best = None
    for key, val in sorted(cands, key=lambda kv: kv[0]):
        r = len(render(val)) / max(1, target_len)
        d = abs(r - 1)
        if best is None or d < best[2]:
            best = (val, r, d)
    return (best[0], round(best[1], 3)) if best else None


def _wrong_location(rec: dict, base: str, py: list[str]) -> dict:
    g = rec["gold"]
    out: dict[str, Any] = {}
    files = [p for p in py if p != g["file"] and p.split("/")[0] == g["file"].split("/")[0]] or [p for p in py if p != g["file"]]
    pick = _closest(len(loc_file_text(g["file"])), [(p, p) for p in files], loc_file_text)
    if pick:
        out["file"], out["file_len_ratio"] = pick
    mod = module_path(g["file"])
    gold_q = g["qualname"]
    cands = []
    for s in collect_scopes(base):
        rs = report_scope([s])
        if s.qualname == gold_q or gold_q.startswith(s.qualname + ".") or s.qualname.startswith(gold_q + "."):
            continue
        if rs is not s or s.qualname.count(".") > 1:
            continue
        cands.append((s.qualname, {"dotted": f"{mod}.{s.qualname}" if mod else s.qualname, "kind": s.kind,
                                   "def_line": s.def_line, "qualname": s.qualname}))
    pick = _closest(len(loc_func_text(g["file"], g["dotted"], g["kind"], g["def_line"])), cands,
                    lambda v: loc_func_text(g["file"], v["dotted"], v["kind"], v["def_line"]))
    if pick:
        v, r = pick
        out.update({"dotted": v["dotted"], "kind": v["kind"], "def_line": v["def_line"], "qualname": v["qualname"],
                    "func_len_ratio": r})
    return out


def assign_cross_task_controls(records: list[dict]) -> None:
    """X-test and X-words donors: another record of the same repo with the closest text length."""
    for rec in records:
        same = [r for r in records if r["repo"] == rec["repo"] and r["instance_id"] != rec["instance_id"]]
        pick = _closest(len(rec["test"]["source"]), [(r["instance_id"], r) for r in same], lambda r: r["test"]["source"])
        if pick:
            d, ratio = pick
            rec["wrong"].update({"test_from": d["instance_id"], "test_source": d["test"]["source"],
                                 "test_files": d["test"]["files"], "test_exists": d["test"]["files_exist"],
                                 "test_len_ratio": ratio})
        if rec.get("words"):
            wsame = [(r["instance_id"], r) for r in same if r.get("words")]
            pick = _closest(len(rec["words"]), wsame, lambda r: r["words"])
            if pick:
                d, ratio = pick
                rec["wrong"].update({"words_from": d["instance_id"], "words": d["words"], "words_len_ratio": ratio})


# --------------------------------------------------------------------------- words rung

def words_prompt(diff: str, strict: bool = False) -> str:
    extra = " Do not copy any code, expression or string literal from the diff." if strict else ""
    return ("Describe the following code change in 1 to 3 plain English sentences for a developer who has to "
            "re-implement it. Say what behaviour changes and where. You may name functions or parameters, but do not "
            f"write code.{extra}\n\n```diff\n{diff}\n```")


def words_leak(words: str, diff: str, min_len: int = 20) -> bool:
    if len(words) > 600:
        return True
    plus = [l[1:].strip() for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    for l in plus:
        for i in range(0, max(0, len(l) - min_len) + 1):
            if len(l) >= min_len and l[i:i + min_len] in words:
                return True
    return False


# --------------------------------------------------------------------------- depth-2 classification

def _norm_path(p: Any) -> str:
    p = str(p or "").strip().lstrip("/")
    return p[len("workspace/"):] if p.startswith("workspace/") else p


def _parse_args(a: Any) -> dict:
    if isinstance(a, dict):
        return a
    try:
        v = json.loads(a or "{}")
        return v if isinstance(v, dict) else {}
    except (ValueError, TypeError):
        return {}


def classify_find(rec: dict, tool_calls: list[dict]) -> dict:
    g, w = rec["gold"], rec["wrong"]
    out = {"tool_call": bool(tool_calls), "hit_file": False, "hit_func": False, "followed_wrong": False, "tool": None}
    if not tool_calls:
        return out
    fn = tool_calls[0].get("function", {})
    name, args = fn.get("name"), _parse_args(fn.get("arguments"))
    out["tool"] = name

    def touches(path: str, lo: int | None, hi: int | None) -> tuple[bool, bool]:
        if name == "read_file" and _norm_path(args.get("filepath")) == path:
            s = int(args.get("start_line") or 1)
            e = int(args.get("end_line") or s + MAX_READ_LINES - 1)
            return True, (lo is not None and not (e < lo or s > hi))
        if name == "run_command" and path in str(args.get("command", "")):
            return True, False
        return False, False

    out["hit_file"], out["hit_func"] = touches(g["file"], g["start_line"], g["end_line"])
    if name in ("get_code_neighbors", "get_code_subgraph", "search_similar_code"):
        blob = json.dumps(args)
        out["hit_func"] = g["qualname"].split(".")[-1] in blob
    if w.get("file"):
        out["followed_wrong"] = touches(w["file"], None, None)[0]
    if w.get("qualname"):
        out["followed_wrong"] = out["followed_wrong"] or (w["qualname"].split(".")[-1] in json.dumps(args))
    return out


def classify_use(rec: dict, tool_calls: list[dict]) -> tuple[dict, str | None]:
    """Returns (flags, edited_file_text or None). Edited text is private (for CPU test verification)."""
    base = rec["_base_text"]
    g = rec["gold"]
    out = {"tool_call": bool(tool_calls), "tool": None, "edit_gold_file": False, "applies": False,
           "on_target": False, "exact": False, "followed_wrong": False}
    if not tool_calls:
        return out, None
    fn = tool_calls[0].get("function", {})
    name, args = fn.get("name"), _parse_args(fn.get("arguments"))
    out["tool"] = name
    path = _norm_path(args.get("filepath"))
    if name not in ("edit_file", "write_file") or path != g["file"]:
        if rec["wrong"].get("file") and path == rec["wrong"]["file"]:
            out["followed_wrong"] = True
        return out, None
    out["edit_gold_file"] = True
    if name == "edit_file":
        edited, how = apply_edit(base, str(args.get("old_string", "")), str(args.get("new_string", "")))
    else:
        edited, how = str(args.get("content", "")), "write"
    if edited is None:
        return out, None
    out["applies"] = True
    gold_edited, _ = apply_edit(base, rec["edit_target"]["args"]["old_string"], rec["edit_target"]["args"]["new_string"])
    bl, el = base.splitlines(), edited.splitlines()
    i = 0
    while i < min(len(bl), len(el)) and bl[i] == el[i]:
        i += 1
    j = 0
    while j < min(len(bl), len(el)) - i and bl[-1 - j] == el[-1 - j]:
        j += 1
    lo, hi = i + 1, len(bl) - j
    ga, gb = rec["changed_lines"]
    out["on_target"] = not (hi < ga - 1 or lo > gb + 1)
    out["exact"] = gold_edited is not None and _norm(edited) == _norm(gold_edited)
    if rec["wrong"].get("def_line") and rec["wrong"].get("qualname"):
        wl = rec["wrong"]["def_line"]
        out["followed_wrong"] = lo <= wl + 5 and hi >= wl and not out["on_target"]
    return out, edited


def public_record(rec: dict) -> dict:
    """Record without private helper fields (still competition-derived: keep on Kaggle)."""
    return {k: v for k, v in rec.items() if not k.startswith("_")}
