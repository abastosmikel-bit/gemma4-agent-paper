"""Generate the Pilot C Kaggle notebooks with the repo code inlined (%%writefile cells).

usage: python notebooks/build_notebooks.py
Writes notebooks/pilot_c_<name>/{<name>.ipynb, kernel-metadata.json}.
Each notebook is self-contained: upload it to Kaggle (or `kaggle kernels push -p <dir>`),
attach the inputs listed in its metadata, pick the accelerator named below, run all.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE_FILES = ["common/__init__.py", "common/diffs.py", "common/locate.py", "common/tasks.py", "common/trace.py",
              "common/metrics.py", "common/runtime_probes.py", "pilot_c/__init__.py", "pilot_c/hints.py", "pilot_c/select_tasks.py", "pilot_c/kaggle_runner.py", "pilot_c/task_ids.json",
              "pilot_c/probe.py", "pilot_c/capture_server.py", "pilot_c/probe_runner.py"]
DOCKER_IMAGE = "gcr.io/kaggle-private-byod/python@sha256:37c64f7dd9c54116ecd1bcc88817c5469b88387388fade02bfa8bf3fc647d461"
MODELS = ["google/gemma-4/Other/gemma-4-e4b-it-qat-w4a16-ct/2", "google/gemma-4/Other/gemma-4-e2b-it-qat-w4a16-ct/2",
          "google/gemma-4/Other/gemma-4-31b-it-qat-w4a16-ct/2", "google/gemma-4/Other/gemma-4-12b-it-qat-w4a16-ct/2"]


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.strip("\n").splitlines(keepends=True)}


def code(src: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": src.strip("\n").splitlines(keepends=True)}


def code_cells() -> list[dict]:
    cells = [code("import os\nos.makedirs('/kaggle/working/pilot/common', exist_ok=True)\n"
                  "os.makedirs('/kaggle/working/pilot/pilot_c', exist_ok=True)")]
    for rel in CODE_FILES:
        p = ROOT / rel
        body = p.read_text(encoding="utf-8") if p.exists() else ""
        if not body.strip():
            # papermill/IPython rejects an empty %%writefile body ("cell body is empty")
            body = "# (empty module)\n" if rel.endswith(".py") else body
        assert body.strip(), f"{rel}: %%writefile cell would be empty"
        cells.append(code(f"%%writefile /kaggle/working/pilot/{rel}\n{body}"))
    return cells


SETUP = """
import os, sys, time, json
from pathlib import Path
sys.path.insert(0, '/kaggle/working/pilot')
SESSION_T0 = time.time()
from pilot_c import kaggle_runner as kr
kr.set_env()
kr.install_wheelhouse(gpu={gpu})
kr.quiet_logs()
IDS = json.loads(Path('/kaggle/working/pilot/pilot_c/task_ids.json').read_text())
print(kr.env_info())
"""

GPU_LOOP = """
# ---- the experiment loop: one vLLM server per model, conditions run as separate Evaluator batches
summary = {{"pilot": "C", "notebook": "{name}", "env": kr.env_info(), "budget": BUDGET, "task_ids": TASKS,
           "plan": PLAN, "concurrency": CONCURRENCY, "servers": [], "runs": [], "skipped": []}}
out = Path('/kaggle/working/pilot_c_{name}.json')
assert TASKS, 'no tasks selected - stopping before any GPU work'
gold = kr.build_gold(TASKS)
for model, conds in PLAN:
    if (time.time() - SESSION_T0) / 3600 > MAX_SESSION_HOURS:
        summary["skipped"].append({{"model": model, "reason": "session time guard"}}); continue
    agent_dir = kr.prepare_agent_dir(model, BUDGET)
    summary["agent"] = kr.describe_agent(agent_dir)
    server, models, adapters, startup = kr.start_server(agent_dir)
    summary["servers"].append({{"model": model, "startup_s": round(startup, 1)}})
    try:
        for cond, rep in conds:
            if (time.time() - SESSION_T0) / 3600 > MAX_SESSION_HOURS:
                summary["skipped"].append({{"model": model, "condition": cond, "replicate": rep, "reason": "session time guard"}}); continue
            run = kr.run_condition(agent_dir, models, adapters, TASKS, gold, cond, rep, CONCURRENCY)
            summary["runs"].append(run)
            summary["session_elapsed_h"] = round((time.time() - SESSION_T0) / 3600, 3)
            kr.save_summary(out, summary)
    finally:
        server.stop()
summary["session_elapsed_h"] = round((time.time() - SESSION_T0) / 3600, 3)
kr.save_summary(out, summary)
print('L4x4 hours used by this session (wall clock):', summary["session_elapsed_h"])
"""

RESULTS_NOTE = """
**When it finishes:** download `/kaggle/working/pilot_c_{name}.json` (numbers only: per-task flags/counts, no patches or traces)
and commit it to `results/` on branch `pilot/c-bottleneck`. Everything under `/kaggle/working/private/` (hinted task copies,
patches, traces) is competition-derived: keep it on Kaggle, never commit it.
"""


def gold_check_nb() -> dict:
    name = "gold_check_cpu"
    cells = [md(f"""
# Pilot C — 00: gold-patch check (CPU only, no GPU quota)
Applies each task's **gold** patch in the scorer's Phase-2 verification path (swegemma `verify_task`, subprocess sandbox)
and records whether it resolves. Tasks that fail here are unsolvable in this environment for any agent and are excluded
from the pilot. Also verifies the gold-location extraction runs on Kaggle.

Accelerator: **None (CPU)**. Inputs: competition `gemma-4-developer-agent`, dataset `metric/gemma-4-developer-agent-wheelhouse`.
Expected time: ~40-90 min for all 129 tasks (written incrementally; eligible tasks run first).
Also records WHY a gold patch fails (missing module / missing fixture / test failure ...), e.g. to check the forum
report that 27 fastapi tasks fail on missing `inline_snapshot` / `dirty_equals`, and picks notebook 01's smoke tasks.
**Notebook 01 needs this notebook's output attached as an input** (it reads `pilot_c_gold_check_kaggle.json`).
""")]
    cells += code_cells()
    cells.append(code(SETUP.format(gpu="False")))
    cells.append(code("""
from common.tasks import load_tasks
from pilot_c.select_tasks import eligible
all_ids = [t['instance_id'] for t in load_tasks(kr.data_dir() / 'tasks.jsonl')]
if os.environ.get('PILOT_TEST_IDS'):           # local dry runs only
    all_ids = os.environ['PILOT_TEST_IDS'].split(',')
gold_all = kr.build_gold(all_ids)              # derived data: stays in memory / private
(kr.PRIVATE).mkdir(parents=True, exist_ok=True)
(kr.PRIVATE / 'gold_all.json').write_text(json.dumps(gold_all))
first = [i for i in all_ids if eligible(gold_all[i])]
order = first + [i for i in all_ids if i not in first]
print(len(first), 'eligible tasks first, then the rest')
OUT = Path('/kaggle/working/pilot_c_gold_check_kaggle.json')
res = kr.gold_check(order, OUT)
print('gold resolves:', sum(r['gold_resolved'] for r in res['rows']), '/', len(res['rows']),
      '| valid (gold passes AND no-patch fails):', sum(bool(r.get('valid')) for r in res['rows']))
print(json.dumps(res['summary'], indent=1))
# pre-registered selection for notebook 01 (smoke3) and later runs, from THIS environment's gold check
final = json.loads(OUT.read_text())
final['selection'] = kr.select_from_gold_check(gold_all, res['rows'])
OUT.write_text(json.dumps(final, indent=1))
print('smoke3 for notebook 01:', final['selection']['smoke3'])
"""))
    cells.append(md(RESULTS_NOTE.format(name="gold_check_kaggle")))
    return _nb(cells), _meta(name, gpu=False)


PRECHECK_00 = """
import sys, json
sys.path.insert(0, '/kaggle/working/pilot')
from pilot_c import kaggle_runner as kr
_gc = json.loads(kr.find_input_json('pilot_c_gold_check_kaggle.json').read_text())   # fails fast if not attached
assert len(_gc['selection']['smoke3']) == 3, f"notebook 00 found fewer than 3 valid tasks: {_gc['selection']['smoke3']}"
print('notebook 00 output OK; smoke tasks:', _gc['selection']['smoke3'], '| valid tasks:', _gc['summary']['valid'])
"""


def smoke_nb() -> dict:
    name = "smoke_timing"
    cells = [md("""
# Pilot C — 01: smoke test + per-size timing (GPU, L4 x4)
Runs the unchanged official sample agent (adapters removed, model swapped) on the **same 3 tasks** at O0 for every size,
plus e4b at O-all to exercise the hint path with a real model. Purpose: (1) prove the pipeline works on Kaggle,
(2) measure vLLM startup and minutes per task for each size, (3) log context compaction (how often, when, what it drops,
whether it shows up in the trace) via runtime probes on the ADK summarizer and LLM client.
Budget: 40 tool calls / 15 min per task (same as pilot A).

Accelerator: **GPU L4 x4** (2x quota). Inputs: competition, wheelhouse dataset, all four Gemma 4 QAT models,
and **the output of notebook 00** (Add input → Notebook output → pilot-c-gold-check-cpu). Run 00 first.
Time guard: stops launching new work after `MAX_SESSION_HOURS`.
""")]
    cells += code_cells()
    cells.append(code(PRECHECK_00))
    cells.append(code(SETUP.format(gpu="True")))
    cells.append(code("""
# ---- configuration (only edit here)
GOLD_CHECK = json.loads(kr.find_input_json('pilot_c_gold_check_kaggle.json').read_text())   # notebook 00 output
TASKS = GOLD_CHECK['selection']['smoke3']      # same 3 gold-solvable tasks for every size
assert len(TASKS) == 3, f'expected 3 smoke tasks from notebook 00, got {TASKS}'
print('smoke tasks (from notebook 00):', TASKS)
BUDGET = dict(timeout_seconds=120, max_tool_calls=40, max_time_minutes=15)   # same as pilot A
CONCURRENCY = 3
MAX_SESSION_HOURS = 1.75
PLAN = [
    ('gemma-4-e4b-it-qat-w4a16-ct', [('O0', 1), ('O-all', 1)]),
    ('gemma-4-e2b-it-qat-w4a16-ct', [('O0', 1)]),
    ('gemma-4-12b-it-qat-w4a16-ct', [('O0', 1)]),
    ('gemma-4-31b-it-qat-w4a16-ct', [('O0', 1)]),
]
"""))
    cells.append(code(GPU_LOOP.format(name=name)))
    cells.append(md(RESULTS_NOTE.format(name=name)))
    return _nb(cells), _meta(name, gpu=True)


def pilot_nb() -> dict:
    name = "pilot_e4b"
    cells = [md("""
# Pilot C — 02: oracle ablation pilot (GPU, L4 x4)
e4b on the 15 pilot tasks: O0, O-func, O-all, then O0 again (noise estimate). Optional e2b block (set RUN_E2B).
Hints are appended to the problem statement in a local task copy only (never in a submission).

Accelerator: **GPU L4 x4**. Inputs: competition, wheelhouse dataset, Gemma 4 e4b (and e2b) QAT models.
""")]
    cells += code_cells()
    cells.append(code(SETUP.format(gpu="True")))
    cells.append(code("""
# ---- configuration (only edit here)
# Task set: pre-registered candidate order per repo; keep those whose GOLD patch resolves here (~4 min CPU),
# then take the first `quota` per repo (fastapi 7, rich 6, requests 2).
cands, quota = IDS['candidates_in_order'], IDS['quota']
gcheck = kr.gold_check([i for v in cands.values() for i in v], Path('/kaggle/working/pilot_c_pilot_goldcheck.json'))
ok = {r['instance_id'] for r in gcheck['rows'] if r.get('valid')}
TASKS = [i for repo, k in quota.items() for i in [x for x in cands[repo] if x in ok][:k]]
print(len(TASKS), 'pilot tasks:', TASKS)
if len(TASKS) < 15:
    print('WARNING: fewer than 15 gold-solvable candidates; the pilot runs on', len(TASKS), 'tasks')
BUDGET = dict(timeout_seconds=120, max_tool_calls=40, max_time_minutes=15)
CONCURRENCY = 5
MAX_SESSION_HOURS = 3.9                        # hard ceiling agreed for the pilot is 4 L4x4 hours
RUN_E2B = False
conds = [('O0', 1), ('O-func', 1), ('O-all', 1), ('O0', 2)]
PLAN = [('gemma-4-e4b-it-qat-w4a16-ct', conds)] + ([('gemma-4-e2b-it-qat-w4a16-ct', conds)] if RUN_E2B else [])
"""))
    cells.append(code(GPU_LOOP.format(name=name)))
    cells.append(md(RESULTS_NOTE.format(name=name)))
    return _nb(cells), _meta(name, gpu=True)


PROBE_CONFIG = """
# ---- configuration (only edit here) — docs/PLAN.md (frozen at 168d115)
PLAN_COMMIT = '168d11573bf20003435e4b4a1874cfaebddd0ce1'
GOLD_CHECK = json.loads(kr.find_input_json('pilot_c_gold_check_kaggle.json').read_text())   # notebook 00 output
order = GOLD_CHECK['selection']['eligible_valid_in_order']       # pre-registered per-repo order of VALID tasks
rr, k = [], 0
while any(len(v) > k for v in order.values()):
    rr += [v[k] for v in order.values() if len(v) > k]; k += 1
CANDIDATES = rr[:40]                    # records are built for up to 40, the first 30 constructible are probed
MAX_TASKS = 30
SIZES = ['gemma-4-31b-it-qat-w4a16-ct', 'gemma-4-e4b-it-qat-w4a16-ct', 'gemma-4-12b-it-qat-w4a16-ct', 'gemma-4-e2b-it-qat-w4a16-ct']
BUDGET = dict(timeout_seconds=120, max_tool_calls=40, max_time_minutes=15)   # capture runs the real agent config
MAX_SESSION_HOURS = 2.9
WORKERS = 16
print(len(CANDIDATES), 'candidates;', 'low power (<20)' if len(CANDIDATES) < 20 else 'ok')
"""

PROBE_RUN = """
from pilot_c import probe_runner as pr
from pilot_c import probe as pb
OUT = Path('/kaggle/working/pilot_c_probe.json')
summary = {'pilot': 'C', 'notebook': 'probe', 'plan_commit': PLAN_COMMIT, 'env': kr.env_info(), 'sizes': [], 'd1': [], 'd2': []}
def save():
    summary['summary'] = pr.summarize(summary['d1'], summary['d2'])
    summary['session_elapsed_h'] = round((time.time() - SESSION_T0) / 3600, 3)
    OUT.write_text(json.dumps(summary, indent=1)); print('saved', OUT, summary['session_elapsed_h'], 'h')

# 1-2: records (CPU) and harness graph output (CPU)
recs, excluded = pr.build_records(CANDIDATES)
recs = recs[:MAX_TASKS]
pr.attach_graphs(recs)
summary['task_ids'] = [r['instance_id'] for r in recs]
summary['excluded'] = excluded
summary['controls'] = {r['instance_id']: {k: v for k, v in r['wrong'].items() if k.endswith('ratio')} for r in recs}
summary['outside_edits'] = {r['instance_id']: r['outside_edits'] for r in recs}
# 3: capture the agent's exact contexts with the real harness loop (CPU, no model)
ctxs = pr.capture_contexts(recs, BUDGET)
summary['context_checks'] = {r['instance_id']: pr.context_check(r, ctxs[r['instance_id']]) for r in recs if r['instance_id'] in ctxs}
summary['capture_missing'] = [r['instance_id'] for r in recs if r['instance_id'] not in ctxs]
kr.PRIVATE.mkdir(parents=True, exist_ok=True)
with open(kr.PRIVATE / 'probe_records.jsonl', 'w') as f:
    for r in recs: f.write(json.dumps(pb.public_record(r)) + '\\n')
(kr.PRIVATE / 'probe_contexts.json').write_text(json.dumps(ctxs))
save()

# 4: one vLLM server per size (starter-identical); 31b first because it writes the words rung
deadline = SESSION_T0 + MAX_SESSION_HOURS * 3600
for model in SIZES:
    if time.time() > deadline - 600:
        summary['sizes'].append({'model': model, 'skipped': 'session time guard'}); continue
    agent_dir = kr.prepare_agent_dir(model, BUDGET)
    server, models, adapters, startup = kr.start_server(agent_dir)
    try:
        res = pr.run_size(server, model, recs, ctxs, deadline, WORKERS, write_words_here=(model.startswith('gemma-4-31b')))
    except Exception as e:
        res = {'size': kr.SHORT[model], 'error': f'{type(e).__name__}: {str(e)[:300]}', 'd1': [], 'd2': []}
    finally:
        server.stop()
    summary['d1'] += res.pop('d1'); summary['d2'] += res.pop('d2')
    summary['sizes'].append({'model': model, 'startup_s': round(startup, 1), **res})
    save()
    if 'SELFCHECK' in str(res.get('error', '')) and len(summary['sizes']) == 1:
        print('API self-check failed on the first size: stopping to save GPU quota'); break
with open(kr.PRIVATE / 'probe_records.jsonl', 'w') as f:   # again, now with words and cross-task controls
    for r in recs: f.write(json.dumps(pb.public_record(r)) + '\\n')
print(json.dumps({k: v for k, v in summary['summary'].items() if '/use/' in k and 'depth2' not in k}, indent=0)[:3000])
"""

VERIFY_RUN = """
from pilot_c import probe_runner as pr
recs_path = kr.find_input_json('probe_records.jsonl')
sample_files = sorted(recs_path.parent.glob('probe_samples_*.jsonl'))
print('records', recs_path, 'samples', [p.name for p in sample_files])
res = pr.verify_samples(recs_path, sample_files, Path('/kaggle/working/pilot_c_probe_verify.json'))
print(json.dumps(res['summary'], indent=1))
"""


def probe_nb() -> dict:
    name = "probe"
    cells = [md("""
# Pilot C — 03: information-ladder probe (GPU, L4 x4)
Pre-registered design: `docs/PLAN.md` (frozen at commit 168d115). For each valid task (from notebook 00) and each size
(31b, e4b, 12b, e2b): (1) capture the agent's exact contexts by running the real harness loop against a capture server
(CPU), (2) score the log-likelihood of the canonical correct action under each rung (depth 1, `prompt_logprobs`),
(3) sample one next action with the agent's settings (depth 2). 31b first writes the "change in words" rung.

Accelerator: **GPU L4 x4**. Inputs: competition, wheelhouse dataset, all four Gemma 4 QAT models, **notebook 00's output**.
Time guard `MAX_SESSION_HOURS` (default 2.9 h). Commit only `pilot_c_probe.json` (ids + numbers). Keep `private/` on Kaggle;
notebook 03v (CPU) runs the tests on the sampled edits from it.
""")]
    cells += code_cells()
    cells.append(code(PRECHECK_00.replace("import sys, json", "import os, sys, json").replace(
        "assert len(_gc['selection']['smoke3']) == 3, f\"notebook 00 found fewer than 3 valid tasks: {_gc['selection']['smoke3']}\"",
        "assert _gc['summary']['valid'] >= int(os.environ.get('PILOT_MIN_VALID', 10)), f\"too few valid tasks: {_gc['summary']['valid']}\"")))
    cells.append(code(SETUP.format(gpu="True")))
    cells.append(code(PROBE_CONFIG))
    cells.append(code(PROBE_RUN))
    cells.append(md(RESULTS_NOTE.format(name="probe")))
    return _nb(cells), _meta(name, gpu=True)


def probe_verify_nb() -> dict:
    name = "probe_verify_cpu"
    cells = [md("""
# Pilot C — 03v: run the required tests on the probe's sampled edits (CPU only, no GPU quota)
Attach notebook 03's output (it contains `private/probe_records.jsonl` and `private/probe_samples_*.jsonl`).
Each sampled S-use edit is applied alone to the base snapshot and verified with the scorer's Phase-2 path.
""")]
    cells += code_cells()
    cells.append(code(SETUP.format(gpu="False")))
    cells.append(code(VERIFY_RUN))
    cells.append(md(RESULTS_NOTE.format(name="probe_verify")))
    return _nb(cells), _meta(name, gpu=False)


def _nb(cells: list[dict]) -> dict:
    for i, c in enumerate(cells):
        c["id"] = f"cell-{i:03d}"  # nbformat >= 4.5 requires cell ids
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                         "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}


def _meta(name: str, gpu: bool) -> dict:
    m = {"id": f"YOUR_KAGGLE_USERNAME/pilot-c-{name.replace('_', '-')}", "title": f"Pilot C {name.replace('_', ' ')}",
         "code_file": f"{name}.ipynb", "language": "python", "kernel_type": "notebook", "is_private": True,
         "enable_gpu": gpu, "enable_tpu": False, "enable_internet": False,
         "dataset_sources": ["metric/gemma-4-developer-agent-wheelhouse"], "kernel_sources": [],
         "competition_sources": ["gemma-4-developer-agent"], "model_sources": MODELS if gpu else [],
         "docker_image": DOCKER_IMAGE}
    if name in ("smoke_timing", "probe"):
        m["kernel_sources"] = ["YOUR_KAGGLE_USERNAME/pilot-c-gold-check-cpu"]
    if name == "probe_verify_cpu":
        m["kernel_sources"] = ["YOUR_KAGGLE_USERNAME/pilot-c-probe"]
    if gpu:
        m["machine_shape"] = "NvidiaL4"  # same as the official starter; choose "GPU L4 x4" in the UI if needed
    return m


def main() -> None:
    for build in (gold_check_nb, smoke_nb, pilot_nb, probe_nb, probe_verify_nb):
        nb, meta = build()
        name = meta["code_file"][:-6]
        d = ROOT / "notebooks" / f"pilot_c_{name}"
        d.mkdir(parents=True, exist_ok=True)
        (d / meta["code_file"]).write_text(json.dumps(nb, indent=1), encoding="utf-8")
        (d / "kernel-metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print("wrote", d)


if __name__ == "__main__":
    main()
