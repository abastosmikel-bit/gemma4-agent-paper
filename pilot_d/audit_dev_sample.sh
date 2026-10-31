#!/usr/bin/env bash
# Gold-patch validity audit on a stratified sample of DEV tasks, both sandbox backends.
# Downloads snapshots to $KDATA (outside git). Writes verdicts to $OUT (outside git);
# only aggregate counts are copied into the repo.
set -euo pipefail
KDATA=${KDATA:-/tmp/kdata}; OUT=${OUT:-/tmp/work/val}; PY=${PY:-/tmp/hvenv/bin/python}
HERE=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$OUT"
IDS=$(python3 -I - "$KDATA/tasks.jsonl" <<'PY'
import json, sys
rows=[json.loads(l) for l in open(sys.argv[1])]
by={}
for r in rows: by.setdefault(r['repo'],[]).append(r['instance_id'])
pick=[]
for repo,ids in sorted(by.items()):
    ids=sorted(ids); n={'psf/requests':99,'encode/httpx':99,'Textualize/rich':12,'fastapi/fastapi':10}[repo]
    step=max(1,len(ids)//n) if len(ids)>n else 1
    pick+=ids[::step][:n]
print(' '.join(pick))
PY
)
FILES=""; for i in $IDS; do [ -f "$KDATA/snapshots/$i.tgz" ] || FILES="$FILES snapshots/$i.tgz"; done
[ -n "$FILES" ] && python3 -I "$HERE/common/kaggle_fetch.py" "$KDATA" $FILES | awk '{print $1}' | sort | uniq -c
for B in subprocess docker; do
  "$PY" "$HERE/common/validate.py" --tasks "$KDATA/tasks.jsonl" --snapshots "$KDATA/snapshots" \
     --backend $B --ids $IDS --out "$OUT/dev_audit_$B.jsonl" --logs "$OUT/logs" --concurrency 3 >/dev/null 2>&1
done
echo done
