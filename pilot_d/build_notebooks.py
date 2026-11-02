"""Generate pilot D's Kaggle notebooks (naming rule: DECISIONS 2026-10-31 on paper/main).

notebooks/D0_heldout_export__CPU.ipynb: rebuild, validate and export the held-out pool (docs/PROBE_INPUT.md Level A).
The repo is private, so code files are embedded (written by the notebook itself). Regenerate after code changes:
  python pilot_d/build_notebooks.py
Every code cell is checked to parse; no cell is empty (papermill stops on an empty %%writefile, LEARNINGS 2026-10-31).
"""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ["common/__init__.py", "common/mining.py", "common/snapshot.py", "common/validate.py", "common/testmap.py",
         "common/annotate.py", "common/graph_build.py", "common/github_text.py", "common/embed_nodes.py",
         "pilot_d/__init__.py", "pilot_d/build_tasks.py", "pilot_d/export_level_a.py", "pilot_d/embedding_parity.py",
         "pilot_d/check_prompt_parity.py", "pilot_d/manifest.json"] + sorted(
    str(p.relative_to(ROOT)) for p in (ROOT / "pilot_d" / "env").glob("*.txt"))
CGL = "git+https://github.com/danielmantiglia/codegraph-loc@1e8e0abbb97a1f78648cb12890fd700712b00623"
CPU_WHEELS = ("swegemma", "adk_eval_core", "adk_submission", "google_adk", "google_genai")  # LEARNINGS 2026-10-31

HEADER = """# D0 · held-out export (pilot D) · CPU

**What it does.** It rebuilds pilot D's held-out task pool from public GitHub (the commits listed in
`pilot_d/manifest.json`) and validates every task in this Kaggle image with the harness's own `verify_task`: the gold
patch must pass and the empty patch must fail. It then fetches issue text from the GitHub API for valid tasks, computes
F2P/P2P, gold locations and verified reproduction tests, and writes released-rule graphs and substitute embeddings.
Everything goes into the `docs/PROBE_INPUT.md` (paper/main) **Level A** layout.

| | |
|---|---|
| Accelerator | **CPU** (no GPU quota) |
| Internet | **ON**: GitHub clone + API, PyPI (test deps), Hugging Face (embedding model `Alibaba-NLP/gte-modernbert-base`, safetensors, no remote code) |
| Environment | the official starter's **pinned environment (Python 3.12)**: open the starter, Copy & Edit, File → Import Notebook with this file, keep "Pin to original environment" (LEARNINGS 2026-10-31). The first code cell stops on any other Python. |
| Attach | competition `gemma-4-developer-agent` (dev graphs + embeddings fit the embedding map) · dataset `metric/gemma-4-developer-agent-wheelhouse` |
| Optional | Kaggle Secret `GITHUB_TOKEN` (raises the GitHub API limit; without it the notebook waits for the hourly reset when needed) |
| Expected run time | ≈ 2–4 h (build ≈ 35 min, validation ≈ 30 min, issue text ≤ 1 h without a token, F2P/annotation ≈ 1–1.5 h, embeddings ≈ 30 min) |
| Output to bring back | `/kaggle/working/D0_summary.json` (aggregates + our own task ids/verdicts; commit to `results/` on pilot/d-heldout). The export `/kaggle/working/heldout_export/` is attached by D1/D2 as this notebook's output. Do not commit it. |
"""


def md(s):
    return {"cell_type": "markdown", "metadata": {}, "source": s}


def code(s):
    assert s.strip(), "empty code cell"
    ast.parse(s.replace("%%time\n", ""))
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s}


def d0() -> dict:
    cells = [md(HEADER)]
    cells.append(code("""import sys
assert sys.version_info[:2] == (3, 12), f"Python {sys.version.split()[0]}: use the starter's pinned environment (3.12)"
print(sys.version)"""))
    cells.append(code(f"""import glob, json, os, shutil, subprocess, sys, time
from pathlib import Path
COMP = Path('/kaggle/input/competitions/gemma-4-developer-agent')
WH = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
W = Path('/kaggle/working'); PD = W / 'pd'; H = W / 'pool'; OUT = W / 'heldout_export'
for d in (PD, H): d.mkdir(parents=True, exist_ok=True)
wheels = [str(w) for w in WH.glob('*.whl') if w.name.split('-')[0].lower() in {CPU_WHEELS!r}]
assert len(wheels) == {len(CPU_WHEELS)}, wheels
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', *wheels], check=True)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '{CGL}'], check=True)
try:
    import sentence_transformers  # noqa: F401
except ImportError:
    subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'sentence-transformers'], check=True)
import swegemma; print('swegemma', swegemma.__file__)"""))
    for f in FILES:
        content = (ROOT / f).read_text()
        cells.append(code(f"import os; os.makedirs('/kaggle/working/pd/{Path(f).parent}', exist_ok=True)\n"
                          f"open('/kaggle/working/pd/{f}', 'w').write({content!r}); print('wrote {f}')"))
    cells.append(md("## 1. Rebuild the pool from the manifest (public GitHub)"))
    cells.append(code("""os.chdir(PD)
man = json.load(open('pilot_d/manifest.json'))
DRY = os.environ.get('D0_DRYRUN') == '1'   # local papermill dry run only: 2 tasks per repo, no GitHub API
if DRY:
    keep = os.environ.get('D0_DRYRUN_REPOS')  # e.g. "pyparsing,networkx" to keep the dry run short
    man['repos'] = [r for r in man['repos'] if not keep or r['short'] in keep.split(',')]
    for r in man['repos']: r['instance_ids'] = r['instance_ids'][:2]
    print('DRY RUN: 2 tasks per repo', [r['short'] for r in man['repos']])
t0 = time.time()
for repo in man['repos']:
    d = W / 'src' / repo['short']
    if not d.exists():
        subprocess.run(['git', 'clone', '-q', f"--shallow-since={man['clone_shallow_since']}", repo['url'], str(d)], check=True)
    cand = H / f"cand_{repo['short']}.jsonl"
    subprocess.run([sys.executable, 'common/mining.py', str(d), '--repo', repo['repo'], '--pkg', repo['pkg'],
                    '--since', man['since'], '--out', str(cand), '--funnel', str(H / f"funnel_{repo['short']}.json")], check=True)
    subprocess.run([sys.executable, 'pilot_d/build_tasks.py', str(cand), str(d), str(H), '--ids', *repo['instance_ids']], check=True)
n = sum(1 for _ in open(H / 'tasks.jsonl')); print('built', n, 'of', sum(len(r['instance_ids']) for r in man['repos']), 'minutes', round((time.time() - t0) / 60, 1))"""))
    cells.append(md("## 2. Declared test-only deps (installed only if missing; versions recorded)"))
    cells.append(code("""import importlib, importlib.metadata as md
used = {}
for env in sorted(glob.glob('pilot_d/env/*.txt')):
    for line in open(env):
        line = line.split('#')[0].strip()
        if not line: continue
        dist = line.split('==')[0]; mod = {'python-dateutil': 'dateutil'}.get(dist, dist)
        try: importlib.import_module(mod)
        except ImportError: subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', line], check=True)
        used[dist] = md.version(dist)
print(used)"""))
    cells.append(md("## 3. Validate in this image (subprocess backend = the scorer's/starter's)"))
    cells.append(code("""t0 = time.time()
subprocess.run([sys.executable, 'common/validate.py', '--tasks', str(H / 'tasks.jsonl'), '--snapshots', str(H / 'snapshots'),
                '--backend', 'subprocess', '--concurrency', '4', '--out', str(H / 'val_subprocess.jsonl')], check=True)
val = [json.loads(l) for l in open(H / 'val_subprocess.jsonl')]
valid = sorted(v['instance_id'] for v in val if v['valid'])
print('valid', len(valid), 'of', len(val), 'minutes', round((time.time() - t0) / 60, 1))"""))
    cells.append(md("## 4. Issue text for valid tasks (GitHub API)"))
    cells.append(code("""vs = set(valid)
with open(H / 'tasks_valid.jsonl', 'w') as ft, open(H / 'meta_valid.jsonl', 'w') as fm:
    for l in open(H / 'tasks.jsonl'):
        if json.loads(l)['instance_id'] in vs: ft.write(l)
    for l in open(H / 'meta.jsonl'):
        if json.loads(l)['instance_id'] in vs: fm.write(l)
if DRY:  # this session cannot reach api.github.com; statements stay empty and are flagged needs_issue_text
    shutil.copy(H / 'tasks_valid.jsonl', H / 'tasks_text.jsonl'); shutil.copy(H / 'meta_valid.jsonl', H / 'meta_text.jsonl')
else:
    subprocess.run([sys.executable, 'common/github_text.py', str(H / 'tasks_valid.jsonl'), str(H / 'meta_valid.jsonl'),
                    str(H / 'tasks_text.jsonl'), str(H / 'meta_text.jsonl')], check=True)"""))
    cells.append(md("## 5. F2P/P2P and annotations (gold nodes, verified repro tests), 3 parallel shards"))
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
    cells.append(md("## 6. Embedding map (fit on dev graphs + released embeddings), export, prompt-parity check"))
    cells.append(code("""EMB = man['embeddings']
pairs, seen = [], set()   # rule: the first dev graph (sorted by file name) of each dev repo that has embeddings
for g in sorted((COMP / 'graphs').glob('*.json')):
    repo = g.stem.split('_')[0]; e = COMP / 'embeddings' / f'{g.stem}.npz'
    if repo not in seen and e.exists(): pairs.append(f'{g}:{e}'); seen.add(repo)
mapfile = None
if EMB.get('map'):
    subprocess.run([sys.executable, 'pilot_d/embedding_parity.py', str(W / 'embedding_parity.json'), str(W / 'emb_cache'), *pairs],
                   check=True, env={**os.environ, 'PARITY_CANDIDATES': f"{EMB['model']}/{EMB['input']}"})
    mapfile = W / 'emb_cache' / f"W_{EMB['model']}_{EMB['input']}.npz"
cmd = [sys.executable, 'pilot_d/export_level_a.py', '--work', str(H), '--out', str(OUT), '--tasks', 'tasks_text.jsonl',
       '--meta', 'meta_text.jsonl', '--embed-model', EMB['model'], '--embed-input', EMB['input'],
       '--wheels-req', *sorted(glob.glob('pilot_d/env/*.txt'))]
if mapfile: cmd += ['--embed-map', str(mapfile)]
subprocess.run(cmd, check=True)
subprocess.run([sys.executable, 'pilot_d/check_prompt_parity.py', str(OUT), '--out', str(W / 'prompt_parity.json')], check=True)"""))
    cells.append(md("## 7. Summary (aggregates + our own task ids; safe to commit)"))
    cells.append(code("""meta = {json.loads(l)['instance_id']: json.loads(l) for l in open(OUT / 'heldout_meta.jsonl')}
pp = json.load(open(W / 'prompt_parity.json'))['aggregate']
summary = {'export': json.load(open(OUT / 'EXPORT.json')), 'built': len(val), 'valid_kaggle': len(valid),
           'by_repo': {r: {'built': sum(v['repo'] == r for v in val), 'valid': sum(v['repo'] == r and v['valid'] for v in val)}
                       for r in sorted({v['repo'] for v in val})},
           'probe_eligible': sorted(i for i, m in meta.items() if m['probe']['eligible']),
           'issue_text': {i: m['problem_statement_source'] for i, m in meta.items()},
           'invalid': {v['instance_id']: ('empty_patch_passes' if v.get('base_resolved') else (v.get('gold_symptom') or v.get('gold_error') or 'gold_fails')[:80])
                       for v in val if not v['valid']},
           'prompt_parity': pp, 'test_deps_used': used,
           'embedding_parity': json.load(open(W / 'embedding_parity.json')) if (W / 'embedding_parity.json').exists() else None}
json.dump(summary, open(W / 'D0_summary.json', 'w'), indent=1)
print(json.dumps({k: summary[k] for k in ('built', 'valid_kaggle', 'by_repo', 'prompt_parity')}, indent=1))"""))
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                         "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}


if __name__ == "__main__":
    out = ROOT / "notebooks" / "D0_heldout_export__CPU.ipynb"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(d0(), indent=1))
    print("wrote", out)
