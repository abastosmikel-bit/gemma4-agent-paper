"""Select the pilot tasks (instance IDs only are written; safe to commit).

Rule (fixed before any agent run):
  eligible = exactly 1 changed source file that already exists at base_commit,
             1-2 enclosing functions/classes (function-level oracle well defined),
             gold patch <= 40 changed lines, >= 1 scorer-required test name,
             repo in {fastapi, rich, requests},
             and the GOLD patch resolves the task in the sandbox (gold check JSON, if given)
  pilot15  = stratified random sample: fastapi 7, rich 6, requests 2 (seeded)
  reserve  = next 4 per repo from the same shuffled order (replace tasks whose gold
             patch fails the CPU gold check)
  smoke3   = first pilot task of each repo (used for the smoke test and size timing)

usage: python -I pilot_c/select_tasks.py <gold_all.json> <out task_ids.json> [gold_check.json ...]
"""
import json
import random
import sys

SEED = 20261031
QUOTA = {"fastapi/fastapi": 7, "Textualize/rich": 6, "psf/requests": 2}
RESERVE = 4


def eligible(g):
    return (len(g["src_files"]) == 1 and not g["new_src_files"] and 1 <= len(g["functions"]) <= 2
            and g["gold_added"] + g["gold_removed"] <= 40 and len(g["test_names"]) >= 1 and g["repo"] in QUOTA)


def main():
    G = json.load(open(sys.argv[1]))
    checks = {}
    for path in sys.argv[3:]:
        for r in json.load(open(path))["rows"]:
            checks[r["instance_id"]] = bool(r["gold_resolved"])
    if checks:
        G = {i: g for i, g in G.items() if checks.get(i) is True}
    rng = random.Random(SEED)
    pilot, reserve, smoke, pool_sizes = [], [], [], {}
    for repo, k in QUOTA.items():
        pool = sorted(i for i, g in G.items() if g["repo"] == repo and eligible(g))
        pool_sizes[repo] = len(pool)
        rng.shuffle(pool)
        pilot += pool[:k]
        reserve += pool[k:k + RESERVE]
        smoke.append(pool[0])
    out = {"seed": SEED, "gold_check_sources": sys.argv[3:], "n_gold_checked": len(checks), "rule": __doc__.split("Rule (fixed before any agent run):")[1].split("usage:")[0].strip(),
           "eligible_pool_sizes": pool_sizes, "pilot15": pilot, "reserve": reserve, "smoke3": smoke}
    json.dump(out, open(sys.argv[2], "w"), indent=1)
    print(json.dumps({k: out[k] for k in ("eligible_pool_sizes", "smoke3")}), len(pilot), len(reserve))


if __name__ == "__main__":
    main()
