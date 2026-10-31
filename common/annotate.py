"""Intervention-ready annotations for swegemma-format tasks (held-out or dev).

Per task:
  edit_hunks:   each code-patch hunk -> file, old line span, enclosing symbol as a graph node id
                (released id rule, common/graph_build.released_ids_for_file) or "<module>" if at module level
  gold_nodes:   unique node ids edited by the gold patch (localization ground truth, graph id space)
  gold_nodes_missing_from_graph_rule: edited symbols the released-style graph cannot contain
                (module-level code, async defs)
  added_symbols: defs/classes that only exist after the patch (new functions)
  repro_test:   (needs FAIL_TO_PASS) a minimal runnable pytest file: test-file imports and module-level
                statements + only the F2P tests (TestCase classes keep setUp/fixtures/helpers), with
                --verify: run in the harness sandbox, must FAIL before and PASS after the gold patch.

Usage (interpreter with swegemma + codegraph-loc installed):
  python common/annotate.py --tasks T.jsonl --snapshots DIR --out ANN.jsonl [--testmap TM.jsonl] [--verify]
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import re
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.graph_build import released_ids_for_file  # noqa: E402

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def parse_hunks(patch: str):
    """Yield (file, old_start, old_len, new_start, new_len, changed_old_lines, changed_new_lines)."""
    cur, h = None, None
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:]
            continue
        if line.startswith("--- "):
            continue
        m = HUNK_RE.match(line)
        if m:
            if h:
                yield h
            os_, ol, ns, nl = int(m[1]), int(m[2] or 1), int(m[3]), int(m[4] or 1)
            h = {"file": cur, "old_start": os_, "old_len": ol, "new_start": ns, "new_len": nl,
                 "old_changed": [], "new_changed": [], "_o": os_, "_n": ns}
            continue
        if h is None:
            continue
        if line.startswith("-"):
            h["old_changed"].append(h["_o"]); h["_o"] += 1
        elif line.startswith("+"):
            h["new_changed"].append(h["_n"]); h["_n"] += 1
        else:
            h["_o"] += 1; h["_n"] += 1
    if h:
        yield h


def _defs_with_spans(src: str):
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([n.lineno] + [d.lineno for d in n.decorator_list])
            out.append((start, n.end_lineno, n.lineno, isinstance(n, ast.AsyncFunctionDef)))
    return out


def enclosing(defs, line):
    best = None
    for s, e, defline, is_async in defs:
        if s <= line <= e and (best is None or s >= best[0]):
            best = (s, e, defline, is_async)
    return best


def module_name(root: Path, rel: str) -> str:
    from cgl.graph import module_name_for
    return module_name_for(root / rel, root, scheme="official")[0]


def locate(root: Path, task: dict) -> dict:
    hunks, gold, missing = [], set(), set()
    new_files = {}
    for h in parse_hunks(task["patch"]):
        rel = h["file"]
        if not rel.endswith(".py"):
            continue
        f = root / rel
        mod = module_name(root, rel)
        src = f.read_text(encoding="utf-8", errors="replace") if f.exists() else ""
        defs, ids = _defs_with_spans(src), released_ids_for_file(f, mod) if f.exists() else {}
        lines = h["old_changed"] or [max(1, h["old_start"] + (h["old_len"] - 1) // 2)]  # pure insertion: anchor
        syms = set()
        for ln in lines:
            enc = enclosing(defs, ln)
            if enc is None:
                syms.add(f"{mod}.<module>"); missing.add(f"{mod}.<module>")
            elif enc[2] in ids:
                syms.add(ids[enc[2]])
            else:  # async def or other def the released graphs do not contain
                tag = f"{mod}.<async@{enc[2]}>" if enc[3] else f"{mod}.<def@{enc[2]}>"
                syms.add(tag); missing.add(tag)
        gold |= {s for s in syms if "<" not in s}
        hunks.append({"file": rel, "old_start": h["old_start"], "old_len": h["old_len"], "symbols": sorted(syms)})
        new_files.setdefault(rel, []).extend(h["new_changed"])
    return {"edit_hunks": hunks, "gold_nodes": sorted(gold),
            "gold_nodes_missing_from_graph_rule": sorted(missing), "_new_lines": new_files}


def added_symbols(new_root: Path, new_lines: dict, old_ids: set[str]) -> list[str]:
    out = set()
    for rel, lines in new_lines.items():
        f = new_root / rel
        if not f.exists():
            continue
        ids = released_ids_for_file(f, module_name(new_root, rel))
        defs = _defs_with_spans(f.read_text(encoding="utf-8", errors="replace"))
        for ln in lines:
            enc = enclosing(defs, ln)
            if enc and enc[2] in ids and ids[enc[2]] not in old_ids:
                out.add(ids[enc[2]])
    return sorted(out)


# ---------------- reproduction tests ----------------

def build_repro(test_src: str, f2p_nodes: list[str], test_path: str) -> str | None:
    """Keep imports + module-level non-test statements + only the selected tests."""
    tree = ast.parse(test_src)
    want_funcs, want_methods = set(), {}
    for node in f2p_nodes:
        parts = node.split("::")
        if parts[0] != test_path:
            continue
        name = parts[-1].split("[", 1)[0]
        if len(parts) == 2:
            want_funcs.add(name)
        else:
            want_methods.setdefault(parts[1], set()).add(name)
    if not want_funcs and not want_methods:
        return None
    body = []
    for st in tree.body:
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if st.name.startswith("test"):
                if st.name in want_funcs:
                    body.append(st)
            else:
                body.append(st)  # helpers and fixtures
        elif isinstance(st, ast.ClassDef):
            if st.name in want_methods:
                keep = [b for b in st.body if not (isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))
                                                   and b.name.startswith("test") and b.name not in want_methods[st.name])]
                st.body = keep or [ast.Pass()]
                body.append(st)
            elif not st.name.startswith("Test"):
                body.append(st)  # helper / base classes
        else:
            body.append(st)
    tree.body = body
    return ast.unparse(tree) + "\n"


def _sandbox_run_repro(snap: Path, repo: str, repro: str, gold_patch: str, test_patch: str):
    from swegemma.harness.container_setup import (apply_patch_in_container, extract_snapshot, setup_baseline_commit,
                                                  setup_git_exclude, setup_workspace_test_config)
    from swegemma.sandbox.subprocess import SubprocessManager

    def apply(sb, sid, patch):
        with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as fh:
            fh.write(patch if patch.endswith("\n") else patch + "\n")
        sb.copy_to(sid, Path(fh.name), "/tmp/")
        rc = apply_patch_in_container(sb, sid, f"/tmp/{Path(fh.name).name}")[0]
        Path(fh.name).unlink(missing_ok=True)
        return rc

    sb = SubprocessManager(timeout_seconds=600)
    sid = sb.start()
    try:
        extract_snapshot(sb, sid, snap)
        setup_git_exclude(sb, sid)
        setup_workspace_test_config(sb, sid, repo=repo)
        setup_baseline_commit(sb, sid, "eval_baseline")
        # test_patch may add fixtures/data the repro needs (it never adds library code)
        apply(sb, sid, test_patch)
        sb.write_file("/tmp/test_repro_injected.py", repro)
        cmd = ("cd /workspace && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 timeout 240 python3 -s -m pytest "
               "/tmp/test_repro_injected.py -p no:anyio -p no:cacheprovider -o timeout=60 -q >/dev/null 2>&1; echo $?")
        before = (sb.exec(sid, cmd).stdout or "").strip().splitlines()[-1:]
        apply(sb, sid, gold_patch)
        after = (sb.exec(sid, cmd).stdout or "").strip().splitlines()[-1:]
    finally:
        sb.stop(sid)
    return (before[0] if before else "?"), (after[0] if after else "?")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", required=True)
    p.add_argument("--snapshots", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--testmap")
    p.add_argument("--verify", action="store_true")
    p.add_argument("--ids", nargs="*")
    a = p.parse_args()
    tm = {r["instance_id"]: r for r in map(json.loads, open(a.testmap))} if a.testmap else {}
    with open(a.out, "w") as out:
        for line in open(a.tasks):
            t = json.loads(line)
            if a.ids and t["instance_id"] not in a.ids:
                continue
            snap = Path(a.snapshots) / f"{t['instance_id']}.tgz"
            with tempfile.TemporaryDirectory() as td:
                root = Path(td) / "ws"
                with tarfile.open(snap) as tf:
                    tf.extractall(root, filter="data")
                rec = {"instance_id": t["instance_id"], **locate(root, t)}
                # apply gold + test patch in a scratch copy to find added symbols and the post-test file
                import subprocess
                for patch in (t["patch"], t["test_patch"]):
                    pf = Path(td) / "p.patch"
                    pf.write_text(patch + ("\n" if not patch.endswith("\n") else ""))
                    subprocess.run(["git", "-c", "safe.directory=*", "-C", str(root), "apply", "--unsafe-paths",
                                    str(pf)], capture_output=True)
                rec["added_symbols"] = added_symbols(root, rec.pop("_new_lines"), set(rec["gold_nodes"]))
                f2p = tm.get(t["instance_id"], {}).get("FAIL_TO_PASS", [])
                if f2p:
                    test_path = f2p[0].split("::")[0]
                    src = (root / test_path).read_text(encoding="utf-8", errors="replace")
                    repro = build_repro(src, f2p, test_path)
                    rec["repro_test"] = {"source_file": test_path, "n_f2p": len(f2p), "code": repro}
                    if repro and a.verify:
                        rc_before, rc_after = _sandbox_run_repro(snap, t["repo"], repro, t["patch"], t["test_patch"])
                        rec["repro_test"].update(exit_before_gold=rc_before, exit_after_gold=rc_after,
                                                 verified=(rc_before not in ("0", "?") and rc_after == "0"))
            out.write(json.dumps(rec) + "\n")
            print(t["instance_id"], len(rec["gold_nodes"]), "gold nodes;",
                  "missing", len(rec["gold_nodes_missing_from_graph_rule"]),
                  "| repro verified:", rec.get("repro_test", {}).get("verified"), flush=True)


if __name__ == "__main__":
    main()
