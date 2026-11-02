"""Generate pilot D's Kaggle notebooks (naming rule: DECISIONS 2026-10-31 on paper/main).

Kaggle refuses Internet for a notebook with this competition attached, even on CPU. So the export is split:
  notebooks/D0a_heldout_fetch__CPU.ipynb   Internet ON, NO competition data: fetch everything external into
                                           /kaggle/working/d0a/ (pool + snapshots + issue text, wheels, model files).
  notebooks/D0b_heldout_export__CPU.ipynb  Internet OFF, competition attached, D0a's output attached: install with
                                           --no-index only, validate, annotate, export. Output layout unchanged:
                                           /kaggle/working/heldout_export/ (docs/PROBE_INPUT.md Level A) + D0_summary.json.
The repo is private, so code files are embedded (written by the notebooks themselves). Regenerate after code changes:
  python pilot_d/build_notebooks.py
Every code cell is checked to parse; no cell is empty (papermill stops on an empty %%writefile, LEARNINGS 2026-10-31).
"""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILES = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "pilot_d" / "env").glob("*.txt"))
FILES_A = ["common/__init__.py", "common/mining.py", "common/snapshot.py", "common/github_text.py",
           "pilot_d/__init__.py", "pilot_d/build_tasks.py", "pilot_d/manifest.json"] + ENV_FILES
FILES_B = ["common/__init__.py", "common/validate.py", "common/testmap.py", "common/annotate.py", "common/graph_build.py",
           "common/embed_nodes.py", "pilot_d/__init__.py", "pilot_d/export_level_a.py", "pilot_d/check_prompt_parity.py",
           "pilot_d/manifest.json"] + ENV_FILES
CGL = "git+https://github.com/danielmantiglia/codegraph-loc@1e8e0abbb97a1f78648cb12890fd700712b00623"
ST = "sentence-transformers==6.2.0"          # version used for the local parity measurement
MODEL = "BAAI/bge-small-en-v1.5"
CPU_WHEELS = ("swegemma", "adk_eval_core", "adk_submission", "google_adk", "google_genai")  # LEARNINGS 2026-10-31
MODULE_OF = "{'python-dateutil': 'dateutil', 'pytest-timeout': 'pytest_timeout'}"

HEADER_A = """# D0a · held-out fetch (pilot D) · CPU · Internet ON

**What it does.** It downloads everything external that D0b needs, into `/kaggle/working/d0a/`:
1. **Task pool.** It clones the repos in `pilot_d/manifest.json` from public GitHub, mines them, and builds every
   task's snapshot (`pool/snapshots/<id>.tgz`, `pool/tasks.jsonl`, `pool/meta.jsonl`).
2. **Issue text** from the GitHub API, including issues linked through a PR body's "Fixes #N"
   (`pool/tasks_text.jsonl`, `pool/meta_text.jsonl`).
3. **Wheels for D0b's offline install** (`wheels/`):
   - the codegraph-loc wheel at the pinned commit;
   - every distribution that `pip install --dry-run` reports as missing in this image for sentence-transformers and the
     declared test dependencies (`need.txt`, exact pins).
4. **Test-only wheels** for Python 3.12 and 3.13, shipped inside the export (`export_wheels/`).
5. **The `BAAI/bge-small-en-v1.5` model files** (safetensors; no remote code) in `models/`.
6. **`D0A_MANIFEST.json`**, with sha256 per file.

Before finishing, it checks itself: it installs from its own `wheels/` with `--no-index` and embeds one string with the
model fully offline.

| | |
|---|---|
| Accelerator | **CPU** (no GPU quota) |
| Internet | **ON** (GitHub clone + API, PyPI, Hugging Face) |
| Environment | the official starter's **pinned environment (Python 3.12)**, the *same* one D0b uses, so the list of missing packages matches. Open the starter, Copy & Edit, **remove the competition input**, File → Import Notebook with this file, keep "Pin to original environment", Settings → Internet ON. The first code cell stops on any other Python. |
| Attach | nothing |
| Optional | Kaggle Secret `GITHUB_TOKEN`. Without it the GitHub API allows 60 requests/h, so ~150 requests wait for 2 hourly resets. |
| Expected run time | ≈ 1–3.5 h (build ≈ 40 min; issue text ≈ 5 min with a token, ≤ 3 h without; wheels and model ≈ 5 min) |
| Output | `/kaggle/working/d0a/` (≈ 7–9 GB, < 250 files). D0b attaches this notebook's output. Bring back `d0a/D0a_summary.json` → `results/` on pilot/d-heldout. |
"""

HEADER_B = """# D0b · held-out export (pilot D) · CPU · Internet OFF

**What it does.** It installs from D0a's local wheels only (`pip --no-index`), with no network. It validates every
task in this Kaggle image with the harness's own `verify_task` (gold patch must pass, empty patch must fail). It then
computes F2P/P2P, gold locations and verified reproduction tests, writes released-rule graphs and bge-small
embeddings, and exports `docs/PROBE_INPUT.md` (paper/main) **Level A**. The output layout is the same as the retired D0's.

| | |
|---|---|
| Accelerator | **CPU** (no GPU quota) |
| Internet | **OFF** (required: Kaggle refuses Internet with this competition attached). Everything external comes from D0a. |
| Environment | the official starter's **pinned environment (Python 3.12)**, the same as D0a. The first code cell stops on any other Python. |
| Attach | competition `gemma-4-developer-agent` · dataset `metric/gemma-4-developer-agent-wheelhouse` (harness wheels) · **the output of `notebooks/D0a_heldout_fetch__CPU.ipynb`** (found by its `D0A_MANIFEST.json`, wherever Kaggle mounts it under `/kaggle/input`) |
| Expected run time | ≈ 2–3 h (validation ≈ 30 min, F2P/annotation ≈ 1–1.5 h, graphs + embeddings ≈ 45 min) |
| Output | `/kaggle/working/heldout_export/` (Level A, read by D1/D2 as this notebook's output; do not commit) and `/kaggle/working/D0_summary.json` (aggregates + our own task ids; commit to `results/` on pilot/d-heldout). Scratch work stays in `/tmp`. |
"""


def md(s):
    return {"cell_type": "markdown", "metadata": {}, "source": s}


def code(s):
    assert s.strip(), "empty code cell"
    ast.parse(s)
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s}


def write_files(files, base):
    cells = []
    for f in files:
        content = (ROOT / f).read_text()
        cells.append(code(f"import os; os.makedirs('{base}/{Path(f).parent}', exist_ok=True)\n"
                          f"open('{base}/{f}', 'w').write({content!r}); print('wrote {f}')"))
    return cells


GUARD = """import sys
assert sys.version_info[:2] == (3, 12), f"Python {sys.version.split()[0]}: use the starter's pinned environment (3.12)"
print(sys.version)"""


def d0a() -> dict:
    cells = [md(HEADER_A), code(GUARD)]
    cells.append(code("""import glob, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path
OUT = Path('/kaggle/working/d0a'); TMP = Path('/tmp/d0a'); PD = TMP / 'pd'
for d in (OUT / 'pool', OUT / 'wheels', OUT / 'export_wheels', OUT / 'models', PD): d.mkdir(parents=True, exist_ok=True)
PIP = [sys.executable, '-m', 'pip']
DRY = os.environ.get('D0A_DRYRUN') == '1'   # local papermill dry run only: 2 tasks per repo, no GitHub API
t_start = time.time()"""))
    cells += write_files(FILES_A, "/tmp/d0a/pd")
    cells.append(md("## 1. Task pool: clone, mine, build snapshots (public GitHub)"))
    cells.append(code("""os.chdir(PD)
man = json.load(open('pilot_d/manifest.json'))
if DRY:
    keep = os.environ.get('D0_DRYRUN_REPOS')
    man['repos'] = [r for r in man['repos'] if not keep or r['short'] in keep.split(',')]
    for r in man['repos']: r['instance_ids'] = r['instance_ids'][:2]
    print('DRY RUN: 2 tasks per repo', [r['short'] for r in man['repos']])
P = OUT / 'pool'; t0 = time.time()
for repo in man['repos']:
    d = TMP / 'src' / repo['short']
    if not d.exists():
        subprocess.run(['git', 'clone', '-q', f"--shallow-since={man['clone_shallow_since']}", repo['url'], str(d)], check=True)
    cand = P / f"cand_{repo['short']}.jsonl"
    subprocess.run([sys.executable, 'common/mining.py', str(d), '--repo', repo['repo'], '--pkg', repo['pkg'],
                    '--since', man['since'], '--out', str(cand), '--funnel', str(P / f"funnel_{repo['short']}.json")], check=True)
    subprocess.run([sys.executable, 'pilot_d/build_tasks.py', str(cand), str(d), str(P), '--ids', *repo['instance_ids']], check=True)
n_built = sum(1 for _ in open(P / 'tasks.jsonl'))
print('built', n_built, 'of', sum(len(r['instance_ids']) for r in man['repos']), 'minutes', round((time.time() - t0) / 60, 1))"""))
    cells.append(md("## 2. Issue text (GitHub API; issue first, then an issue linked from the PR body, then the PR body)"))
    cells.append(code("""if DRY:  # the session that dry-runs this notebook cannot reach api.github.com
    shutil.copy(P / 'tasks.jsonl', P / 'tasks_text.jsonl'); shutil.copy(P / 'meta.jsonl', P / 'meta_text.jsonl')
else:
    subprocess.run([sys.executable, 'common/github_text.py', str(P / 'tasks.jsonl'), str(P / 'meta.jsonl'),
                    str(P / 'tasks_text.jsonl'), str(P / 'meta_text.jsonl')], check=True)
src = [json.loads(l).get('problem_statement_source', 'pending') for l in open(P / 'meta_text.jsonl')]
print({k: sum(s.split('#')[0] == k for s in src) for k in ('issue', 'pr_body', 'pending')})"""))
    cells.append(md("## 3. Wheels for D0b's offline install (exactly what this image lacks)"))
    cells.append(code(f"""MODULE_OF = {MODULE_OF}
missing = []
for env in sorted(glob.glob('pilot_d/env/*.txt')):
    for line in open(env):
        line = line.split('#')[0].strip()
        if line and importlib.util.find_spec(MODULE_OF.get(line.split('==')[0], line.split('==')[0])) is None:
            missing.append(line)
need = ['{ST}'] + missing
(OUT / 'need.txt').write_text('\\n'.join(need) + '\\n')
subprocess.run([*PIP, 'install', '--dry-run', '--quiet', '--report', str(TMP / 'report.json'), '-r', str(OUT / 'need.txt')], check=True)
pins = sorted({{f"{{i['metadata']['name']}}=={{i['metadata']['version']}}" for i in json.load(open(TMP / 'report.json'))['install']}})
for pin in pins:  # wheels only; build one from sdist if a project has no wheel
    if subprocess.run([*PIP, 'download', '-q', '--no-deps', '--only-binary=:all:', '-d', str(OUT / 'wheels'), pin]).returncode != 0:
        subprocess.run([*PIP, 'wheel', '-q', '--no-deps', '-w', str(OUT / 'wheels'), pin], check=True)
subprocess.run([*PIP, 'wheel', '-q', '--no-deps', '-w', str(OUT / 'wheels'), '{CGL}'], check=True)
for env in sorted(glob.glob('pilot_d/env/*.txt')):  # test-only wheels shipped inside the export (both sandbox Pythons)
    if not any(l.split('#')[0].strip() for l in open(env)): continue
    for pyv in ('3.12', '3.13'):
        subprocess.run([*PIP, 'download', '-q', '--no-deps', '-r', env, '--only-binary=:all:', '--python-version', pyv,
                        '--platform', 'manylinux2014_x86_64', '--platform', 'manylinux_2_17_x86_64',
                        '--platform', 'manylinux_2_28_x86_64', '-d', str(OUT / 'export_wheels')], check=True)
print('need:', need); print(len(pins), 'pinned distributions;', len(list((OUT / 'wheels').glob('*.whl'))), 'wheels')"""))
    cells.append(md("## 4. Model files, then a self-check: offline install from `wheels/` + offline embedding"))
    cells.append(code(f"""subprocess.run([*PIP, 'install', '-q', '--no-index', '--find-links', str(OUT / 'wheels'), '-r', str(OUT / 'need.txt')], check=True)
from huggingface_hub import snapshot_download
MD = OUT / 'models' / 'bge-small-en-v1.5'
snapshot_download('{MODEL}', local_dir=str(MD), allow_patterns=['*.json', '*.txt', 'model.safetensors', '1_Pooling/*'])
check = subprocess.run([sys.executable, '-c', (
    "import os; os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'\\n"
    "from sentence_transformers import SentenceTransformer\\n"
    f"m = SentenceTransformer('{{MD}}', trust_remote_code=False, device='cpu', model_kwargs={{{{'use_safetensors': True}}}})\\n"
    "v = m.encode(['def f(x): return x'], normalize_embeddings=True); print('offline embedding ok', v.shape)")],
    capture_output=True, text=True)
print(check.stdout.strip(), check.stderr[-500:]); assert 'offline embedding ok' in check.stdout"""))
    cells.append(md("## 5. Manifest (sha256 per file) and summary"))
    cells.append(code("""files = {}
for f in sorted(OUT.rglob('*')):
    if f.is_file() and f.name != 'D0A_MANIFEST.json':
        h = hashlib.sha256()
        with open(f, 'rb') as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b''): h.update(chunk)
        files[str(f.relative_to(OUT))] = {'sha256': h.hexdigest(), 'bytes': f.stat().st_size}
meta = [json.loads(l) for l in open(P / 'meta_text.jsonl')]
summary = {'version': 1, 'built': n_built, 'need': need, 'pinned_wheels': pins, 'dry_run': DRY,
           'by_repo': {r['repo']: sum(m['repo'] == r['repo'] for m in meta) for r in man['repos']},
           'problem_statement_source': {k: sum((m.get('problem_statement_source') or 'pending').split('#')[0] == k for m in meta)
                                        for k in ('issue', 'pr_body', 'pending')},
           'n_files': len(files) + 2, 'gigabytes': round(sum(v['bytes'] for v in files.values()) / 1e9, 2),
           'minutes': round((time.time() - t_start) / 60, 1)}
json.dump({'files': files, 'summary': summary}, open(OUT / 'D0A_MANIFEST.json', 'w'))
json.dump(summary, open(OUT / 'D0a_summary.json', 'w'), indent=1); print(json.dumps(summary, indent=1)[:1500])"""))
    return nb(cells)


def d0b() -> dict:
    cells = [md(HEADER_B), code(GUARD)]
    cells.append(code(f"""import glob, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
for k in ('PIP_NO_INDEX', 'HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE', 'HF_DATASETS_OFFLINE'): os.environ[k] = '1'
COMP = Path('/kaggle/input/competitions/gemma-4-developer-agent')
WH = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
W = Path('/kaggle/working'); OUT = W / 'heldout_export'; TMP = Path('/tmp/d0b'); PD = TMP / 'pd'; H = TMP / 'pool'
for d in (PD, H / 'snapshots'): d.mkdir(parents=True, exist_ok=True)
hits = glob.glob('/kaggle/input/**/D0A_MANIFEST.json', recursive=True)
assert len(hits) == 1, f'attach exactly one output of notebooks/D0a_heldout_fetch__CPU.ipynb (found {{hits}})'
D0A = Path(hits[0]).parent; MAN = json.load(open(D0A / 'D0A_MANIFEST.json'))
missing = [f for f in MAN['files'] if not (D0A / f).exists()]
assert not missing, f'D0a output incomplete: {{missing[:5]}}'
print('D0a output:', D0A, MAN['summary'])
PIP = [sys.executable, '-m', 'pip', 'install', '-q', '--no-index']
wheels = [str(w) for w in WH.glob('*.whl') if w.name.split('-')[0].lower() in {CPU_WHEELS!r}]
assert len(wheels) == {len(CPU_WHEELS)}, wheels
subprocess.run([*PIP, '--no-deps', *wheels], check=True)
subprocess.run([*PIP, '--no-deps', *map(str, (D0A / 'wheels').glob('codegraph_loc-*.whl'))], check=True)
subprocess.run([*PIP, '--find-links', str(D0A / 'wheels'), '-r', str(D0A / 'need.txt')], check=True)
import swegemma, sentence_transformers; print('swegemma', swegemma.__file__, '| sentence-transformers', sentence_transformers.__version__)
t_start = time.time()"""))
    cells += write_files(FILES_B, "/tmp/d0b/pd")
    cells.append(md("## 1. Pool from D0a (read-only input; snapshots linked, not copied)"))
    cells.append(code("""os.chdir(PD)
for f in ('tasks_text.jsonl', 'meta_text.jsonl'): shutil.copy(D0A / 'pool' / f, H / f)
for s in (D0A / 'pool' / 'snapshots').glob('*.tgz'): (H / 'snapshots' / s.name).symlink_to(s)
print('tasks', sum(1 for _ in open(H / 'tasks_text.jsonl')))"""))
    cells.append(md("## 2. Validate in this image (subprocess backend = the scorer's/starter's)"))
    cells.append(code("""t0 = time.time()
subprocess.run([sys.executable, 'common/validate.py', '--tasks', str(H / 'tasks_text.jsonl'), '--snapshots', str(H / 'snapshots'),
                '--backend', 'subprocess', '--concurrency', '4', '--out', str(H / 'val_subprocess.jsonl')], check=True)
val = [json.loads(l) for l in open(H / 'val_subprocess.jsonl')]
valid = sorted(v['instance_id'] for v in val if v['valid'])
print('valid', len(valid), 'of', len(val), 'minutes', round((time.time() - t0) / 60, 1))"""))
    cells.append(md("## 3. F2P/P2P and annotations (gold nodes, verified repro tests), 3 parallel shards"))
    cells.append(code("""def shards(k):
    return [valid[i::k] for i in range(k)]
procs = [subprocess.Popen([sys.executable, 'common/testmap.py', '--tasks', str(H / 'tasks_text.jsonl'), '--snapshots', str(H / 'snapshots'),
                           '--out', str(H / f'testmap_{i}.jsonl'), '--ids', *s]) for i, s in enumerate(shards(3)) if s]
assert all(p.wait() == 0 for p in procs)
with open(H / 'testmap.jsonl', 'w') as o:
    for f in sorted(H.glob('testmap_*.jsonl')): o.write(open(f).read())
procs = [subprocess.Popen([sys.executable, 'common/annotate.py', '--tasks', str(H / 'tasks_text.jsonl'), '--snapshots', str(H / 'snapshots'),
                           '--testmap', str(H / 'testmap.jsonl'), '--out', str(H / f'ann_{i}.jsonl'), '--verify', '--ids', *s])
         for i, s in enumerate(shards(3)) if s]
assert all(p.wait() == 0 for p in procs)
with open(H / 'annotations.jsonl', 'w') as o:
    for f in sorted(H.glob('ann_*.jsonl')): o.write(open(f).read())
print('annotated', sum(1 for _ in open(H / 'annotations.jsonl')))"""))
    cells.append(md("## 4. Export (graphs + local-model embeddings + local test wheels), prompt-parity check"))
    cells.append(code("""man = json.load(open('pilot_d/manifest.json')); EMB = man['embeddings']
env = {**os.environ, 'EMBED_MODEL_PATH': str(D0A / 'models' / 'bge-small-en-v1.5')}
subprocess.run([sys.executable, 'pilot_d/export_level_a.py', '--work', str(H), '--out', str(OUT), '--tasks', 'tasks_text.jsonl',
                '--meta', 'meta_text.jsonl', '--embed-model', EMB['model'], '--embed-input', EMB['input'],
                '--wheels-dir', str(D0A / 'export_wheels')], check=True, env=env)
subprocess.run([sys.executable, 'pilot_d/check_prompt_parity.py', str(OUT), '--out', str(TMP / 'prompt_parity.json')], check=True, env=env)"""))
    cells.append(md("## 5. Summary (aggregates + our own task ids; safe to commit)"))
    cells.append(code("""meta = {json.loads(l)['instance_id']: json.loads(l) for l in open(OUT / 'heldout_meta.jsonl')}
pp = json.load(open(TMP / 'prompt_parity.json'))['aggregate']
summary = {'export': json.load(open(OUT / 'EXPORT.json')), 'built': len(val), 'valid_kaggle': len(valid),
           'by_repo': {r: {'built': sum(v['repo'] == r for v in val), 'valid': sum(v['repo'] == r and v['valid'] for v in val)}
                       for r in sorted({v['repo'] for v in val})},
           'probe_eligible': sorted(i for i, m in meta.items() if m['probe']['eligible']),
           'issue_text': {i: m['problem_statement_source'] for i, m in meta.items()},
           'invalid': {v['instance_id']: ('empty_patch_passes' if v.get('base_resolved') else (v.get('gold_symptom') or v.get('gold_error') or 'gold_fails')[:80])
                       for v in val if not v['valid']},
           'prompt_parity': pp, 'd0a': MAN['summary'], 'offline': True,
           'minutes': round((time.time() - t_start) / 60, 1)}
json.dump(summary, open(W / 'D0_summary.json', 'w'), indent=1)
print(json.dumps({k: summary[k] for k in ('built', 'valid_kaggle', 'by_repo', 'prompt_parity')}, indent=1))"""))
    return nb(cells)


def nb(cells):
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                         "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}


if __name__ == "__main__":
    (ROOT / "notebooks").mkdir(exist_ok=True)
    for name, fn in (("D0a_heldout_fetch__CPU.ipynb", d0a), ("D0b_heldout_export__CPU.ipynb", d0b)):
        (ROOT / "notebooks" / name).write_text(json.dumps(fn(), indent=1))
        print("wrote notebooks/" + name)
