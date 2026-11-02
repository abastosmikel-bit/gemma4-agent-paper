"""Run pilot C's OWN probe code, unmodified, on a pilot D export (format compatibility, docs/PROBE_INPUT.md).

Steps:
  1. pilot_c/build_gold.py (run separately) → GOLD.json
  2. this script: pilot_c.select_tasks.eligible (its dev-repo filter neutralised; every other rule as C applies it),
     then pilot_c.probe.build_probe_record per eligible task; counts the reasons; compares with pilot D's mirror
     (heldout_meta.jsonl "probe.eligible").
Usage:
  python -I PC/pilot_c/build_gold.py --tasks EXPORT/tasks.jsonl --snapshots EXPORT/snapshots --out GOLD.json   (cwd=PC)
  python -I pilot_d/c_compat.py PC GOLD.json EXPORT OUT_OK_IDS.json
where PC is a checkout of pilot/c-bottleneck.
"""
import collections
import json
import sys

PC, GOLD, EXPORT, OUT = sys.argv[1:5]
sys.path.insert(0, PC)
from pilot_c import probe as pb  # noqa: E402
from pilot_c.select_tasks import eligible  # noqa: E402

G = json.load(open(GOLD))
G = G.get("tasks", G) if isinstance(G, dict) else {g["instance_id"]: g for g in G}
tasks = {json.loads(l)["instance_id"]: json.loads(l) for l in open(f"{EXPORT}/tasks.jsonl")}
mine = {json.loads(l)["instance_id"]: json.loads(l)["probe"]["eligible"] for l in open(f"{EXPORT}/heldout_meta.jsonl")}
reasons, agree, ok_ids, n_elig = collections.Counter(), 0, [], 0
for iid, t in tasks.items():
    g = G[iid]
    e = eligible({**g, "repo": "fastapi/fastapi"})  # C's repo filter lists dev repos only
    n_elig += e
    agree += (e == mine[iid])
    if not e:
        reasons["not eligible (C rule)"] += 1
        continue
    rec, why = pb.build_probe_record(t, g, f"{EXPORT}/snapshots/{iid}.tgz")
    reasons[why] += 1
    if rec:
        ok_ids.append(iid)
print(json.dumps({"tasks": len(tasks), "C_eligible": n_elig, "pilot_D_mirror_agrees": f"{agree}/{len(tasks)}",
                  "build_probe_record": dict(reasons)}))
json.dump(sorted(ok_ids), open(OUT, "w"))
