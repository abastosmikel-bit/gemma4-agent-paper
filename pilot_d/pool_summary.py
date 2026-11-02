"""Summarise the local held-out pool build into results/heldout_pool_local.json (our own tasks only, no task content).

Inputs (outside git): POOL dir (tasks/meta/val_*.jsonl), EXPORT dir (Level A + heldout_meta.jsonl), the list of task ids
for which pilot C's probe.build_probe_record returned ok, and optionally a prompt-parity result.
Usage: python -I pilot_d/pool_summary.py POOL EXPORT PROBE_OK.json OUT.json [--parity PARITY.json] [--val-override F.jsonl ...]
"""
import argparse
import collections
import json
from pathlib import Path


def jl(p):
    return [json.loads(l) for l in open(p)] if Path(p).exists() else []


def reason(v):
    if v["valid"]:
        return "valid"
    if v.get("base_resolved"):
        return "empty_patch_passes"
    if v.get("gold_resolved") is None:
        return "setup_error"
    return "gold_fails"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("pool"); p.add_argument("export"); p.add_argument("probe_ok"); p.add_argument("out")
    p.add_argument("--parity"); p.add_argument("--val-override", nargs="*", default=[])
    p.add_argument("--dropped", default="pilot_d/manifest.json")
    a = p.parse_args()
    P, E = Path(a.pool), Path(a.export)
    val = {v["instance_id"]: v for v in jl(P / "val_subprocess.jsonl")}
    for f in a.val_override:  # later validations (e.g. after declaring a missing test dependency) replace earlier ones
        val.update({v["instance_id"]: v for v in jl(f)})
    meta = {m["instance_id"]: m for m in jl(E / "heldout_meta.jsonl")}
    ok = set(json.load(open(a.probe_ok)))
    dropped = json.load(open(a.dropped)).get("dropped_repos", {})
    by = collections.defaultdict(collections.Counter)
    for v in val.values():
        by[v["repo"]][reason(v)] += 1
    pool = []
    for i, m in meta.items():
        v = val[i]
        pool.append({"instance_id": i, "repo": v["repo"], "probe_ready": i in ok,
                     "issue_linked_local": bool(m["issue_refs"]), "hang_bug": v.get("base_exit") == 124,
                     "n_f2p": len(m["FAIL_TO_PASS"]), "gold_nodes": len(m["gold_nodes"]),
                     "repro_verified": (m.get("repro_test") or {}).get("verified")})
    usable = [r for r in pool if r["probe_ready"] and r["issue_linked_local"] and not r["hang_bug"]]
    out = {
        "what": "local subprocess-sandbox validation of the held-out pool (host env = harness deps + declared test deps); "
                "probe readiness from pilot C's own build_gold/eligible/build_probe_record, unmodified",
        "built_by_repo": {r: dict(c) for r, c in sorted(by.items())},
        "dropped_repos": dropped,
        "exported_valid": len(meta),
        "probe_ready": sum(r["probe_ready"] for r in pool),
        "probe_ready_by_repo": dict(collections.Counter(r["repo"] for r in pool if r["probe_ready"])),
        "usable_for_D1_D2_now": {"n": len(usable), "by_repo": dict(collections.Counter(r["repo"] for r in usable)),
                                 "rule": "probe-ready + issue reference found in git + no 300 s hang; the GitHub API "
                                         "step in D0 can only add issue links"},
        "repro_verified_of_exported": sum(1 for r in pool if r["repro_verified"]),
        "prompt_parity": json.load(open(a.parity))["aggregate"] if a.parity else None,
        "tasks": sorted(pool, key=lambda r: r["instance_id"]),
    }
    Path(a.out).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("built_by_repo", "exported_valid", "probe_ready", "probe_ready_by_repo",
                                          "usable_for_D1_D2_now")}, indent=1))


if __name__ == "__main__":
    main()
