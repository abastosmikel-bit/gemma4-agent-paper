"""Predict the D1/D2 task set before any GPU session, from numbers already committed (no task data needed).

The frozen rule (docs/D_SPECS.md rules 1-6, pilot_c/heldout.py) needs, per task: validity, statement source, C's probe
record (rule 2), the no-patch hang (rule 4) and the graph size (rule 6). This replays it from
  - D0b's summary (results/D0b_summary.json: the valid task ids and each one's problem_statement_source), and
  - pilot D's local per-task flags (results/heldout_pool_local.json on pilot/d-heldout: C's unmodified build_probe_record
    ok, graph nodes, hang), computed on the same task ids,
then runs the frozen sampler (heldout.select). D1 and D2 recompute the selection from the real export on Kaggle; their
D_selection.json is authoritative. This prediction lets the coordinator check the task set before spending GPU.
Usage: python -m pilot_c.predict_d_selection <D0b_summary.json> <heldout_pool_local.json> <out.json>
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

from pilot_c import heldout as ho


def predict(summary: dict, local: dict, n: int = 24) -> dict:
    loc = {t["instance_id"]: t for t in local["tasks"]}
    src = summary["issue_text"]                       # valid task id -> problem_statement_source
    valid = set(src)
    why: dict[str, str] = {}
    pool = []
    for i in sorted(valid):
        t = loc.get(i)
        if t is None:
            why[i] = "no local flags (task not in pilot D's local pool)"
        elif t["repo"] in ho.EXCLUDE_REPOS:
            why[i] = "excluded repo"
        elif not src[i].startswith("issue#"):
            why[i] = "statement not from an issue (" + src[i].split("#")[0] + ")"
        elif i in ho.HANG_IDS or t.get("hang_bug"):
            why[i] = "300 s hang without a patch"
        elif (t.get("graph_nodes") or 10 ** 9) > ho.MAX_NODES:
            why[i] = f"graph > {ho.MAX_NODES} nodes"
        elif not t.get("probe_ready"):
            why[i] = "C's probe record not ok (not eligible, or the edit is outside the 150-line read window)"
        else:
            pool.append(i)
    repo_of = {i: loc[i]["repo"] for i in loc}
    sel = ho.select(pool, repo_of, n)
    return {"what": "PREDICTED D1/D2 selection (docs/D_SPECS.md rules 1-6, pilot_c/heldout.py); D1/D2 recompute it on Kaggle",
            "inputs": {"validity_and_statement_source": "D0b summary (Kaggle, offline)",
                       "probe_ready_graph_nodes_hang": "pilot D local flags (results/heldout_pool_local.json, pilot/d-heldout)"},
            "valid": len(valid), "local_flags_same_ids": valid == set(loc),
            "statement_source_valid": dict(collections.Counter(v.split("#")[0] for v in src.values())),
            "excluded": dict(collections.Counter(why.values())), "excluded_ids": why,
            "hang_tasks_local": sorted(i for i, t in loc.items() if t.get("hang_bug")), **sel,
            "selected_issue": {i: src[i] for i in sel["selected"]}}


def main(summary_path: str, local_path: str, out_path: str) -> dict:
    P = predict(json.loads(Path(summary_path).read_text()), json.loads(Path(local_path).read_text()))
    Path(out_path).write_text(json.dumps(P, indent=1))
    print(json.dumps({k: P[k] for k in ("valid", "local_flags_same_ids", "excluded", "pool_by_repo", "selected_by_repo")}, indent=1))
    return P


if __name__ == "__main__":
    main(*sys.argv[1:4])
