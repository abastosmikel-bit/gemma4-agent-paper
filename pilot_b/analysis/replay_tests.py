"""Step 4 (tests): run the task's tests on base, gold and symbol-edit replay, paired in one env.

For each task whose Python changes are expressible as symbol edits (results/expressibility_tasks.jsonl,
level != not_expressible), and for each of three working trees
  base   = base_commit + test_patch                       (should fail)
  gold   = base_commit + gold patch + test_patch          (should pass)
  replay = base_commit + graph-edit replay + test_patch   (the claim: behaves like gold)
run pytest on the test files touched by test_patch. A local PyPI venv per repo stands in for the
competition sandbox; because all three trees share it, env drift affects them equally.
Writes results/replay_tests.json (ids + pass/fail only).

usage: python -m pilot_b.analysis.replay_tests [--repos rich,requests] [--limit N]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from pilot_b.analysis.expressibility import classify_file, execute_plan, git, sl  # noqa: E402
from common.patches import file_diffs  # noqa: E402
from common.tasks import DATA_DIR, checkout, load_tasks, reset_checkout, short_repo  # noqa: E402

VENV = os.path.join(DATA_DIR, "venv")
PYPATH = {"requests": "src", "rich": ".", "fastapi": ".", "httpx": "."}


def run_tests(task, root, targets, timeout=180):
    py = os.path.join(VENV, short_repo(task), "bin", "python")
    env = dict(os.environ, PYTHONPATH=os.path.join(root, PYPATH[short_repo(task)]), PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([py, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:randomly", "-o", "addopts=", *targets],
                           cwd=root, env=env, capture_output=True, text=True, timeout=timeout)
        tail = p.stdout.strip().splitlines()[-1:] if p.stdout.strip() else []
        summ = re.sub(r"\s+in [\d.]+s.*$", "", tail[0]).strip("= ")[:200] if tail else ""
        return {"rc": p.returncode, "summary": summ}
    except subprocess.TimeoutExpired:
        return {"rc": "timeout", "summary": ""}


def apply(root, patch):
    return git(root, "apply", "--whitespace=nowarn", "-", check=False, inp=patch + "\n").returncode == 0


def replay(task, root):
    """Rebuild the gold patch's Python changes through the skill library. Returns status string."""
    fds = file_diffs(task["patch"])
    olds = {fd["old_path"]: sl.read(root, fd["old_path"]) for fd in fds
            if os.path.exists(os.path.join(root, fd["old_path"]))}
    if not apply(root, task["patch"]):
        return "gold_apply_failed"
    news = {fd["new_path"]: sl.read(root, fd["new_path"]) for fd in fds}
    reset_checkout(root)
    for fd in fds:
        p = fd["new_path"]
        if fd["old_path"] not in olds:                      # new file: written verbatim (not a symbol edit)
            os.makedirs(os.path.dirname(os.path.join(root, p)) or root, exist_ok=True)
            with open(os.path.join(root, p), "w") as f:
                f.write(news[p])
            continue
        if not p.endswith(".py") or olds[p] == news[p]:
            continue
        ops, plan = classify_file(olds[p], news[p], p, None)
        if plan is None:
            return "unparseable"
        st, *_ = execute_plan(root, p, news[p], plan)
        if st != "ok":
            return st
    return "ok"


def main():
    args = sys.argv[1:]
    repos = None
    limit = None
    if "--repos" in args:
        repos = set(args[args.index("--repos") + 1].split(","))
    if "--limit" in args:
        limit = int(args[args.index("--limit") + 1])
    levels = {}
    with open(os.path.join(ROOT, "results", "expressibility_tasks.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            levels[r["instance_id"]] = r["level"]
    out_path = os.path.join(ROOT, "results", "replay_tests.json")
    done = {}
    if os.path.exists(out_path):
        done = {r["instance_id"]: r for r in json.load(open(out_path))["tasks"]}
    tasks = [t for t in load_tasks() if levels.get(t["instance_id"], "not_expressible").startswith("L")
             and (repos is None or short_repo(t) in repos)]
    n = 0
    for t in tasks:
        if t["instance_id"] in done:
            continue
        if limit is not None and n >= limit:
            break
        n += 1
        root = checkout(t)
        reset_checkout(root)
        targets = sorted({fd["new_path"] for fd in file_diffs(t["test_patch"]) if fd["new_path"].endswith(".py")})
        rec = {"instance_id": t["instance_id"], "repo": short_repo(t), "level": levels[t["instance_id"]]}
        for cond in ("base", "gold", "replay"):
            reset_checkout(root)
            if cond == "gold" and not apply(root, t["patch"]):
                rec[cond] = {"rc": "apply_failed"}
                continue
            if cond == "replay":
                st = replay(t, root)
                rec["replay_status"] = st
                if st != "ok":
                    rec[cond] = {"rc": "replay_failed"}
                    continue
            if not apply(root, t["test_patch"]):
                rec[cond] = {"rc": "test_patch_failed"}
                continue
            rec[cond] = run_tests(t, root, targets)
        reset_checkout(root)
        done[t["instance_id"]] = rec
        print(t["instance_id"], {c: rec[c].get("rc") for c in ("base", "gold", "replay")}, flush=True)
        _save(out_path, done)
    _save(out_path, done)


def _save(path, done):
    rows = list(done.values())
    ok = lambda r, c: r.get(c, {}).get("rc") == 0  # noqa: E731
    informative = [r for r in rows if ok(r, "gold") and not ok(r, "base")]
    summary = {
        "tasks_run": len(rows),
        "gold_pass": sum(ok(r, "gold") for r in rows),
        "base_fail_gold_pass (informative)": len(informative),
        "replay_pass_on_informative": sum(ok(r, "replay") for r in informative),
        "replay_equals_gold_outcome": sum((r.get("replay", {}).get("rc") == 0) == ok(r, "gold") for r in rows),
        "replay_equals_gold_test_counts": sum(r.get("replay", {}).get("summary") == r.get("gold", {}).get("summary")
                                              and bool(r.get("gold", {}).get("summary")) for r in rows),
        "gold_differs_from_base_counts": sum(r.get("base", {}).get("summary") != r.get("gold", {}).get("summary") for r in rows),
        "replay_failed_to_build": sum(r.get("replay", {}).get("rc") == "replay_failed" for r in rows),
    }
    with open(path, "w") as f:
        json.dump({"summary": summary, "tasks": rows}, f, indent=1)


if __name__ == "__main__":
    main()
