#!/usr/bin/env bash
# LOCAL papermill dry run of notebooks/D0a_heldout_fetch__CPU.ipynb (online, like Kaggle with Internet ON), in a stand-in
# for the starter image (/tmp/kimg_a: py3.12 + torch + harness deps, WITHOUT sentence-transformers/pytest/duckdb/...).
set -euo pipefail
R=/home/user/gemma4-agent-paper
rm -rf /kaggle && mkdir -p /kaggle/input /kaggle/working /tmp/d0a && rm -rf /tmp/d0a/*
/tmp/kimg_a/bin/python -m ipykernel install --user --name kimg_a >/dev/null 2>&1
D0A_DRYRUN=1 D0_DRYRUN_REPOS=pyparsing,tomlkit /tmp/kimg_a/bin/python -m papermill -k kimg_a --log-output \
  $R/notebooks/D0a_heldout_fetch__CPU.ipynb /tmp/work/D0a_dryrun_out.ipynb > /tmp/work/D0a_dryrun.log 2>&1
/tmp/kimg_a/bin/python - <<'PY'
import json, hashlib
from pathlib import Path
O = Path('/kaggle/working/d0a'); M = json.load(open(O / 'D0A_MANIFEST.json')); s = M['summary']
bad = [f for f, v in M['files'].items() if hashlib.sha256((O / f).read_bytes()).hexdigest() != v['sha256']]
wheels = sorted(p.name for p in (O / 'wheels').glob('*.whl'))
checks = {
  'built > 0': s['built'] > 0,
  'snapshots for every task': len(list((O / 'pool' / 'snapshots').glob('*.tgz'))) == s['built'],
  'codegraph-loc wheel': any(w.startswith('codegraph_loc-') for w in wheels),
  'sentence-transformers wheel': any(w.startswith('sentence_transformers-') for w in wheels),
  'pytest wheel (missing in image)': any(w.startswith('pytest-') for w in wheels),
  'model safetensors': (O / 'models' / 'bge-small-en-v1.5' / 'model.safetensors').exists(),
  'export wheels py3.12 + py3.13': any('cp312' in w.name for w in (O / 'export_wheels').glob('*.whl')) and any('cp313' in w.name for w in (O / 'export_wheels').glob('*.whl')),
  'manifest sha256 all match': not bad,
  'under 500 output files': s['n_files'] < 500,
}
print(json.dumps({k: s[k] for k in ('built', 'need', 'n_files', 'gigabytes', 'minutes')}), len(wheels), 'wheels')
for k, v in checks.items(): print(('PASS ' if v else 'FAIL ') + k)
assert all(checks.values())
PY
grep -q "offline embedding ok" /tmp/work/D0a_dryrun.log && echo "PASS offline self-check (embedding from local wheels + local model)"
