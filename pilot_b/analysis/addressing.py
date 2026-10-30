"""How should an edit site be addressed? Model-free properties of addressing schemes on gold patches.

For every gold hunk (line-level opcode) in modified non-test .py files:
  * staleness: would a line-number address computed before the fix be wrong when this hunk is
    applied (earlier hunks in the same file changed the line count)?
  * context cost: how many extra lines must a minimal text anchor grow, file-wide, before it is
    unique? (compare: naming the enclosing symbol)
  * graph at edit sites: for the innermost def/class touched, is its graph name missing (async),
    renamed (flattened), or shared with another definition in the same file?
Aggregates only -> results/addressing.json

usage: python -m pilot_b.analysis.addressing
"""
from __future__ import annotations

import collections
import difflib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from pilot_b.analysis.expressibility import git, sl  # noqa: E402
from common.patches import file_diffs  # noqa: E402
from common.tasks import checkout, load_tasks, reset_checkout  # noqa: E402


def grow_until_unique(text: str, lines: list[str], i1: int, i2: int, max_k: int = 10):
    """Smallest k (lines of context added alternately above/below) making the anchor unique, or None."""
    lo, hi = (i1, i2) if i2 > i1 else (i1 - 1, i1)
    for k in range(0, max_k + 1):
        a = max(0, lo - (k + 1) // 2)
        b = min(len(lines), hi + k // 2)
        needle = "\n".join(lines[a:b])
        if needle.strip() and text.count(needle) == 1:
            return k, len(needle)
    return None, None


def main():
    c = collections.Counter()
    ctx_k = []
    for t in load_tasks():
        root = checkout(t)
        reset_checkout(root)
        fds = [fd for fd in file_diffs(t["patch"]) if fd["new_path"].endswith(".py") and not sl.is_test_path(fd["new_path"])]
        olds = {fd["old_path"]: sl.read(root, fd["old_path"]) for fd in fds if os.path.exists(os.path.join(root, fd["old_path"]))}
        git(root, "apply", "-", inp=t["patch"] + "\n")
        news = {p: sl.read(root, p) for p in olds}
        reset_checkout(root)
        task_hunks, task_stale = 0, 0
        for p, old in olds.items():
            try:
                syms = sl.index_file("", p, old)
            except SyntaxError:
                continue
            gcount = collections.Counter(s.gname for s in syms if s.kind != "async def")
            ol, nl = old.split("\n"), news[p].split("\n")
            delta = 0
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ol, nl, autojunk=False).get_opcodes():
                if tag == "equal":
                    continue
                c["hunks"] += 1
                task_hunks += 1
                if delta != 0:
                    c["stale_line_address"] += 1
                    task_stale += 1
                delta += (j2 - j1) - (i2 - i1)
                k, n = grow_until_unique(old, ol, i1, i2)
                if k is None:
                    c["anchor_never_unique_k<=10"] += 1
                else:
                    ctx_k.append(k)
                    c[f"anchor_context_k={min(k, 3)}{'+' if k >= 3 else ''}"] += 1
                inner = [s for s in syms if s.start - 1 <= i1 and max(i2, i1 + 1) <= s.end]
                if not inner:
                    c["site.module_level"] += 1
                    continue
                s = min(inner, key=lambda x: x.end - x.start)
                c["site.in_symbol"] += 1
                if s.kind == "async def":
                    c["site.graph_missing_async"] += 1
                elif gcount[s.gname] > 1:
                    c["site.graph_name_shared"] += 1
                elif s.gname != s.qname:
                    c["site.graph_name_renamed_unique"] += 1
                else:
                    c["site.graph_name_exact"] += 1
        if task_hunks:
            c["tasks_with_hunks"] += 1
            c["tasks_with_a_stale_line_address"] += task_stale > 0
    out = dict(c)
    out["share_stale_line_address"] = c["stale_line_address"] / c["hunks"]
    out["share_anchor_needs_context"] = 1 - c["anchor_context_k=0"] / c["hunks"]
    out["mean_context_lines_when_needed"] = (sum(k for k in ctx_k if k) / max(1, sum(1 for k in ctx_k if k)))
    ins = c["site.in_symbol"]
    out["share_edit_sites_graph_misleads"] = (c["site.graph_missing_async"] + c["site.graph_name_shared"]) / ins
    with open(os.path.join(ROOT, "results", "addressing.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
