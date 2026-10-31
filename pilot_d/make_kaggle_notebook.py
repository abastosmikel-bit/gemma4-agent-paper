"""Generate notebooks/pilot_d_kaggle_cpu.ipynb, a CPU-only Kaggle notebook (no GPU quota).

Part A (instrument check): gold-patch validity of ALL dev tasks inside the real Kaggle image,
        subprocess backend, host env = Kaggle image + starter wheelhouse (exactly the starter's setup).
Part B (held-out): rebuild the pilot's held-out tasks from public GitHub (manifest), fetch issue
        text from the GitHub API, install declared test deps, then validate, map F2P/P2P, annotate,
        and build graphs. Needs Internet ON (Settings, Internet); Part A does not.
Outputs in /kaggle/working:
  pilot_d_summary.json                      aggregates only (safe to commit to results/)
  dev_audit_per_task_DO_NOT_COMMIT.jsonl    contains competition task ids: never commit
  heldout/                                  our own tasks (tasks.jsonl, snapshots, graphs, annotations)

The repo is private, so the code is embedded via %%writefile cells. Regenerate after code changes:
  python pilot_d/make_kaggle_notebook.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["common/__init__.py", "common/kaggle_fetch.py", "common/mining.py", "common/snapshot.py",
         "common/validate.py", "common/testmap.py", "common/annotate.py", "common/graph_build.py",
         "common/github_text.py", "common/export_swebench.py", "pilot_d/__init__.py", "pilot_d/build_tasks.py",
         "pilot_d/manifest.json", "pilot_d/env/sqlglot.txt", "pilot_d/env/networkx.txt"]
CGL = "git+https://github.com/danielmantiglia/codegraph-loc@1e8e0abbb97a1f78648cb12890fd700712b00623"


def md(s):
    return {"cell_type": "markdown", "metadata": {}, "source": s}


def code(s):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s}


cells = [md("# Pilot D: harness-faithful validation on Kaggle (CPU only)\n"
            "Runs on **CPU**; uses no GPU quota and makes no submission. Part A needs only the competition data and the "
            "`metric/gemma-4-developer-agent-wheelhouse` dataset. Part B needs **Internet ON**.\n\n"
            "Commit only `pilot_d_summary.json`. Never commit `*_DO_NOT_COMMIT*` files.")]
cells.append(code("""import glob, os, shutil, subprocess, sys, json, time
from pathlib import Path
DATA_DIR = Path('/kaggle/input/competitions/gemma-4-developer-agent')
WHEELHOUSE_DIR = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
W = Path('/kaggle/working'); W.mkdir(exist_ok=True)
# Same host setup as the official starter notebook (so the subprocess sandbox inherits the same site-packages)
for pth in glob.glob('/usr/local/lib/python*/dist-packages/*cutlass*.pth') + glob.glob('/usr/local/lib/python*/site-packages/*cutlass*.pth'):
    try: os.unlink(pth)
    except OSError: pass
tmp_whl = Path('/tmp/wheelhouse'); tmp_whl.mkdir(parents=True, exist_ok=True)
for w in WHEELHOUSE_DIR.glob('*.whl'):
    if 'cutlass' in w.name.lower(): continue
    t = tmp_whl / (w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name)
    if not t.exists():
        try: os.symlink(w, t)
        except OSError: shutil.copyfile(w, t)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', *sorted(map(str, tmp_whl.glob('*.whl')))], check=True)
print(sys.version)
import swegemma; print('swegemma', swegemma.__file__)"""))
for f in FILES:
    p = ROOT / f
    content = p.read_text() if p.exists() else ""
    cells.append(code(f"import os; os.makedirs('/kaggle/working/pd/{Path(f).parent}', exist_ok=True)\n"
                      f"open('/kaggle/working/pd/{f}', 'w').write({content!r}); print('wrote {f}')"))
cells.append(md("## Part A: gold-patch validity of all dev tasks (real Kaggle host env)\n"
                "Expected runtime about 30–60 min on 4 CPUs. Per task: empty patch must fail, gold patch must pass."))
cells.append(code("""os.chdir('/kaggle/working/pd')
t0 = time.time()
r = subprocess.run([sys.executable, 'common/validate.py', '--tasks', str(DATA_DIR/'tasks.jsonl'), '--snapshots', str(DATA_DIR/'snapshots'),
                    '--wheels', str(DATA_DIR/'wheels'), '--backend', 'subprocess', '--concurrency', '4',
                    '--out', str(W/'dev_audit_per_task_DO_NOT_COMMIT.jsonl')], capture_output=True, text=True)
print('minutes', round((time.time()-t0)/60, 1)); print(r.stderr[-2000:])
from collections import Counter, defaultdict
rows = [json.loads(l) for l in open(W/'dev_audit_per_task_DO_NOT_COMMIT.jsonl')]
agg = defaultdict(Counter)
for x in rows:
    k = 'valid' if x['valid'] else ('empty_patch_already_passes' if x.get('base_resolved') else ('setup_error' if x.get('gold_resolved') is None else 'gold_patch_fails'))
    agg[x['repo']][k] += 1
symptoms = Counter((x['repo'], x.get('gold_symptom') or x.get('gold_error', '')[:60]) for x in rows if not x['valid'])
summary = {'part_A_dev_audit': {r_: dict(c) for r_, c in agg.items()},
           'part_A_failure_symptoms': [[a, b, n] for (a, b), n in symptoms.most_common(20)],
           'python': sys.version.split()[0]}
json.dump(summary, open(W/'pilot_d_summary.json', 'w'), indent=1); print(json.dumps(summary, indent=1))"""))
cells.append(md("## Part B: rebuild and validate the held-out pilot tasks (Internet ON)"))
cells.append(code(f"""os.chdir('/kaggle/working/pd')
man = json.load(open('pilot_d/manifest.json'))
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '{CGL}'], check=True)
# Install declared test deps ONLY if missing (pinning would downgrade the Kaggle image's numpy/pandas); record versions used
import importlib, importlib.metadata as md
used = {{}}
for env in ('pilot_d/env/sqlglot.txt', 'pilot_d/env/networkx.txt'):
    for line in open(env):
        line = line.split('#')[0].strip()
        if not line: continue
        dist = line.split('==')[0]; mod = {{'python-dateutil': 'dateutil'}}.get(dist, dist)
        try: importlib.import_module(mod)
        except ImportError: subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', line], check=True)
        used[dist] = md.version(dist)
print('test deps used:', used)
H = W/'heldout'; H.mkdir(exist_ok=True)
for repo in man['repos']:
    d = Path('/kaggle/working/src')/repo['short']
    if not d.exists():
        subprocess.run(['git', 'clone', '-q', f"--shallow-since={{man['clone_shallow_since']}}", repo['url'], str(d)], check=True)
    subprocess.run([sys.executable, 'common/mining.py', str(d), '--repo', repo['repo'], '--pkg', repo['pkg'], '--since', man['since'],
                    '--out', str(H/f"cand_{{repo['short']}}.jsonl"), '--funnel', str(H/f"funnel_{{repo['short']}}.json")], check=True)
    subprocess.run([sys.executable, 'pilot_d/build_tasks.py', str(H/f"cand_{{repo['short']}}.jsonl"), str(d), str(H), '--ids', *repo['instance_ids']], check=True)
subprocess.run([sys.executable, 'common/github_text.py', str(H/'tasks.jsonl'), str(H/'meta.jsonl'), str(H/'tasks_text.jsonl'), str(H/'meta_text.jsonl')], check=True)
for step in (['common/validate.py', '--tasks', str(H/'tasks_text.jsonl'), '--snapshots', str(H/'snapshots'), '--backend', 'subprocess', '--out', str(H/'val_kaggle.jsonl')],
             ['common/testmap.py', '--tasks', str(H/'tasks_text.jsonl'), '--snapshots', str(H/'snapshots'), '--out', str(H/'testmap.jsonl')]):
    subprocess.run([sys.executable, *step], check=True)
tm = {{json.loads(l)['instance_id']: json.loads(l) for l in open(H/'testmap.jsonl')}}
with open(H/'tasks_final.jsonl', 'w') as out:
    for l in open(H/'tasks_text.jsonl'):
        t = json.loads(l); t['FAIL_TO_PASS'] = tm[t['instance_id']]['FAIL_TO_PASS']; t['PASS_TO_PASS'] = tm[t['instance_id']]['PASS_TO_PASS']; out.write(json.dumps(t)+'\\n')
subprocess.run([sys.executable, 'common/annotate.py', '--tasks', str(H/'tasks_final.jsonl'), '--snapshots', str(H/'snapshots'),
                '--testmap', str(H/'testmap.jsonl'), '--out', str(H/'annotations.jsonl'), '--verify'], check=True)
import tarfile, tempfile
for l in open(H/'tasks_final.jsonl'):
    t = json.loads(l); short = t['repo'].split('/')[1].lower()
    with tempfile.TemporaryDirectory() as td:
        tarfile.open(H/'snapshots'/f"{{t['instance_id']}}.tgz").extractall(td, filter='data')
        subprocess.run([sys.executable, 'common/graph_build.py', 'build', td, short, t['base_commit'], str(H/'graphs')], check=True)
val = [json.loads(l) for l in open(H/'val_kaggle.jsonl')]
ann = [json.loads(l) for l in open(H/'annotations.jsonl')]
meta = [json.loads(l) for l in open(H/'meta_text.jsonl')]
summary = json.load(open(W/'pilot_d_summary.json'))
summary['part_B_heldout'] = {{'tasks': len(val), 'valid_kaggle_subprocess': sum(v['valid'] for v in val),
    'per_task': [{{k: v.get(k) for k in ('instance_id', 'valid', 'base_resolved', 'gold_resolved', 'gold_symptom')}} for v in val],
    'repro_verified': sum(1 for a in ann if a.get('repro_test', {{}}).get('verified')),
    'problem_statement_source': Counter((m.get('problem_statement_source') or 'pending').split('#')[0] for m in meta),
    'test_deps_used': used}}
json.dump(summary, open(W/'pilot_d_summary.json', 'w'), indent=1); print(json.dumps(summary['part_B_heldout'], indent=1))"""))

nb = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                   "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
out = ROOT / "notebooks" / "pilot_d_kaggle_cpu.ipynb"
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(nb, indent=1))
print("wrote", out, len(cells), "cells")
