"""Pilot D: turn mined candidates into competition-format tasks (+ sidecar metadata).

Writes, under OUT_DIR (outside git):
  tasks.jsonl            competition fields (+ optional FAIL_TO_PASS/PASS_TO_PASS later)
  meta.jsonl             provenance: fix commit, PR, issue refs, dates, AI marker, timings
  snapshots/<iid>.tgz    dev-layout snapshot
problem_statement is left EMPTY with needs_issue_text=true: issue text must be fetched from the
GitHub API (common/github_text.py), which this cloud session cannot reach for third-party repos.

Usage: python -I pilot_d/build_tasks.py CANDIDATES.jsonl REPO_DIR OUT_DIR [--n N] [--issue-linked-only]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.snapshot import build_snapshot  # noqa: E402


def spread(rows, n):
    """Pick n rows spread evenly over time (rows sorted by commit date)."""
    rows = sorted(rows, key=lambda r: r["committed_at"])
    if len(rows) <= n:
        return rows
    step = len(rows) / n
    return [rows[int(i * step)] for i in range(n)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("candidates")
    p.add_argument("repo_dir")
    p.add_argument("out_dir")
    p.add_argument("--n", type=int, default=12)
    p.add_argument("--issue-linked-only", action="store_true")
    a = p.parse_args()
    rows = [json.loads(l) for l in open(a.candidates)]
    if a.issue_linked_only:
        rows = [r for r in rows if r["issue_refs"]]
    chosen = spread(rows, a.n)
    out = Path(a.out_dir)
    (out / "snapshots").mkdir(parents=True, exist_ok=True)
    with open(out / "tasks.jsonl", "a") as ft, open(out / "meta.jsonl", "a") as fm:
        for r in chosen:
            t0 = time.perf_counter()
            snap = build_snapshot(a.repo_dir, r["base_commit"], str(out / "snapshots" / f"{r['instance_id']}.tgz"))
            task = {
                "instance_id": r["instance_id"], "repo": r["repo"], "base_commit": r["base_commit"],
                "patch": r["patch"], "test_patch": r["test_patch"],
                "problem_statement": "", "hints_text": "", "created_at": r["authored_at"],
            }
            meta = {k: r[k] for k in ("instance_id", "repo", "fix_commit", "pr_number", "issue_refs", "subject",
                                      "committed_at", "authored_at", "code_files", "test_files",
                                      "code_lines_changed", "ai_authored_marker")}
            meta.update(snap, needs_issue_text=True, build_seconds=round(time.perf_counter() - t0, 1))
            ft.write(json.dumps(task) + "\n")
            fm.write(json.dumps(meta) + "\n")
            print(r["instance_id"], snap, meta["build_seconds"], flush=True)


if __name__ == "__main__":
    main()
