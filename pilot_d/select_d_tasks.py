"""Select the D1/D2 task set from a D0 export, by the rule frozen in docs/D_SPECS.md (paper/main).

Pool rules (all must hold):
  1 valid in the export's validation file;  2 id in PROBE_OK (ids for which pilot C's probe.build_probe_record is ok);
  3 problem statement from a real issue (heldout_meta problem_statement_source startswith "issue#"; with
    --allow-git-issue-refs a git issue reference is accepted instead, for local dry runs without issue text);
  4 no 300 s hang in the no-patch run;  5 >= 2 pool tasks in the same repo;  6 graph <= 20,000 nodes.
Selection: seeded (20261102) repo-stratified random sample, N (default 24), at most N//2 per repo, >= 3 repos.
Output: JSON with the selected instance ids (our own task ids; safe to commit) and the pool counts.

Usage: python -I pilot_d/select_d_tasks.py EXPORT_DIR VALIDATION.jsonl PROBE_OK.json OUT.json [--n 24] [--allow-git-issue-refs]
"""
import argparse
import collections
import json
import random
from pathlib import Path

SEED = 20261102
MAX_NODES = 20000


def main():
    p = argparse.ArgumentParser()
    p.add_argument("export"); p.add_argument("validation"); p.add_argument("probe_ok"); p.add_argument("out")
    p.add_argument("--n", type=int, default=24)
    p.add_argument("--allow-git-issue-refs", action="store_true")
    a = p.parse_args()
    E = Path(a.export)
    tasks = {json.loads(l)["instance_id"]: json.loads(l) for l in open(E / "tasks.jsonl")}
    meta = {json.loads(l)["instance_id"]: json.loads(l) for l in open(E / "heldout_meta.jsonl")}
    val = {json.loads(l)["instance_id"]: json.loads(l) for l in open(a.validation)}
    ok = set(json.load(open(a.probe_ok)))

    def issue(i):
        src = (meta[i].get("problem_statement_source") or "")
        return src.startswith("issue#") or (a.allow_git_issue_refs and bool(meta[i].get("issue_refs")))

    def nodes(i):
        t = tasks[i]
        g = E / "graphs" / f"{t['repo'].split('/')[1]}_{t['base_commit']}.json"
        return len(json.load(open(g))["nodes"]) if g.exists() else 10 ** 9

    pool = [i for i in sorted(tasks) if val.get(i, {}).get("valid") and i in ok and issue(i)
            and val[i].get("base_exit") != 124 and nodes(i) <= MAX_NODES]
    by = collections.defaultdict(list)
    for i in pool:
        by[tasks[i]["repo"]].append(i)
    by = {r: ids for r, ids in by.items() if len(ids) >= 2}           # rule 5
    rng = random.Random(SEED)
    for r in sorted(by):
        rng.shuffle(by[r])
    cap = a.n // 2
    chosen, repos = [], sorted(by, key=lambda r: (-len(by[r]), r))
    while len(chosen) < a.n and any(by[r] for r in repos):            # round-robin over repos, respecting the cap
        for r in repos:
            if by[r] and sum(tasks[c]["repo"] == r for c in chosen) < cap and len(chosen) < a.n:
                chosen.append(by[r].pop(0))
        if all(not by[r] or sum(tasks[c]["repo"] == r for c in chosen) >= cap for r in repos):
            break
    out = {"rule": "docs/D_SPECS.md (paper/main) v1", "seed": SEED, "n_target": a.n, "cap_per_repo": cap,
           "pool": len(pool), "pool_by_repo": dict(collections.Counter(tasks[i]["repo"] for i in pool)),
           "selected": sorted(chosen), "selected_by_repo": dict(collections.Counter(tasks[i]["repo"] for i in chosen)),
           "n_repos": len({tasks[i]["repo"] for i in chosen}), "issue_rule": "git refs (dry run)" if a.allow_git_issue_refs else "issue text"}
    if out["n_repos"] < 3:
        out["warning"] = "fewer than 3 repos: the spec requires >= 3"
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "selected"}, indent=1))


if __name__ == "__main__":
    main()
