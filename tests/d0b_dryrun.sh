#!/usr/bin/env bash
# LOCAL papermill dry run of notebooks/D0b_heldout_export__CPU.ipynb with the network BLOCKED: it runs inside a new network
# namespace (no route to anything but loopback) and a sitecustomize guard logs any non-loopback connection or DNS lookup.
# Inputs where Kaggle mounts them: competition, wheelhouse dataset, and D0a's output (from the D0a dry run).
set -euo pipefail
R=/home/user/gemma4-agent-paper; S=$(cd "$(dirname "$0")" && pwd)
[ -f /kaggle/working/d0a/D0A_MANIFEST.json ] || { echo "run the D0a dry run first"; exit 2; }
rm -rf /tmp/d0a_out && mv /kaggle/working/d0a /tmp/d0a_out
rm -rf /kaggle /tmp/d0b && mkdir -p /kaggle/input/competitions /kaggle/input/datasets/metric /kaggle/input/d0a-heldout-fetch-cpu /kaggle/working
ln -s /tmp/kdata /kaggle/input/competitions/gemma-4-developer-agent
ln -s /tmp/fakewh /kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse
cp -r /tmp/d0a_out /kaggle/input/d0a-heldout-fetch-cpu/d0a && chmod -R a-w /kaggle/input/d0a-heldout-fetch-cpu
/tmp/kimg_b/bin/python -m ipykernel install --user --name kimg_b >/dev/null 2>&1
rm -f /tmp/net_guard.log
unshare -n bash -c "
  python3 $S/lo_up.py
  if curl -s -m 5 -o /dev/null https://pypi.org/simple/; then echo 'NETWORK NOT BLOCKED'; exit 3; else echo 'outbound blocked inside the namespace (curl to pypi.org fails)'; fi
  PYTHONPATH=$S/netguard NET_GUARD_LOG=/tmp/net_guard.log /tmp/kimg_b/bin/python -m papermill -k kimg_b --log-output \
    $R/notebooks/D0b_heldout_export__CPU.ipynb /tmp/work/D0b_dryrun_out.ipynb > /tmp/work/D0b_dryrun.log 2>&1
"
/tmp/kimg_b/bin/python - <<'PY'
import json, os
s = json.load(open('/kaggle/working/D0_summary.json')); e = s['export']; pp = s['prompt_parity']
attempts = open('/tmp/net_guard.log').read().splitlines() if os.path.exists('/tmp/net_guard.log') else []
checks = {
  'built == D0a built': s['built'] == s['d0a']['built'],
  'valid > 0': s['valid_kaggle'] > 0,
  'exported == valid': e['tasks'] == s['valid_kaggle'],
  'layout: heldout_export/{tasks.jsonl,heldout_meta.jsonl,EXPORT.json,snapshots,graphs,embeddings,wheels}': all(
      os.path.exists(f'/kaggle/working/heldout_export/{p}') for p in ('tasks.jsonl', 'heldout_meta.jsonl', 'EXPORT.json', 'snapshots', 'graphs', 'embeddings', 'wheels')),
  'graph section on every exported task': pp['section_present_with_embeddings'] == pp['tasks'] == e['tasks'],
  'section absent without embeddings (control)': pp['section_present_without_embeddings'] == 0,
  'graph tools answer': pp['search_similar_code_ok'] > 0 and pp['get_code_neighbors_ok'] > 0,
  'embeddings from the local model': (e.get('embeddings') or {}).get('model') == 'bge',
  'test wheels copied into the export': len(e['test_dep_wheels']) > 0,
  'ZERO network attempts logged by the guard': not attempts,
}
print(json.dumps({'built': s['built'], 'valid': s['valid_kaggle'], 'by_repo': s['by_repo'], 'guard_attempts': len(attempts)}))
for a in attempts[:5]: print('  attempt:', a)
for k, v in checks.items(): print(('PASS ' if v else 'FAIL ') + k)
assert all(checks.values())
PY
