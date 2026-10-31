#!/usr/bin/env bash
# Graph fidelity vs released graphs on dev commits whose snapshots are already downloaded.
# Prints one JSON line per commit (aggregate metrics only; no ids).
set -euo pipefail
KDATA=${KDATA:-/tmp/kdata}; PY=${PY:-/tmp/hvenv/bin/python}; HERE=$(cd "$(dirname "$0")/.." && pwd)
W=$(mktemp -d)
python3 -I - "$KDATA" "$@" > "$W/picks.txt" <<'PY'
import json, sys
kd, want = sys.argv[1], sys.argv[2:]
for l in open(f"{kd}/tasks.jsonl"):
    r = json.loads(l)
    if r["instance_id"] in want:
        print(r["instance_id"], r["repo"].split("/")[1].lower(), r["base_commit"])
PY
while read iid short bc; do
  [ -f "$KDATA/graphs/${short}_$bc.json" ] || python3 -I "$HERE/common/kaggle_fetch.py" "$KDATA" "graphs/${short}_$bc.json" >/dev/null
  mkdir -p "$W/$iid" && tar xzf "$KDATA/snapshots/$iid.tgz" -C "$W/$iid"
  out=$("$PY" "$HERE/common/graph_build.py" build "$W/$iid" "$short" "$bc" "$W/g" | tail -1)
  echo "$short $("$PY" "$HERE/common/graph_build.py" fidelity "$out" "$KDATA/graphs/${short}_$bc.json")"
  rm -rf "$W/$iid"
done < "$W/picks.txt"
rm -rf "$W"
