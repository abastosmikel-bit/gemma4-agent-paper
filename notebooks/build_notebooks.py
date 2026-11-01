"""Generate the Pilot C Kaggle notebooks with the repo code inlined (%%writefile cells).

usage: python notebooks/build_notebooks.py
Writes notebooks/<file> for every entry of SPECS, and notebooks/README.md (run-order table).
Naming rule (DECISIONS.md, paper/main): <pilot letter><number>_<what>__<accelerator>.ipynb, flat in notebooks/.
Kaggle uses the file name as the notebook title, so the name carries what it is and where it runs.
The first cell of each notebook says what it does, accelerator, internet, inputs to attach, run time, output.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE_FILES = ["common/__init__.py", "common/diffs.py", "common/locate.py", "common/tasks.py", "common/trace.py",
              "common/metrics.py", "common/runtime_probes.py", "common/server_watchdog.py", "pilot_c/__init__.py", "pilot_c/hints.py", "pilot_c/select_tasks.py", "pilot_c/kaggle_runner.py", "pilot_c/task_ids.json",
              "pilot_c/probe.py", "pilot_c/capture_server.py", "pilot_c/probe_runner.py"]


COMPETITION = "competition `gemma-4-developer-agent`"
WHEELHOUSE = "dataset `metric/gemma-4-developer-agent-wheelhouse`"
GEMMA = ("models `google/gemma-4` → Other → `gemma-4-e2b-it-qat-w4a16-ct`, `gemma-4-e4b-it-qat-w4a16-ct`, "
         "`gemma-4-12b-it-qat-w4a16-ct`, `gemma-4-31b-it-qat-w4a16-ct` (version 2)")
L4_NOTE = "The **GPU L4 x4** option only appears after the competition `gemma-4-developer-agent` is attached as an input."
STARTER = "https://www.kaggle.com/code/ryanholbrook/getting-started-gemma-4-developer-agent"
FREEZE_NOTE = ("**Freeze protection:** every request to the inference server has a timeout, and a watchdog polls its "
               "`/health`. If the server stops responding (~90 s), the watchdog kills it, the next unit of work gets a "
               "fresh server, and the session stops after a second freeze. Freezes are listed under `freezes` in the "
               "output file.")
ENV_NOTE = ("These notebooks must run in the **official starter's pinned Kaggle environment (Python 3.12)**. New Kaggle "
            "notebooks default to Python 3.13, and pip then rejects the wheelhouse's cp312 wheels.")


def env_steps(sp: dict) -> list[str]:
    """Exact UI steps to run notebook `sp` in the starter's pinned environment."""
    title = sp["file"][:-6]
    acc = "None" if sp["accelerator"].startswith("None") else "GPU L4 x4"
    up = (f"Add input → Your Work → Notebooks → `{SPECS[sp['upstream']]['file'][:-6]}` (its output)."
          if sp["upstream"] else "No earlier notebook output is needed.")
    if sp.get("also_attach"):
        up += f" If it has run, also `{SPECS[sp['also_attach']]['file'][:-6]}` (its output)."
    models = ("Keep the four Gemma 4 models that came with the copy." if acc != "None"
              else "The Gemma 4 models that came with the copy are not needed (you can remove them).")
    return [
        f"1. Open the official starter: {STARTER} and click **Copy & Edit**. The copy keeps the starter's pinned "
        "environment (Python 3.12) and its inputs: the competition, the wheelhouse and the four Gemma 4 models.",
        f"2. In the copy: **File → Import Notebook** → upload `notebooks/{sp['file']}` from branch `pilot/c-bottleneck`. "
        "This replaces the cells; the environment and inputs stay.",
        f"3. Rename the notebook (title, top left) to `{title}`.",
        f"4. Right panel → **Settings**: Environment = **Pin to original environment** (do not switch to "
        f"\"Always use latest environment\"); Accelerator = **{acc}**; Internet = **Off**.",
        f"5. Inputs: {up} {models}",
        "6. **Save Version → Save & Run All**. The first code cell prints the Python version and stops within seconds "
        "if it is not 3.12. In that case the environment is not the starter's: redo steps 1–4.",
    ]


ENV_CHECK = """
# Environment check (must stay the first code cell)
import sys
print('Python', sys.version)
EXPECTED = (3, 12)   # the official starter's pinned Kaggle environment; the wheelhouse is built for cp312
if sys.version_info[:2] != EXPECTED:
    raise RuntimeError(
        f'WRONG ENVIRONMENT: this session runs Python {sys.version_info[0]}.{sys.version_info[1]}, these notebooks need '
        f'Python {EXPECTED[0]}.{EXPECTED[1]}. Open the official starter (ryanholbrook/getting-started-gemma-4-developer-agent), '
        'click Copy & Edit, then File -> Import Notebook with this .ipynb, and keep Settings -> Environment = '
        '"Pin to original environment". Stopped before installing anything.')
print('environment OK')
"""

# One spec per notebook, in run order. Drives the first cell of each notebook and notebooks/README.md.
SPECS = {
    "C00": {"file": "C00_gold_check__CPU.ipynb", "accelerator": "None (CPU)", "internet": "Off",
            "inputs": [COMPETITION, WHEELHOUSE], "upstream": None, "upstream_file": None,
            "time": "≈ 60–90 min CPU (129 tasks, each verified with the gold patch and with no patch); 0 GPU h",
            "output": "C00_gold_check.json",
            "what": "Applies every task's gold patch AND no patch in the scorer's verification path. A task is valid "
                    "only if gold passes and no-patch fails. Records why gold fails (missing module / fixture / test "
                    "failure), counts fastapi tasks failing on `inline_snapshot`/`dirty_equals`, and writes the "
                    "pre-registered task order and smoke set used by C01 and C03."},
    "C01": {"file": "C01_smoke_timing__L4x4.ipynb", "accelerator": "GPU L4 x4", "internet": "Off",
            "inputs": [COMPETITION, WHEELHOUSE, GEMMA], "upstream": "C00", "upstream_file": "C00_gold_check.json",
            "time": "≈ 1.3 L4x4 h (range 1.0–1.75; hard stop 1.75 h)",
            "output": "C01_smoke_timing.json",
            "what": "Official sample agent (adapters removed, 40 calls / 15 min) on the same 3 valid tasks for e4b, e2b, "
                    "12b, 31b at no hints, plus e4b with all hints. Measures vLLM start-up and minutes per task per "
                    "size, and logs context compaction (how often, when, what it drops, whether the trace shows it)."},
    "C03": {"file": "C03_probe__L4x4.ipynb", "accelerator": "GPU L4 x4", "internet": "Off",
            "inputs": [COMPETITION, WHEELHOUSE, GEMMA], "upstream": "C00", "upstream_file": "C00_gold_check.json",
            "time": "≈ 2.2 L4x4 h (range 1.6–3.0; hard stop 2.9 h)",
            "output": "C03_probe.json", "extra_output": "C03_probe_31b.json, C03_probe_e4b.json, C03_probe_12b.json, C03_probe_e2b.json (one per size; each is complete on its own)",
            "what": "Information-ladder probe (pre-registered: docs/PLAN.md, frozen at 168d115). Captures the agent's "
                    "exact contexts with the real harness loop, then for 31b, e4b, 12b, e2b scores the log-likelihood "
                    "of the correct action under each rung and samples one next action."},
    "C04": {"file": "C04_probe_followup__L4x4.ipynb", "accelerator": "GPU L4 x4", "internet": "Off",
            "inputs": [COMPETITION, WHEELHOUSE, GEMMA], "upstream": "C03",
            "upstream_file": "C03_probe.json + private/probe_records.jsonl + private/probe_contexts.json",
            "time": "≈ 2.0 L4x4 h (range 1.7–2.4; hard stop 2.5 h)",
            "output": "C04_probe_followup.json", "extra_output": "C04_probe_followup_e2b.json, C04_probe_followup_12b.json, C04_probe_followup_31b.json, C04_probe_followup_e4b.json (one per size; each is complete on its own)",
            "what": "Follow-up to the probe, on the same 30 tasks, contexts and words as C03 (read from its output). Runs the "
                    "pre-registered cells C03 did not reach (e2b at both depths, 12b depth 2 and 3 tasks of 12b depth 1) and, "
                    "as exploratory additions (docs/PLAN.md §11 items 10–13): X-graph at depth 2, the unrelated-file graph "
                    "control G-null, and a split of each target's log-likelihood into the action part (call this tool now) "
                    "and the arguments, re-scoring S-use L0/L2/L5/W for 31b, e4b, 12b."},
    "C05": {"file": "C05_validation_12b__L4x4.ipynb", "accelerator": "GPU L4 x4", "internet": "Off",
            "inputs": [COMPETITION, WHEELHOUSE, "model `google/gemma-4` → Other → `gemma-4-12b-it-qat-w4a16-ct` (version 2; the other three that come with the starter copy are unused)"],
            "upstream": "C03", "upstream_file": "C03_probe.json (the 30 probe tasks, in order)",
            "time": "≈ 2.0 L4x4 h (range 1.6–2.4; ≈ 1.0 h if the sequential rule stops it after 15 tasks; hard stop 2.5 h)",
            "output": "C05_validation_12b.json",
            "what": "12b rollout validation (pre-registered: docs/PLAN_C05_validation.md). The official sample agent "
                    "(adapters removed, 40 calls / 15 min, concurrency 5) runs the 30 probe tasks with no hint (O0) and with "
                    "file + function + test names (O-all), 1 seed each, first on 15 tasks; it stops there if fewer than 2 "
                    "tasks change outcome. Records resolved per task (scorer rule: non-empty patch) and the common metrics."},
    "C03v": {"file": "C03v_test_verify__CPU.ipynb", "accelerator": "None (CPU)", "internet": "Off",
             "inputs": [COMPETITION, WHEELHOUSE], "upstream": "C03",
             "upstream_file": "private/probe_records.jsonl + private/probe_samples_*.jsonl",
             "also_attach": "C04",
             "time": "≈ 2–4 h CPU (each distinct sampled edit is verified once); 0 GPU h",
             "output": "C03v_test_verify.json",
             "what": "Applies each edit sampled by C03 alone to the base snapshot and runs the required tests with the "
                     "scorer's verification path. If `notebooks/C04_probe_followup__L4x4.ipynb` has run, attach its output too: "
                     "its sampled edits are verified in the same pass."},
}


def first_cell(key: str) -> dict:
    sp = SPECS[key]
    up = (f"**the output of `notebooks/{SPECS[sp['upstream']]['file']}`** (Add input → Your Work → Notebooks → "
          f"`{SPECS[sp['upstream']]['file'][:-6]}`; it provides `{sp['upstream_file']}`). Run that notebook first."
          if sp["upstream"] else "none (this notebook runs first).")
    if sp.get("also_attach"):
        up += (f" If `notebooks/{SPECS[sp['also_attach']]['file']}` has run, also attach its output "
               f"(`{SPECS[sp['also_attach']]['file'][:-6]}`).")
    lines = [f"# {sp['file'][:-6]} — Pilot C", "", sp["what"], "",
             f"- **Accelerator:** {sp['accelerator']}",
             f"- **Internet:** {sp['internet']}",
             "- **Inputs to attach:** " + "; ".join(sp["inputs"]),
             f"- **Earlier output needed:** {up}",
             f"- **Expected run time:** {sp['time']}",
             f"- **Bring back:** `/kaggle/working/{sp['output']}`"
             + (f" and {sp['extra_output']}" if sp.get("extra_output") else "")
             + " → commit to `results/` on branch `pilot/c-bottleneck`. Leave `/kaggle/working/private/` on Kaggle (competition-derived)."]
    if sp["accelerator"].startswith("GPU"):
        lines.append(f"- {L4_NOTE}")
        lines.append(f"- {FREEZE_NOTE}")
    lines += ["", f"**How to run it in the right environment.** {ENV_NOTE}", ""] + env_steps(sp)
    return md("\n".join(lines))


def readme() -> str:
    head = ["# Pilot C notebooks (run on Kaggle)", "",
            "Generated by `notebooks/build_notebooks.py`; do not edit the `.ipynb` files by hand. Naming rule "
            "(DECISIONS.md on `paper/main`): `<pilot letter><number>_<what>__<accelerator>.ipynb`, flat in `notebooks/`. "
            "Kaggle uses the file name as the title.", "",
            f"> **Note:** {L4_NOTE}", "",
            f"> **Environment:** {ENV_NOTE} Every notebook's first code cell stops it within seconds on any other "
            "Python version.", "",
            "## How to run any of these notebooks (same steps for each; accelerator and inputs per the table)", "",
            *[l.replace(f"`notebooks/{SPECS['C00']['file']}`", "the notebook's `.ipynb`").replace(f"`{SPECS['C00']['file'][:-6]}`", "the file name without `.ipynb`")
              .replace("Accelerator = **None**", "Accelerator = as in the table").replace("No earlier notebook output is needed.", "Attach the earlier notebook's output listed in the table (Add input → Your Work → Notebooks).")
              .replace("The Gemma 4 models that came with the copy are not needed (you can remove them).", "CPU notebooks don't need the Gemma 4 models that came with the copy (you can remove them).")
              for l in env_steps(SPECS["C00"])], "",
            f"> {FREEZE_NOTE.replace('**Freeze protection:**', '**Freeze protection (GPU notebooks):**')}", "",
            "CPU notebooks (`C00`, `C03v`) install only the 5 wheelhouse wheels they need: `swegemma`, `adk_eval_core`, "
            "`adk_submission`, `google_adk`, `google_genai` (all pure Python). GPU notebooks install the starter's full set "
            "of 41.", "",
            "## Run order", "",
            "Run in this order (each row lists everything to attach):", "",
            "| Order | Full path | Accelerator | Internet | Inputs to attach | Earlier output needed | Expected time | Output file to commit |",
            "|---|---|---|---|---|---|---|---|"]
    rows = []
    for i, (k, sp) in enumerate(SPECS.items(), 1):
        up = f"`notebooks/{SPECS[sp['upstream']]['file']}` → `{sp['upstream_file']}`" if sp["upstream"] else "—"
        if sp.get("also_attach"):
            up += f"; also `notebooks/{SPECS[sp['also_attach']]['file']}` if it has run"
        rows.append(f"| {i} | `notebooks/{sp['file']}` | {sp['accelerator']} | {sp['internet']} | "
                    + "; ".join(sp["inputs"]) + f" | {up} | {sp['time']} | `results/{sp['output']}`"
                    + (" + per-size files" if sp.get("extra_output") else "") + " |")
    tail = ["", "`notebooks/C01_smoke_timing__L4x4.ipynb` and `notebooks/C03_probe__L4x4.ipynb` both need only the output of "
            "`notebooks/C00_gold_check__CPU.ipynb`; they are independent of each other. "
            "`notebooks/C04_probe_followup__L4x4.ipynb` and `notebooks/C05_validation_12b__L4x4.ipynb` both need only the output "
            "of `notebooks/C03_probe__L4x4.ipynb`; they are independent of each other. "
            "`notebooks/C03v_test_verify__CPU.ipynb` (CPU) runs last so it can verify the edits of both C03 and C04.", "",
            "**Status:** done on Kaggle: `notebooks/C00_gold_check__CPU.ipynb` and `notebooks/C01_smoke_timing__L4x4.ipynb` "
            "(2026-10-31), `notebooks/C03_probe__L4x4.ipynb` (2026-11-01). Next: `notebooks/C04_probe_followup__L4x4.ipynb` and "
            "`notebooks/C05_validation_12b__L4x4.ipynb` (GPU; each needs the coordinator's OK on its estimate), then "
            "`notebooks/C03v_test_verify__CPU.ipynb`.", "",
            "When a notebook finishes, download the output file named in the table and commit it to `results/`.", "",
            "Every notebook is dry-run locally with papermill (the executor Kaggle uses) before hand-off, under Python 3.12 "
            "and with the real wheel install from the full wheelhouse: "
            "`tests/papermill_dryrun.sh <local_comp> <py3.12 venv> <out> C00 C01 C03 C04 C05 C03v` (WHEELHOUSE=<dir of the 41 wheels>).", "",
            "Data rule: everything under `/kaggle/working/private/` (task copies, gold locations, captured contexts, probe "
            "records, sampled edits, traces) is competition-derived. Leave it on Kaggle. Commit only the output files above "
            "(task IDs, numbers, flags).", ""]
    return "\n".join(head + rows + tail)


def md(src: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": src.strip("\n").splitlines(keepends=True)}


def code(src: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": src.strip("\n").splitlines(keepends=True)}


def code_cells() -> list[dict]:
    cells = [code(ENV_CHECK), code("import os\nos.makedirs('/kaggle/working/pilot/common', exist_ok=True)\n"
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
kr.install_wheelhouse(gpu={gpu}, only={only})
kr.quiet_logs()
IDS = json.loads(Path('/kaggle/working/pilot/pilot_c/task_ids.json').read_text())
print(kr.env_info())
"""

GPU_LOOP = """
# ---- the experiment loop: one vLLM server per model, conditions run as separate Evaluator batches.
# Freeze protection (common/server_watchdog.py): per-request timeouts + a /health watchdog that kills a frozen
# server; the next condition gets a restarted server; the session stops after the second freeze.
from common import server_watchdog as wd
summary = {{"pilot": "C", "notebook": "notebooks/{nbfile}", "env": kr.env_info(), "budget": BUDGET, "task_ids": TASKS,
           "plan": PLAN, "concurrency": CONCURRENCY, "servers": [], "runs": [], "skipped": [], "freezes": [],
           "restarts": 0, "stopped": None}}
out = Path('/kaggle/working/{out}')
assert TASKS, 'no tasks selected - stopping before any GPU work'
gold = kr.build_gold(TASKS)
MAX_FREEZES = 2

def start_watched(model):
    # start a server (in its own process group, after GPU memory is free) and its watchdog
    wd.reset()
    agent_dir = kr.prepare_agent_dir(model, BUDGET)
    server, models, adapters, startup = kr.start_server(agent_dir)
    tag = kr.SHORT[model]
    dog = wd.Watchdog(kr.server_root(server), lambda srv=server: kr.stop_server(srv, tag=tag))
    dog.start()
    summary["servers"].append({{"model": model, "startup_s": round(startup, 1)}})
    return agent_dir, server, models, adapters, dog

for model, conds in PLAN:
    if summary["stopped"] or (time.time() - SESSION_T0) / 3600 > MAX_SESSION_HOURS:
        summary["skipped"].append({{"model": model, "reason": summary["stopped"] or "session time guard"}}); continue
    try:
        agent_dir, server, models, adapters, dog = start_watched(model)
    except kr.GpuMemoryNotReleased as e:
        summary["stopped"] = "GPU memory was not released by a stopped server"
        summary["servers"].append({{"model": model, "error": f"GpuMemoryNotReleased: {{e}}"}})
        kr.save_summary(out, summary); continue
    except Exception as e:
        summary["servers"].append({{"model": model, "error": f"{{type(e).__name__}}: {{str(e)[:400]}}",
                                   "server_error_kinds": kr.error_kinds(kr.LAST_SERVER_ERRORS)}})
        kr.save_summary(out, summary); continue
    summary["agent"] = kr.describe_agent(agent_dir)
    try:
        for cond, rep in conds:
            if summary["stopped"] or (time.time() - SESSION_T0) / 3600 > MAX_SESSION_HOURS:
                summary["skipped"].append({{"model": model, "condition": cond, "replicate": rep,
                                           "reason": summary["stopped"] or "session time guard"}}); continue
            if wd.TRIPPED.is_set():   # the previous condition froze the server: restart it for this one
                dog.stop(); kr.stop_server(server, tag=kr.SHORT[model])
                try:
                    agent_dir, server, models, adapters, dog = start_watched(model)
                except Exception as e:
                    summary["stopped"] = f"restart after a freeze failed: {{type(e).__name__}}: {{str(e)[:200]}}"
                    break
                summary["restarts"] += 1
            run = kr.run_condition(agent_dir, models, adapters, TASKS, gold, cond, rep, CONCURRENCY)
            if wd.TRIPPED.is_set():
                run["server_frozen"] = True
                summary["freezes"].append({{"model": model, "condition": cond, "replicate": rep, **wd.state()}})
                if len(summary["freezes"]) >= MAX_FREEZES:
                    summary["stopped"] = "second inference-server freeze"
            summary["runs"].append(run)
            agg = run["aggregate"]
            if not wd.TRIPPED.is_set() and agg["n_tasks"] and agg["errors"] == agg["n_tasks"] and not agg["tool_calls_mean"]:
                summary["stopped"] = "every task failed without a single tool call (agent cannot reach the model)"
            summary["session_elapsed_h"] = round((time.time() - SESSION_T0) / 3600, 3)
            kr.save_summary(out, summary)
    finally:
        dog.stop(); summary["servers"][-1]["stop"] = kr.stop_server(server, tag=kr.SHORT[model])
summary["session_elapsed_h"] = round((time.time() - SESSION_T0) / 3600, 3)
kr.save_summary(out, summary)
print('L4x4 hours used by this session (wall clock):', summary["session_elapsed_h"], '| freezes:', len(summary["freezes"]),
      '| stopped:', summary["stopped"])
"""

RESULTS_NOTE = """
**When it finishes:** download `/kaggle/working/{out}` (numbers only: per-task flags/counts, no patches or traces)
and commit it to `results/` on branch `pilot/c-bottleneck`. Everything under `/kaggle/working/private/` (hinted task copies,
patches, traces) is competition-derived: keep it on Kaggle, never commit it.
"""


C00_RUN = """
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
OUT = Path('/kaggle/working/C00_gold_check.json')
res = kr.gold_check(order, OUT)
print('gold resolves:', sum(r['gold_resolved'] for r in res['rows']), '/', len(res['rows']),
      '| valid (gold passes AND no-patch fails):', sum(bool(r.get('valid')) for r in res['rows']))
print(json.dumps(res['summary'], indent=1))
# pre-registered selection for C01 (smoke3) and C03 (task order), from THIS environment's gold check
final = json.loads(OUT.read_text())
final['selection'] = kr.select_from_gold_check(gold_all, res['rows'])
OUT.write_text(json.dumps(final, indent=1))
print('smoke3 for notebooks/C01_smoke_timing__L4x4.ipynb:', final['selection']['smoke3'])
"""

C01_CONFIG = """
# ---- configuration (only edit here)
GOLD_CHECK = json.loads(kr.find_input_json('C00_gold_check.json').read_text())   # output of notebooks/C00_gold_check__CPU.ipynb
TASKS = GOLD_CHECK['selection']['smoke3']      # same 3 valid tasks for every size
assert len(TASKS) == 3, f'expected 3 smoke tasks from C00, got {TASKS}'
print('smoke tasks (from notebooks/C00_gold_check__CPU.ipynb):', TASKS)
BUDGET = dict(timeout_seconds=120, max_tool_calls=40, max_time_minutes=15)   # same as pilot A
CONCURRENCY = 3
MAX_SESSION_HOURS = 1.75
PLAN = [
    ('gemma-4-e4b-it-qat-w4a16-ct', [('O0', 1), ('O-all', 1)]),
    ('gemma-4-e2b-it-qat-w4a16-ct', [('O0', 1)]),
    ('gemma-4-12b-it-qat-w4a16-ct', [('O0', 1)]),
    ('gemma-4-31b-it-qat-w4a16-ct', [('O0', 1)]),
]
"""


def gold_check_nb() -> tuple[dict, str]:
    cells = [first_cell("C00")]
    cells += code_cells()
    cells.append(code(SETUP.format(gpu="False", only="kr.CPU_WHEELS")))
    cells.append(code(C00_RUN))
    cells.append(md(RESULTS_NOTE.format(out=SPECS["C00"]["output"])))
    return _nb(cells), SPECS["C00"]["file"]


PRECHECK_00 = """
import sys, json
sys.path.insert(0, '/kaggle/working/pilot')
from pilot_c import kaggle_runner as kr
_gc = json.loads(kr.find_input_json('C00_gold_check.json').read_text())   # fails fast if C00's output is not attached
assert len(_gc['selection']['smoke3']) == 3, f"notebooks/C00_gold_check__CPU.ipynb found fewer than 3 valid tasks: {_gc['selection']['smoke3']}"
print('C00 output OK; smoke tasks:', _gc['selection']['smoke3'], '| valid tasks:', _gc['summary']['valid'])
"""


def smoke_nb() -> tuple[dict, str]:
    cells = [first_cell("C01")]
    cells += code_cells()
    cells.append(code(PRECHECK_00))
    cells.append(code(SETUP.format(gpu="True", only="None")))
    cells.append(code(C01_CONFIG))
    cells.append(code(GPU_LOOP.format(nbfile=SPECS["C01"]["file"], out=SPECS["C01"]["output"])))
    cells.append(md(RESULTS_NOTE.format(out=SPECS["C01"]["output"])))
    return _nb(cells), SPECS["C01"]["file"]


PROBE_CONFIG = """
# ---- configuration (only edit here) — docs/PLAN.md (frozen at 168d115)
PLAN_COMMIT = '168d11573bf20003435e4b4a1874cfaebddd0ce1'
GOLD_CHECK = json.loads(kr.find_input_json('C00_gold_check.json').read_text())   # output of notebooks/C00_gold_check__CPU.ipynb
order = GOLD_CHECK['selection']['eligible_valid_in_order']       # pre-registered per-repo order of VALID tasks
rr, k = [], 0
while any(len(v) > k for v in order.values()):
    rr += [v[k] for v in order.values() if len(v) > k]; k += 1
CANDIDATES = rr[:40]                    # records are built for up to 40, the first 30 constructible are probed
MAX_TASKS = 30
# One server start per size (4 = the minimum; the capture step above uses no inference server). 31b goes first because
# it writes the "change in words" rung that the other sizes' L4/L5/W/X-words cells use; then e4b (the small-footprint
# size), 12b, e2b. Each size's results are saved on their own (C03_probe_<size>.json), so a failure keeps the others.
SIZES = ['gemma-4-31b-it-qat-w4a16-ct', 'gemma-4-e4b-it-qat-w4a16-ct', 'gemma-4-12b-it-qat-w4a16-ct', 'gemma-4-e2b-it-qat-w4a16-ct']
# Probe servers only: more GPU headroom for prompt_logprobs (a full-vocabulary log-softmax per prompt token), smaller
# prefill chunks. Scheduling/memory settings only; they do not change the model's outputs. (PLAN §11, deviation 7)
PROBE_GPU_UTIL = 0.75
PROBE_VLLM_ARGS = ('--max-num-batched-tokens', '1024')
BUDGET = dict(timeout_seconds=120, max_tool_calls=40, max_time_minutes=15)   # capture runs the real agent config
MAX_SESSION_HOURS = 2.9
WORKERS = 16
print(len(CANDIDATES), 'candidates;', 'low power (<20)' if len(CANDIDATES) < 20 else 'ok')
"""

PROBE_RUN = """
from pilot_c import probe_runner as pr
from pilot_c import probe as pb
OUT = Path('/kaggle/working/C03_probe.json')
summary = {'pilot': 'C', 'notebook': 'notebooks/C03_probe__L4x4.ipynb', 'plan_commit': PLAN_COMMIT, 'env': kr.env_info(), 'sizes': [], 'd1': [], 'd2': []}
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

# 4: one vLLM server per size. Each size is isolated: its start, run, stop and GPU-memory wait are wrapped, and its
# results are saved to their own file. Freeze protection (common/server_watchdog.py) kills a frozen server; the
# session stops after a second freeze, after two consecutive self-check failures, or if GPU memory is not released.
from common import server_watchdog as wd
deadline = SESSION_T0 + MAX_SESSION_HOURS * 3600
summary['freezes'], summary['stopped'] = [], None
MAX_FREEZES, selfcheck_fail_streak = 2, 0
for model in SIZES:
    size = kr.SHORT[model]
    if summary['stopped'] or time.time() > deadline - 600:
        summary['sizes'].append({'model': model, 'skipped': summary['stopped'] or 'session time guard'}); continue
    res, startup, server, dog = {'size': size, 'd1': [], 'd2': []}, None, None, None
    try:
        wd.reset()
        agent_dir = kr.prepare_agent_dir(model, BUDGET)
        server, models, adapters, startup = kr.start_server(agent_dir, gpu_memory_utilization=PROBE_GPU_UTIL,
                                                            extra_args=PROBE_VLLM_ARGS)
        dog = wd.Watchdog(kr.server_root(server), lambda srv=server, tag=size: kr.stop_server(srv, tag=tag))
        dog.start()
        res = pr.run_size(server, model, recs, ctxs, deadline, WORKERS, write_words_here=(size == '31b'))
    except kr.GpuMemoryNotReleased as e:
        res['error'] = f'GpuMemoryNotReleased: {e}'
        summary['stopped'] = 'GPU memory was not released by a stopped server'
    except Exception as e:
        res['error'] = f'{type(e).__name__}: {str(e)[:600]}'
    finally:
        if dog is not None:
            dog.stop()
        if server is not None:
            res['stop'] = kr.stop_server(server, tag=size)
        res['server_error_kinds'] = kr.error_kinds(kr.LAST_SERVER_ERRORS)
        if kr.LAST_SERVER_ERRORS and res.get('error'):
            print(f'[{size}] server log errors (full log in private/server_logs/):', *kr.LAST_SERVER_ERRORS[-8:], sep='\\n  ')
    if wd.TRIPPED.is_set():
        res['server_frozen'] = True
        summary['freezes'].append({'model': model, **wd.state()})
        if len(summary['freezes']) >= MAX_FREEZES:
            summary['stopped'] = 'second inference-server freeze'
    selfcheck_fail_streak = selfcheck_fail_streak + 1 if 'SELFCHECK' in str(res.get('error', '')) else 0
    if selfcheck_fail_streak >= 2:
        summary['stopped'] = 'API self-check failed on two sizes in a row'
    d1, d2 = res.pop('d1'), res.pop('d2')
    entry = {'model': model, 'startup_s': round(startup, 1) if startup else None, **res}
    Path(f'/kaggle/working/C03_probe_{size}.json').write_text(json.dumps(
        {'pilot': 'C', 'notebook': 'notebooks/C03_probe__L4x4.ipynb', 'plan_commit': PLAN_COMMIT, 'size': size,
         'task_ids': summary['task_ids'], 'entry': entry, 'd1': d1, 'd2': d2,
         'summary': pr.summarize(d1, d2)}, indent=1))
    summary['d1'] += d1; summary['d2'] += d2
    summary['sizes'].append(entry)
    save()
    if res.get('error'):
        print(f'[{size}] FAILED: {res["error"][:300]}')
save()   # also records sizes skipped after a stop
with open(kr.PRIVATE / 'probe_records.jsonl', 'w') as f:   # again, now with words and cross-task controls
    for r in recs: f.write(json.dumps(pb.public_record(r)) + '\\n')
print(json.dumps({k: v for k, v in summary['summary'].items() if '/use/' in k and 'depth2' not in k}, indent=0)[:3000])
"""

VERIFY_RUN = """
from pilot_c import probe_runner as pr
recs_path = kr.find_input_json('probe_records.jsonl')
_seen, sample_files = set(), []   # sampled edits of C03 and, if its output is attached, C04
for p in sorted(Path(os.environ.get('PILOT_INPUT_ROOT', '/kaggle/input')).glob('**/private/probe_samples_*.jsonl')):
    if p.name not in _seen:
        _seen.add(p.name); sample_files.append(p)
print('records', recs_path, 'samples', [p.name for p in sample_files])
res = pr.verify_samples(recs_path, sample_files, Path('/kaggle/working/C03v_test_verify.json'))
print(json.dumps(res['summary'], indent=1))
"""


PRECHECK_03 = """
import os, sys, json
sys.path.insert(0, '/kaggle/working/pilot')
from pilot_c import kaggle_runner as kr
_c03 = json.loads(kr.find_input_json('C03_probe.json').read_text())   # fails fast if C03's output is not attached
assert len(_c03['task_ids']) >= int(os.environ.get('PILOT_MIN_TASKS', 20)), f"C03 probed only {len(_c03['task_ids'])} tasks"
{extra}
print('C03 output OK:', len(_c03['task_ids']), 'tasks; plan', _c03['plan_commit'][:7])
"""

FOLLOWUP_CONFIG = """
# ---- configuration (only edit here) — docs/PLAN.md (frozen at 168d115) + §11 items 10-13 (exploratory additions)
PLAN_COMMIT = '168d11573bf20003435e4b4a1874cfaebddd0ce1'
# Order: e2b first (the size C03 never reached), then 12b (depth 2), then 31b and e4b (controls and re-scores only).
# A time guard skips the tail. Each size's results are saved on their own (C04_probe_followup_<size>.json).
SIZES = ['gemma-4-e2b-it-qat-w4a16-ct', 'gemma-4-12b-it-qat-w4a16-ct', 'gemma-4-31b-it-qat-w4a16-ct', 'gemma-4-e4b-it-qat-w4a16-ct']
RESCORE_SIZES = ('31b', 'e4b', '12b')            # S-use L0/L2/L5/W re-scored with the action/arguments split
GRAPH_CONTROLS = (('find', 'G-null'), ('use', 'G-null'))          # depth 1, every size
D2_EXTRA = (('find', 'X-graph'), ('find', 'G-null'))              # depth 2 (n=1), every size
PROBE_GPU_UTIL = 0.75                            # same probe-server settings as C03 (PLAN §11, deviation 7)
PROBE_VLLM_ARGS = ('--max-num-batched-tokens', '1024')
BUDGET = dict(timeout_seconds=120, max_tool_calls=40, max_time_minutes=15)
MAX_SESSION_HOURS = 2.5
WORKERS = 16
"""

FOLLOWUP_RUN = """
from pilot_c import probe_runner as pr
from pilot_c import probe as pb
from common import server_watchdog as wd
OUT = Path('/kaggle/working/C04_probe_followup.json')
recs, ctxs, c03 = pr.load_c03_inputs()          # same tasks, records (with 31b's words), contexts as C03
pb.assign_null_graphs(recs)
summary = {'pilot': 'C', 'notebook': 'notebooks/C04_probe_followup__L4x4.ipynb', 'plan_commit': PLAN_COMMIT,
           'plan_additions': 'docs/PLAN.md §11 items 10-13', 'env': kr.env_info(), 'task_ids': [r['instance_id'] for r in recs],
           'c03_plan_commit': c03['plan_commit'], 'sizes': [], 'd1': [], 'd2': [], 'freezes': [], 'stopped': None,
           'null_controls': {r['instance_id']: {k: r['null_graph'][k] for k in ('from', 'len_ratio', 'within_tol')}
                             for r in recs if r.get('null_graph')},
           'contexts_missing': [r['instance_id'] for r in recs if r['instance_id'] not in ctxs]}
assert recs and not summary['contexts_missing'], 'C03 records/contexts incomplete: stopping before any GPU work'
def save():
    summary['summary'] = pr.summarize(summary['d1'], summary['d2'])
    summary['session_elapsed_h'] = round((time.time() - SESSION_T0) / 3600, 3)
    OUT.write_text(json.dumps(summary, indent=1)); print('saved', OUT, summary['session_elapsed_h'], 'h')
save()
deadline = SESSION_T0 + MAX_SESSION_HOURS * 3600
MAX_FREEZES, selfcheck_fail_streak = 2, 0
for model in SIZES:
    size = kr.SHORT[model]
    d1_cells, d2_cells, counts = pr.followup_cells(size, recs, c03, RESCORE_SIZES, GRAPH_CONTROLS, D2_EXTRA)
    print(f'[{size}] cells planned:', counts)
    if summary['stopped'] or time.time() > deadline - 600:
        summary['sizes'].append({'model': model, 'size': size, 'planned': counts, 'skipped': summary['stopped'] or 'session time guard'}); continue
    res, startup, server, dog = {'size': size, 'd1': [], 'd2': []}, None, None, None
    try:
        wd.reset()
        agent_dir = kr.prepare_agent_dir(model, BUDGET)
        server, models, adapters, startup = kr.start_server(agent_dir, gpu_memory_utilization=PROBE_GPU_UTIL,
                                                            extra_args=PROBE_VLLM_ARGS)
        dog = wd.Watchdog(kr.server_root(server), lambda srv=server, tag=size: kr.stop_server(srv, tag=tag))
        dog.start()
        res = pr.run_cells(server, model, recs, ctxs, deadline, d1_cells, d2_cells, WORKERS,
                           samples_file=f'probe_samples_C04_{size}.jsonl')
    except kr.GpuMemoryNotReleased as e:
        res['error'] = f'GpuMemoryNotReleased: {e}'
        summary['stopped'] = 'GPU memory was not released by a stopped server'
    except Exception as e:
        res['error'] = f'{type(e).__name__}: {str(e)[:600]}'
    finally:
        if dog is not None:
            dog.stop()
        if server is not None:
            res['stop'] = kr.stop_server(server, tag=size)
        res['server_error_kinds'] = kr.error_kinds(kr.LAST_SERVER_ERRORS)
        if kr.LAST_SERVER_ERRORS and res.get('error'):
            print(f'[{size}] server log errors (full log in private/server_logs/):', *kr.LAST_SERVER_ERRORS[-8:], sep='\\n  ')
    if wd.TRIPPED.is_set():
        res['server_frozen'] = True
        summary['freezes'].append({'model': model, **wd.state()})
        if len(summary['freezes']) >= MAX_FREEZES:
            summary['stopped'] = 'second inference-server freeze'
    selfcheck_fail_streak = selfcheck_fail_streak + 1 if 'SELFCHECK' in str(res.get('error', '')) else 0
    if selfcheck_fail_streak >= 2:
        summary['stopped'] = 'API self-check failed on two sizes in a row'
    d1, d2 = res.pop('d1'), res.pop('d2')
    entry = {'model': model, 'startup_s': round(startup, 1) if startup else None, 'planned': counts, **res}
    Path(f'/kaggle/working/C04_probe_followup_{size}.json').write_text(json.dumps(
        {'pilot': 'C', 'notebook': 'notebooks/C04_probe_followup__L4x4.ipynb', 'plan_commit': PLAN_COMMIT, 'size': size,
         'task_ids': summary['task_ids'], 'entry': entry, 'd1': d1, 'd2': d2, 'summary': pr.summarize(d1, d2)}, indent=1))
    summary['d1'] += d1; summary['d2'] += d2
    summary['sizes'].append(entry)
    save()
    if res.get('error'):
        print(f'[{size}] FAILED: {res["error"][:300]}')
save()
print('L4x4 hours used by this session (wall clock):', summary['session_elapsed_h'], '| freezes:', len(summary['freezes']),
      '| stopped:', summary['stopped'])
"""

VALIDATION_CONFIG = """
# ---- configuration (only edit here) — pre-registered in docs/PLAN_C05_validation.md
C03 = json.loads(kr.find_input_json('C03_probe.json').read_text())   # output of notebooks/C03_probe__L4x4.ipynb
TASKS = C03['task_ids']                       # the probe tasks, in their pre-registered order
MODEL = 'gemma-4-12b-it-qat-w4a16-ct'
CONDITIONS = ['O0', 'O-all']                  # no hint vs file + function + test names (pilot_c/hints.py)
N_STAGE1 = int(os.environ.get('PILOT_C05_STAGE1_N', 15))
STAGES = [TASKS[:N_STAGE1], TASKS[N_STAGE1:]]
MIN_DISCORDANT_STAGE1 = int(os.environ.get('PILOT_C05_MIN_DISCORDANT', 2))   # sequential rule (PLAN §8)
BUDGET = dict(timeout_seconds=120, max_tool_calls=40, max_time_minutes=15)   # same agent config as C01 and C03's capture
CONCURRENCY = 5
SEC_PER_TASK = 465                            # 12b mean wall time per task in notebooks/C01_smoke_timing__L4x4.ipynb
MAX_SESSION_HOURS = 2.5                       # hard stop: a stage starts only if both its batches fit before it
print(len(TASKS), 'tasks; stage sizes', [len(s) for s in STAGES])
"""

VALIDATION_LOOP = """
# ---- 12b validation: one vLLM server (starter settings), conditions run as separate Evaluator batches per stage.
# Freeze protection (common/server_watchdog.py): per-request timeouts + a /health watchdog that kills a frozen
# server; the next batch gets a restarted server; the session stops after the second freeze.
from common import server_watchdog as wd
from common.metrics import paired_flips
out = Path('/kaggle/working/C05_validation_12b.json')
summary = {'pilot': 'C', 'notebook': 'notebooks/C05_validation_12b__L4x4.ipynb', 'plan': 'docs/PLAN_C05_validation.md',
           'env': kr.env_info(), 'budget': BUDGET, 'task_ids': TASKS, 'model': MODEL, 'conditions': CONDITIONS,
           'concurrency': CONCURRENCY, 'stages': [], 'runs': [], 'servers': [], 'freezes': [], 'restarts': 0, 'stopped': None}
assert TASKS, 'no tasks - stopping before any GPU work'
gold = kr.build_gold(TASKS)
MAX_FREEZES = 2

def save():
    by = {c: [row for r in summary['runs'] if r['condition'] == c for row in r['rows']] for c in CONDITIONS}
    summary['paired_all'] = paired_flips(by['O0'], by['O-all'])
    summary['per_task'] = {t: {c: next((bool(x['resolved']) for x in by[c] if x['instance_id'] == t), None) for c in CONDITIONS}
                           for t in TASKS}
    summary['session_elapsed_h'] = round((time.time() - SESSION_T0) / 3600, 3)
    summary['saved_utc'] = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())
    out.write_text(json.dumps(summary, indent=1)); print('saved', out, summary['session_elapsed_h'], 'h')

def start_watched():
    wd.reset()
    agent_dir = kr.prepare_agent_dir(MODEL, BUDGET)
    server, models, adapters, startup = kr.start_server(agent_dir)   # starter settings (gpu_memory_utilization 0.90)
    dog = wd.Watchdog(kr.server_root(server), lambda srv=server: kr.stop_server(srv, tag='12b'))
    dog.start()
    summary['servers'].append({'model': MODEL, 'startup_s': round(startup, 1)})
    return agent_dir, server, models, adapters, dog

server = dog = None
try:
    agent_dir, server, models, adapters, dog = start_watched()
    summary['agent'] = kr.describe_agent(agent_dir)
    for si, stage_tasks in enumerate(STAGES, 1):
        need_h = 2 * len(stage_tasks) * SEC_PER_TASK / CONCURRENCY / 3600 * 1.3
        if not stage_tasks:
            continue
        if summary['stopped'] or (time.time() - SESSION_T0) / 3600 + need_h > MAX_SESSION_HOURS:
            summary['stages'].append({'stage': si, 'tasks': stage_tasks, 'skipped': summary['stopped'] or
                                      f'session time guard (needs ~{need_h:.2f} h)'}); continue
        stage_rows = {}
        for cond in CONDITIONS:
            if wd.TRIPPED.is_set():   # the previous batch froze the server: restart it for this one
                dog.stop(); kr.stop_server(server, tag='12b')
                agent_dir, server, models, adapters, dog = start_watched()
                summary['restarts'] += 1
            run = kr.run_condition(agent_dir, models, adapters, stage_tasks, gold, cond, 1, CONCURRENCY, tag=f's{si}')
            run['stage'] = si
            if wd.TRIPPED.is_set():
                run['server_frozen'] = True
                summary['freezes'].append({'stage': si, 'condition': cond, **wd.state()})
                if len(summary['freezes']) >= MAX_FREEZES:
                    summary['stopped'] = 'second inference-server freeze'
            summary['runs'].append(run); stage_rows[cond] = run['rows']
            agg = run['aggregate']
            if not wd.TRIPPED.is_set() and agg['n_tasks'] and agg['errors'] == agg['n_tasks'] and not agg['tool_calls_mean']:
                summary['stopped'] = 'every task failed without a single tool call (agent cannot reach the model)'
            save()
            if summary['stopped']:
                break
        if len(stage_rows) == len(CONDITIONS):
            pf = paired_flips(stage_rows['O0'], stage_rows['O-all'])
            st = {'stage': si, 'tasks': stage_tasks, **pf, 'discordant': pf['b_only'] + pf['a_only']}
            summary['stages'].append(st)
            if si == 1 and st['discordant'] < MIN_DISCORDANT_STAGE1:
                summary['stopped'] = (f'sequential rule: {st["discordant"]} discordant task(s) in the first '
                                      f'{len(stage_tasks)} (< {MIN_DISCORDANT_STAGE1})')
        save()
except kr.GpuMemoryNotReleased as e:
    summary['stopped'] = f'GPU memory was not released: {e}'
except Exception as e:
    summary['stopped'] = f'{type(e).__name__}: {str(e)[:400]}'
    summary['server_error_kinds'] = kr.error_kinds(kr.LAST_SERVER_ERRORS)
finally:
    if dog is not None:
        dog.stop()
    if server is not None and summary['servers']:
        summary['servers'][-1]['stop'] = kr.stop_server(server, tag='12b')
    save()
print('L4x4 hours used by this session (wall clock):', summary['session_elapsed_h'], '| stages:',
      [(s['stage'], s.get('discordant', s.get('skipped'))) for s in summary['stages']], '| stopped:', summary['stopped'])
print('paired O-all vs O0 over all run tasks:', summary['paired_all'])
"""


def probe_nb() -> tuple[dict, str]:
    cells = [first_cell("C03")]
    cells += code_cells()
    cells.append(code(PRECHECK_00.replace("import sys, json", "import os, sys, json").replace(
        "assert len(_gc['selection']['smoke3']) == 3, f\"notebooks/C00_gold_check__CPU.ipynb found fewer than 3 valid tasks: {_gc['selection']['smoke3']}\"",
        "assert _gc['summary']['valid'] >= int(os.environ.get('PILOT_MIN_VALID', 10)), f\"too few valid tasks: {_gc['summary']['valid']}\"")))
    cells.append(code(SETUP.format(gpu="True", only="None")))
    cells.append(code(PROBE_CONFIG))
    cells.append(code(PROBE_RUN))
    cells.append(md(RESULTS_NOTE.format(out=SPECS["C03"]["output"])))
    return _nb(cells), SPECS["C03"]["file"]


def probe_verify_nb() -> tuple[dict, str]:
    cells = [first_cell("C03v")]
    cells += code_cells()
    cells.append(code(SETUP.format(gpu="False", only="kr.CPU_WHEELS")))
    cells.append(code(VERIFY_RUN))
    cells.append(md(RESULTS_NOTE.format(out=SPECS["C03v"]["output"])))
    return _nb(cells), SPECS["C03v"]["file"]


def followup_nb() -> tuple[dict, str]:
    cells = [first_cell("C04")]
    cells += code_cells()
    cells.append(code(PRECHECK_03.replace("{extra}", "kr.find_input_json('probe_records.jsonl'); kr.find_input_json('probe_contexts.json')")))
    cells.append(code(SETUP.format(gpu="True", only="None")))
    cells.append(code(FOLLOWUP_CONFIG))
    cells.append(code(FOLLOWUP_RUN))
    cells.append(md(RESULTS_NOTE.format(out=SPECS["C04"]["output"])))
    return _nb(cells), SPECS["C04"]["file"]


def validation_nb() -> tuple[dict, str]:
    cells = [first_cell("C05")]
    cells += code_cells()
    cells.append(code(PRECHECK_03.replace("{extra}", "")))
    cells.append(code(SETUP.format(gpu="True", only="None")))
    cells.append(code(VALIDATION_CONFIG))
    cells.append(code(VALIDATION_LOOP))
    cells.append(md(RESULTS_NOTE.format(out=SPECS["C05"]["output"])))
    return _nb(cells), SPECS["C05"]["file"]


def _nb(cells: list[dict]) -> dict:
    for i, c in enumerate(cells):
        c["id"] = f"cell-{i:03d}"  # nbformat >= 4.5 requires cell ids
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                         "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}


def main() -> None:
    out = ROOT / "notebooks"
    for build in (gold_check_nb, smoke_nb, probe_nb, followup_nb, validation_nb, probe_verify_nb):
        nb, fname = build()
        src = "".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code" and not "".join(c["source"]).startswith("%%"))
        for i, c in enumerate(nb["cells"]):  # every generated code cell must at least parse
            cs = "".join(c["source"])
            if c["cell_type"] == "code" and not (cs.startswith("%%writefile") and not cs.split("\n", 1)[0].endswith(".py")):
                compile(cs.partition("\n")[2] if cs.startswith("%%writefile") else cs, f"{fname}:cell{i}", "exec")
        if "__L4x4" in fname or "__T4x2" in fname:
            assert "wd.Watchdog(" in src and "server_watchdog" in src, f"{fname}: GPU notebooks must run the server watchdog"
        (out / fname).write_text(json.dumps(nb, indent=1), encoding="utf-8")
        print("wrote", out / fname)
    (out / "README.md").write_text(readme(), encoding="utf-8")
    print("wrote", out / "README.md")


if __name__ == "__main__":
    main()
