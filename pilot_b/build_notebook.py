"""Generate notebooks/pilot_b_live.ipynb: e4b with vs without the graph-edit skill on Kaggle L4x4.

The skill and the shared metrics code are embedded as strings, so the notebook runs offline and
always matches this repo. Re-run after changing the skill:  python pilot_b/build_notebook.py
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 15 tasks, stratified by repo and by offline expressibility (seed 20261030, see REPORT.md):
# 10 expressible as symbol edits, 5 not. Smoke = 3 tasks, one per repo.
TASKS = ["fastapi_14458", "fastapi_14964", "rich_3518", "rich_3535", "fastapi_13920", "fastapi_14266",
         "requests_6644", "rich_3130", "fastapi_14303", "fastapi_15745", "requests_7502", "rich_3882",
         "fastapi_5077", "rich_3506", "rich_3777"]
SMOKE = ["fastapi_14458", "rich_3518", "requests_7502"]

EMBED = {
    "skills/graph-edit/SKILL.md": "pilot_b/skill/graph-edit/SKILL.md",
    "skills/graph-edit/scripts/_symlib.py": "pilot_b/skill/graph-edit/scripts/_symlib.py",
    "skills/graph-edit/scripts/show_symbol.py": "pilot_b/skill/graph-edit/scripts/show_symbol.py",
    "skills/graph-edit/scripts/edit_symbol.py": "pilot_b/skill/graph-edit/scripts/edit_symbol.py",
    "skills/graph-edit/scripts/insert_symbol.py": "pilot_b/skill/graph-edit/scripts/insert_symbol.py",
    "common/__init__.py": "common/__init__.py",
    "common/traces.py": "common/traces.py",
    "common/metrics.py": "common/metrics.py",
}

PROMPT_ADDON = """

## Editing code by symbol name (graph-edit skill)
To change code inside a function, method or class, prefer the `graph-edit` skill over edit_file:
- See a symbol: run_skill_script(skill_name="graph-edit", file_path="scripts/show_symbol.py", args={"symbol": "pkg.module.Class.method"})
- Change part of it: run_skill_script(skill_name="graph-edit", file_path="scripts/edit_symbol.py", args={"symbol": "pkg.module.Class.method", "old_string": "...", "new_string": "..."})
- Replace it whole: same script with args={"symbol": ..., "new_source": "<complete new definition>"}
- Add a new function/method: scripts/insert_symbol.py with args={"new_source": ..., "after": "<existing symbol>"}
Symbol names are the dotted names that get_code_neighbors / search_similar_code print. Edits are syntax-checked; on "status": "error" the file is unchanged.
Use edit_file only for imports and other module-level lines.
"""

CELLS = []


def md(s):
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": s})


def code(s):
    CELLS.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s})


md("""# Pilot B live check: graph-edit skill, Gemma 4 E4B, with vs without

Attach: competition `gemma-4-developer-agent`, dataset `metric/gemma-4-developer-agent-wheelhouse`,
model `google/gemma-4/Other/gemma-4-e4b-it-qat-w4a16-ct/2`. Accelerator: **GPU L4 x4**. Internet off.

1. Run with `SMOKE = True` (3 tasks x 2 conditions). It prints measured minutes and an extrapolation.
2. If the extrapolation is OK, set `SMOKE = False` and run again (15 tasks x 2 conditions).
3. Download only `/kaggle/working/pilot_b_live_results.json` (aggregate numbers + per-task ids/numbers;
   no code, patches or traces) and commit it to `results/` on the pilot branch.""")

code(f"""SMOKE = True
MODEL_NAME = 'gemma-4-e4b-it-qat-w4a16-ct'
TASK_IDS = {SMOKE!r} if SMOKE else {TASKS!r}
CONDITIONS = ['baseline', 'graph_edit']
# identical budgets for both conditions (the sample's 10 calls / 1 minute is a toy budget)
BUDGET = dict(max_tool_calls=50, max_time_minutes=10.0, timeout_seconds=120, max_turns=150)
HARD_STOP_H = 1.9   # never start a condition after this much notebook wall time (cap: 2 L4x4 h)
CONCURRENCY = 4
SEED = 1234
import time; T0 = time.time()""")

# starter cell 1 verbatim-equivalent: env + wheelhouse install
code("""import glob, importlib, logging, os, shutil, subprocess, sys, re, json
from pathlib import Path
for k, v in {'TRANSFORMERS_NO_TF': '1', 'TRANSFORMERS_NO_FLAX': '1', 'TRANSFORMERS_OFFLINE': '1',
             'VLLM_NO_USAGE_STATS': '1', 'VLLM_WORKER_MULTIPROC_METHOD': 'spawn', 'VLLM_ENGINE_READY_TIMEOUT_S': '1200',
             'VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS': '1', 'NCCL_DEBUG': 'WARN', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True',
             'LITELLM_TELEMETRY': 'False', 'LITELLM_LOG': 'WARNING', 'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True',
             'OTEL_SDK_DISABLED': 'true', 'OTEL_PYTHON_DISABLED': 'true'}.items():
    os.environ[k] = v
os.environ.setdefault('OPENAI_API_KEY', 'EMPTY'); os.environ.setdefault('LOCAL_API_KEY', 'EMPTY')
for name in ('LiteLLM', 'LiteLLM Router', 'LiteLLM Proxy', 'litellm', 'httpx', 'httpcore', 'openai', 'urllib3', 'opentelemetry'):
    lg = logging.getLogger(name); lg.setLevel(logging.WARNING)
    if 'litellm' in name.lower(): lg.propagate = False; lg.handlers.clear()
WHEELHOUSE_DIR = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
for pat in ('/usr/local/lib/python*/dist-packages/*cutlass*.pth', '/usr/local/lib/python*/site-packages/*cutlass*.pth'):
    for pth in glob.glob(pat):
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
importlib.invalidate_caches()
print('wheelhouse installed')""")

embedded = {dst: open(os.path.join(ROOT, src), encoding="utf-8").read() for dst, src in EMBED.items()}
code(f"""# Embedded pilot files (generated from the repo by pilot_b/build_notebook.py)
PILOT = Path('/kaggle/working/pilot_b'); PILOT.mkdir(parents=True, exist_ok=True)
EMBEDDED = {json.dumps(embedded, indent=0)}
for rel, txt in EMBEDDED.items():
    p = PILOT / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(txt, encoding='utf-8')
sys.path.insert(0, str(PILOT))
PROMPT_ADDON = {PROMPT_ADDON!r}
print(sorted(EMBEDDED))""")

code("""# Build the two submissions from sample_submission (same model, budgets and sampling; only the skill differs)
from swegemma.models import load_tasks
DATA_DIR = Path('/kaggle/input/competitions/gemma-4-developer-agent')
WORKING_DIR = Path('/kaggle/working')
def build_submission(cond):
    d = WORKING_DIR / f'sub_{cond}'
    if d.exists(): shutil.rmtree(d)
    shutil.copytree(DATA_DIR / 'sample_submission', d)
    shutil.rmtree(d / 'adapters', ignore_errors=True)            # 31b-shaped dummy LoRAs
    for y in [d / 'agent.yaml', *sorted((d / 'sub_agents').glob('*.yaml'))]:
        t = y.read_text()
        t = re.sub(r'^(\\s*model:\\s*).*$', rf'\\g<1>{MODEL_NAME}', t, flags=re.M)
        t = re.sub(r'^\\s*adapter:\\s*.*\\n?', '', t, flags=re.M)
        y.write_text(t)
    samp = d / 'configs' / 'sampling.yaml'
    samp.write_text(samp.read_text().rstrip() + f'\\nseed: {SEED}\\n')
    (d / 'eval_config.yaml').write_text('evaluation:\\n' + ''.join(f'  {k}: {v}\\n' for k, v in BUDGET.items()))
    if cond == 'graph_edit':
        shutil.copytree(PILOT / 'skills', d / 'skills')
        y = d / 'agent.yaml'
        y.write_text(y.read_text().rstrip() + '\\nskills:\\n  - skills/graph-edit\\n')
        p = d / 'prompts' / 'system.md'
        p.write_text(p.read_text() + PROMPT_ADDON)
    for pc in d.rglob('__pycache__'): shutil.rmtree(pc)
    return d
SUBS = {c: build_submission(c) for c in CONDITIONS}
tasks = load_tasks(DATA_DIR / 'tasks.jsonl')
sel = [t for t in tasks if t.instance_id in set(TASK_IDS)]
assert len(sel) == len(TASK_IDS), (len(sel), TASK_IDS)
print({c: str(p) for c, p in SUBS.items()}, len(sel), 'tasks')
print((SUBS['graph_edit'] / 'agent.yaml').read_text())""")

code("""# Validate both submissions with the official validator before spending GPU time on vLLM
from adk_submission import validate_directory
from swegemma.config import build_submission_limits
limits, gen_constraints = build_submission_limits()
for c, d in SUBS.items():
    validate_directory(d, limits=limits); print(c, 'valid')""")

code("""# vLLM server (as in the official starter)
import litellm, torch
from adk_submission import VllmConfig, VllmServer, discover_adapters
litellm.drop_params = True
MODEL_PATH = Path(f'/kaggle/input/models/google/gemma-4/other/{MODEL_NAME}/2')
assert MODEL_PATH.exists(), MODEL_PATH
adapters = discover_adapters(str(SUBS['baseline']), adapter_extensions={'.safetensors'})
gpu_count = torch.cuda.device_count()
tp = 4 if gpu_count >= 4 else (2 if gpu_count >= 2 else 1)
T_VLLM = time.time()
server_instance = VllmServer(VllmConfig(
    model=str(MODEL_PATH), port=8000, host='127.0.0.1', tool_call_parser='gemma4', reasoning_parser='gemma4',
    max_model_len=32768, dtype='bfloat16' if torch.cuda.is_bf16_supported() else 'auto', gpu_memory_utilization=0.90,
    enable_auto_tool_choice=True, enable_lora=False, max_loras=1, max_lora_rank=128, scheduler_reserve_full_isl=False,
    tensor_parallel_size=tp, startup_timeout=60 * 20), adapter_manifest=adapters)
server_instance.start()
models = server_instance.create_model_registry(aliases=[MODEL_NAME], model_prefix='openai/', api_key=os.environ.get('LOCAL_API_KEY', 'EMPTY'))
T_VLLM = time.time() - T_VLLM
print('vLLM up in', round(T_VLLM), 's, tp =', tp)""")

code("""# Run both conditions on the same tasks
import asyncio, concurrent.futures
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.apps._configs import EventsCompactionConfig
from swegemma.config import EvalConfig
from swegemma.evaluate import Evaluator
def run_sync(fn):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(fn())).result()
    return asyncio.run(fn())
WALL = {}
for cond in CONDITIONS:
    if (time.time() - T0) / 3600 > HARD_STOP_H:
        print('HARD STOP: not starting', cond); break
    res_dir = WORKING_DIR / f'results_{cond}'
    if res_dir.exists(): shutil.rmtree(res_dir)
    cfg = EvalConfig(
        tasks_path=DATA_DIR / 'tasks.jsonl', snapshots_dir=DATA_DIR / 'snapshots', results_dir=res_dir,
        submission_dir=SUBS[cond], models=models, sandbox='subprocess',
        timeout_seconds=BUDGET['timeout_seconds'], verification_timeout_seconds=300,
        max_time_minutes=BUDGET['max_time_minutes'], max_tool_calls=BUDGET['max_tool_calls'], max_turns=BUDGET['max_turns'],
        limits=limits, generation_constraints=gen_constraints, adapter_manifest=adapters,
        context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
        events_compaction_config=EventsCompactionConfig(compaction_interval=15, overlap_size=2, token_threshold=14336, event_retention_size=5),
        graph_dir=str(DATA_DIR / 'graphs'), embeddings_dir=str(DATA_DIR / 'embeddings'), wheels_dir=DATA_DIR / 'wheels',
        task_ids=list(TASK_IDS), concurrency=CONCURRENCY, display_mode='quiet', verbose=False)
    t = time.time()
    run_sync(Evaluator(cfg).run)
    WALL[cond] = time.time() - t
    print(cond, 'done in', round(WALL[cond] / 60, 1), 'min')""")

code("""# Metrics (common/metrics.py, identical across pilots) -> one JSON with aggregates + per-task numbers
from common.traces import parse_trace
from common.metrics import task_metrics, aggregate
out = {'smoke': SMOKE, 'model': MODEL_NAME, 'task_ids': list(TASK_IDS), 'budget': BUDGET, 'concurrency': CONCURRENCY,
       'seed': SEED, 'vllm_startup_s': T_VLLM, 'condition_wall_s': WALL, 'conditions': {}}
for cond in [c for c in CONDITIONS if c in WALL]:
    res_dir = WORKING_DIR / f'results_{cond}'
    rows = [json.loads(l) for l in open(res_dir / 'task_results.jsonl')]
    per = []
    for r in rows:
        tp_ = res_dir / 'traces' / f"trace_{r['instance_id']}.json"
        tr = parse_trace(str(tp_)) if tp_.exists() else parse_trace({'steps': []})
        m = task_metrics(tr, r)
        m['error'] = (r.get('error') or '')[:120]
        m['tool_names'] = dict(__import__('collections').Counter(e.name for e in tr.events))
        m['skill_scripts'] = dict(__import__('collections').Counter(str(e.args.get('file_path')) for e in tr.events if e.name == 'run_skill_script'))
        m['skill_errors'] = dict(__import__('collections').Counter(
            ((__import__('common.metrics', fromlist=['x']).skill_stdout_json(e) or {}).get('error_type') or 'ok')
            for e in tr.events if e.name == 'run_skill_script'))
        m['edit_file_errors'] = dict(__import__('collections').Counter(
            (e.result.get('error_type') if isinstance(e.result, dict) else 'n/a') for e in tr.events
            if e.name == 'edit_file' and isinstance(e.result, dict) and e.result.get('status') == 'error'))
        per.append(m)
    out['conditions'][cond] = {'aggregate': aggregate(per), 'tasks': per}
elapsed_h = (time.time() - T0) / 3600
out['notebook_wall_h'] = elapsed_h
if SMOKE:
    per_task_min = {c: WALL[c] / 60 / len(TASK_IDS) for c in WALL}
    full_h = (T_VLLM + sum(WALL[c] * 15 / len(TASK_IDS) for c in WALL)) / 3600 + 0.25
    out['extrapolation'] = {'minutes_per_task_at_concurrency': per_task_min, 'full_run_L4x4_hours_est': full_h}
    print('SMOKE: per-task minutes (at concurrency', CONCURRENCY, '):', per_task_min)
    print('Estimated full run (15 tasks x 2 conditions incl. setup): %.2f L4x4 hours' % full_h)
with open(WORKING_DIR / 'pilot_b_live_results.json', 'w') as f:
    json.dump(out, f, indent=1, default=str)
for c in out['conditions']: print(c, json.dumps(out['conditions'][c]['aggregate']))
print('notebook wall: %.2f h' % elapsed_h)""")

nb = {"cells": CELLS, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                   "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}
os.makedirs(os.path.join(ROOT, "notebooks"), exist_ok=True)
with open(os.path.join(ROOT, "notebooks", "pilot_b_live.ipynb"), "w") as f:
    json.dump(nb, f, indent=1)
print("wrote notebooks/pilot_b_live.ipynb")
