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
              "pilot_c/probe.py", "pilot_c/capture_server.py", "pilot_c/probe_runner.py", "pilot_c/analyze_c06.py"]


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
    if sp.get("upstream_ext"):
        up = (f"Add input → Your Work → Notebooks → `{sp['upstream_ext'][:-6]}` (its output; pilot D's notebook on branch "
              "`pilot/d-heldout`)." + ("" if not sp["upstream"] else
                                       f" Also `{SPECS[sp['upstream']]['file'][:-6]}` (its output)."))
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
            "time": "≈ 1.5 L4x4 h (range 1.3–1.8; hard stop 2.0 h)",
            "output": "C04_probe_followup.json", "extra_output": "C04_probe_followup_12b.json, C04_probe_followup_31b.json, C04_probe_followup_e4b.json (one per size), and the analysis files written by the last cell: C04_analysis.json, C04_tables.md, C03C04_analysis.json, C03C04_tables.md, C04_fig4/5 and C03C04_fig1-3 images",
            "what": "Follow-up to the probe, on the same 30 tasks, contexts and words as C03 (read from its output), for 12b, 31b "
                    "and e4b (no e2b). Runs the pre-registered cells C03 did not reach (12b depth 2 and 3 tasks of 12b depth 1) "
                    "and, as exploratory additions (docs/PLAN.md §11 items 10–14): X-graph at depth 2, the unrelated-file "
                    "graph control G-null, and a split of each target's log-likelihood into the action part (call this tool "
                    "now) and the arguments, re-scoring S-find L0/L1/L2/G-json/X-graph and S-use L0/L2/L5/W. The last cell "
                    "writes the final tables and figures."},
    "C05": {"file": "C05_validation_12b__L4x4.ipynb", "accelerator": "GPU L4 x4", "internet": "Off",
            "inputs": [COMPETITION, WHEELHOUSE, "model `google/gemma-4` → Other → `gemma-4-12b-it-qat-w4a16-ct` (version 2; the other three that come with the starter copy are unused)"],
            "upstream": "C03", "upstream_file": "C03_probe.json (the 30 probe tasks, in order)",
            "time": "≈ 2.0 L4x4 h (range 1.6–2.4; ≈ 1.0 h if the sequential rule stops it after 15 tasks; hard stop 2.5 h)",
            "output": "C05_validation_12b.json",
            "what": "12b rollout validation (pre-registered: docs/PLAN_C05_validation.md). The official sample agent "
                    "(adapters removed, 40 calls / 15 min, concurrency 5) runs the 30 probe tasks with no hint (O0) and with "
                    "file + function + test names (O-all), 1 seed each, first on 15 tasks; it stops there if fewer than 2 "
                    "tasks change outcome. Records resolved per task (scorer rule: non-empty patch) and the common metrics."},
    "C06": {"file": "C06_validation_fix_12b__L4x4.ipynb", "accelerator": "GPU L4 x4", "internet": "Off",
            "inputs": [COMPETITION, WHEELHOUSE, "model `google/gemma-4` → Other → `gemma-4-12b-it-qat-w4a16-ct` (version 2; the other three that come with the starter copy are unused)"],
            "upstream": "C03", "upstream_file": "C03_probe.json (the 30 probe tasks, in order)",
            "time": "≈ 2.4 L4x4 h (range 2.0–2.6; ≈ 1.2 h if the sequential rule stops it after 15 tasks; hard stop 2.9 h)",
            "output": "C06_validation_fix_12b.json",
            "extra_output": "C06_analysis.json, C06_tables.md and C06_fig1_how_runs_ended.png, C06_fig2_hint_effect.png, C06_fig3_summary_retention.png (written by the notebook's last cell; numbers only)",
            "what": "The 12b validation of `notebooks/C05_validation_12b__L4x4.ipynb` rerun with one change: the agent requests at most "
                    "8,192 output tokens instead of 16,384, so the prompt can grow to 24,576 tokens before vLLM rejects it "
                    "(pre-registered: docs/PLAN_C06_validation_fix.md). Same 30 tasks, O0 and O-all, concurrency 5, same "
                    "stop rule. It also records, for every request after a compaction, whether the task-prompt marker comes "
                    "from the original prompt or from the summary, and how much of the task statement each summary keeps "
                    "(summary text stays in private/). The last cell runs the frozen analysis (pilot_c/analyze_c06.py) and "
                    "writes the tables and figures."},
    "C03v": {"file": "C03v_test_verify__CPU.ipynb", "accelerator": "None (CPU)", "internet": "Off",
             "inputs": [COMPETITION, WHEELHOUSE], "upstream": "C03",
             "upstream_file": "private/probe_records.jsonl + private/probe_samples_*.jsonl",
             "also_attach": "C04",
             "time": "≈ 2–4 h CPU (each distinct sampled edit is verified once); 0 GPU h",
             "output": "C03v_test_verify.json",
             "extra_output": "C03v_analysis.json, C03v_tables.md, C03v_fig_solves.png (written by the last cell)",
             "what": "Applies each edit sampled by C03 alone to the base snapshot and runs the required tests with the "
                     "scorer's verification path. If `notebooks/C04_probe_followup__L4x4.ipynb` has run, attach its output too: "
                     "its sampled edits are verified in the same pass."},
    "D1": {"file": "D1_heldout_probe__L4x4.ipynb", "accelerator": "GPU L4 x4", "internet": "Off",
           "inputs": [COMPETITION, WHEELHOUSE, "models `google/gemma-4` → Other → `gemma-4-e4b-it-qat-w4a16-ct`, "
                      "`gemma-4-12b-it-qat-w4a16-ct`, `gemma-4-31b-it-qat-w4a16-ct` (version 2; e2b is unused)"],
           "upstream": None, "upstream_ext": "D0b_heldout_export__CPU.ipynb",
           "upstream_file": "heldout_export/ and D0_summary.json",
           "time": "≈ 1.55 L4x4 h main version (range 1.3–2.0; hard stop 2.2 h); ≈ 1.15 h fallback version, `DEPTH2 = False` "
                   "(range 1.0–1.5; hard stop 1.6 h)",
           "output": "D1_heldout_probe.json",
           "extra_output": "D_selection.json, D1_heldout_probe_31b.json, D1_heldout_probe_e4b.json, D1_heldout_probe_12b.json "
                           "(one per size), and the analysis files written by the last cell: D1_analysis.json, D1_tables.md, "
                           "D1_fig1_criteria.png, D1_fig2_depth2.png",
           "what": "Held-out information-ladder probe (pre-registered: docs/PLAN_D1_heldout_probe.md; spec docs/D_SPECS.md on "
                   "paper/main). Re-checks claims 1 and 3 on pilot D's held-out tasks: selects 24 of them by the frozen rule "
                   "(issue statements only, no sympy), captures the agent's contexts with the real harness loop, then for "
                   "31b, e4b and 12b scores 15 depth-1 cells per task and draws 11 depth-2 samples per task. **Version switch:** "
                   "the configuration cell has `DEPTH2 = True` (main version). Set it to `False` for the fallback version "
                   "(depth 1 only); change nothing else. The last cell writes the final tables and figures."},
    "D2": {"file": "D2_heldout_rollouts_12b__L4x4.ipynb", "accelerator": "GPU L4 x4", "internet": "Off",
           "inputs": [COMPETITION, WHEELHOUSE, "model `google/gemma-4` → Other → `gemma-4-12b-it-qat-w4a16-ct` (version 2; "
                      "the other three that come with the starter copy are unused)"],
           "upstream": None, "upstream_ext": "D0b_heldout_export__CPU.ipynb",
           "upstream_file": "heldout_export/ and D0_summary.json",
           "time": "≈ 1.25 L4x4 h (range 1.1–1.6; hard stop 2.0 h)",
           "output": "D2_heldout_rollouts_12b.json",
           "extra_output": "D_selection.json, D2_failed_edits.json, and the analysis files written by the last cell: "
                           "D2_analysis.json, D2_tables.md, D2_fig1_how_runs_ended.png, D2_fig2_summary_retention.png",
           "what": "Held-out rollouts (pre-registered: docs/PLAN_D2_heldout_rollouts_12b.md; spec docs/D_SPECS.md on paper/main). "
                   "Re-checks claims 2 and 4 and measures the held-out solve rate with the paper's agent configuration: the "
                   "official sample agent at 12b with `max_output_tokens` 8192 and C06's instrumentation, no hint, 1 run on each "
                   "of D1's 24 held-out tasks (the same selection rule; if the output of "
                   "`notebooks/D1_heldout_probe__L4x4.ipynb` is attached, its task list is used), concurrency 5. The last cell "
                   "writes the final tables and figures."},
    "D1v": {"file": "D1v_test_verify__CPU.ipynb", "accelerator": "None (CPU)", "internet": "Off",
            "inputs": [COMPETITION, WHEELHOUSE], "upstream": "D1", "upstream_ext": "D0b_heldout_export__CPU.ipynb",
            "upstream_file": "heldout_export/ (D0b); D1_heldout_probe.json + private/probe_records.jsonl + "
                             "private/probe_samples_D1_*.jsonl (D1)",
            "time": "≈ 1–3 h CPU (each distinct sampled edit is verified once); 0 GPU h",
            "output": "D1v_test_verify.json", "extra_output": "D1v_analysis.json, D1v_tables.md (written by the last cell)",
            "what": "Exploratory (docs/PLAN_D1_heldout_probe.md §6): applies each S-use edit sampled by "
                    "`notebooks/D1_heldout_probe__L4x4.ipynb` alone to the held-out task's base snapshot and runs the required "
                    "tests with the scorer's verification path, as `notebooks/C03v_test_verify__CPU.ipynb` did for the dev probe. "
                    "Attach both D0b's output (the tasks) and D1's output (the sampled edits)."},
}


def first_cell(key: str) -> dict:
    sp = SPECS[key]
    up = (f"**the output of `notebooks/{SPECS[sp['upstream']]['file']}`** (Add input → Your Work → Notebooks → "
          f"`{SPECS[sp['upstream']]['file'][:-6]}`; it provides `{sp['upstream_file']}`). Run that notebook first."
          if sp["upstream"] else "none (this notebook runs first).")
    if sp.get("upstream_ext"):
        up = (f"**the output of `notebooks/{sp['upstream_ext']}`** (pilot D, branch `pilot/d-heldout`; Add input → Your Work → "
              f"Notebooks → `{sp['upstream_ext'][:-6]}`; it provides `{sp['upstream_file']}`)."
              + (f" Also **the output of `notebooks/{SPECS[sp['upstream']]['file']}`**." if sp["upstream"] else "")
              + " Run those notebooks first.")
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
        if sp.get("upstream_ext"):
            up = f"`notebooks/{sp['upstream_ext']}` (pilot/d-heldout) → `{sp['upstream_file']}`" + (
                f"; `notebooks/{SPECS[sp['upstream']]['file']}`" if sp["upstream"] else "")
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
            "(2026-10-31), `notebooks/C03_probe__L4x4.ipynb` and `notebooks/C05_validation_12b__L4x4.ipynb` (2026-11-01). "
            "Next: `notebooks/C06_validation_fix_12b__L4x4.ipynb`, then `notebooks/C04_probe_followup__L4x4.ipynb` (GPU; each "
            "needs the coordinator's OK on its estimate), then `notebooks/C03v_test_verify__CPU.ipynb`. "
            "`notebooks/C06_validation_fix_12b__L4x4.ipynb` needs only C03's output, like C05.", "",
            "**Held-out notebooks (D1, D2, D1v; spec `docs/D_SPECS.md` on `paper/main`).** Each needs the output of pilot D's "
            "`notebooks/D0b_heldout_export__CPU.ipynb` (branch `pilot/d-heldout`) attached. "
            "`notebooks/D1_heldout_probe__L4x4.ipynb` and `notebooks/D2_heldout_rollouts_12b__L4x4.ipynb` are independent; both "
            "select the same 24 tasks by the frozen rule (if D1's output is attached to D2, D2 uses D1's list). "
            "`notebooks/D1v_test_verify__CPU.ipynb` (CPU) runs after D1 with D1's output attached too. Plans: "
            "`docs/PLAN_D1_heldout_probe.md`, `docs/PLAN_D2_heldout_rollouts_12b.md`. GPU notebooks need the coordinator's OK on "
            "their estimate first.", "",
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


def code_cells(extra: tuple[str, ...] = ()) -> list[dict]:
    """Environment check, then every repo file the notebook needs, inlined as %%writefile cells. `extra`: committed
    result files (numbers only) a notebook's analysis needs, e.g. results/C05_validation_12b.json."""
    cells = [code(ENV_CHECK), code("import os\nos.makedirs('/kaggle/working/pilot/common', exist_ok=True)\n"
                  "os.makedirs('/kaggle/working/pilot/pilot_c', exist_ok=True)\n"
                  "os.makedirs('/kaggle/working/pilot/results', exist_ok=True)")]
    for rel in list(CODE_FILES) + list(extra):
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
# Order: 12b (depth 2 and the 3 tasks C03 cut), then 31b and e4b (controls and re-scores only). e2b is not run
# (coordinator, 2026-11-02). A time guard skips the tail. Each size's results are saved on their own.
SIZES = ['gemma-4-12b-it-qat-w4a16-ct', 'gemma-4-31b-it-qat-w4a16-ct', 'gemma-4-e4b-it-qat-w4a16-ct']
RESCORE_SIZES = ('31b', 'e4b', '12b')            # re-scored with the action/arguments split:
RESCORE_FIND = ('L0', 'L1', 'L2', 'G-json', 'X-graph')   #   S-find (PLAN §11 item 14)
RESCORE_USE = ('L0', 'L2', 'L5', 'W')                    #   S-use (PLAN §11 item 13)
GRAPH_CONTROLS = (('find', 'G-null'), ('use', 'G-null'))          # depth 1, every size
D2_EXTRA = (('find', 'X-graph'), ('find', 'G-null'))              # depth 2 (n=1), every size
PROBE_GPU_UTIL = 0.75                            # same probe-server settings as C03 (PLAN §11, deviation 7)
PROBE_VLLM_ARGS = ('--max-num-batched-tokens', '1024')
BUDGET = dict(timeout_seconds=120, max_tool_calls=40, max_time_minutes=15)
MAX_SESSION_HOURS = 2.0
WORKERS = 16
"""

FOLLOWUP_ANALYSIS = """
# ---- standalone analysis (pilot_c/analyze_c04.py; tested on synthetic data): the pre-registered tables and figures with
# C04's design cells merged in (C03C04_*), and the exploratory additions (C04_*). Numbers only.
from pilot_c import analyze_c04 as a4
A4 = a4.main(str(kr.find_input_json('C03_probe.json')), '/kaggle/working/C04_probe_followup.json', '/kaggle/working')
print('figures:', A4['figures'])
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
    d1_cells, d2_cells, counts = pr.followup_cells(size, recs, c03, RESCORE_SIZES, GRAPH_CONTROLS, D2_EXTRA,
                                                   RESCORE_USE, RESCORE_FIND)
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


VERIFY_ANALYSIS = """
# ---- standalone analysis (pilot_c/analyze_c03v.py; tested on synthetic data): pass rates per size and condition, the
# information threshold with `exact or solves`, H5 with `solves`. Joins the verified edits to the probe's depth-2 rows
# from C03 and, if attached, C04. Numbers only.
from pilot_c import analyze_c03v as av
_root = Path(os.environ.get('PILOT_INPUT_ROOT', '/kaggle/input'))
_c04 = sorted(str(p) for p in _root.glob('**/C04_probe_followup.json'))[:1]
AV = av.main('/kaggle/working/C03v_test_verify.json', str(kr.find_input_json('C03_probe.json')), *_c04, '/kaggle/working')
print('figures:', AV['figures'])
"""


def probe_verify_nb() -> tuple[dict, str]:
    cells = [first_cell("C03v")]
    cells += code_cells(extra=("pilot_c/analyze_c03v.py",))
    cells.append(code(SETUP.format(gpu="False", only="kr.CPU_WHEELS")))
    cells.append(code(VERIFY_RUN))
    cells.append(code(VERIFY_ANALYSIS))
    cells.append(md(RESULTS_NOTE.format(out=SPECS["C03v"]["output"]).replace(
        "and commit it", "plus `C03v_analysis.json`, `C03v_tables.md` and `C03v_fig_solves.png`, and commit them")))
    return _nb(cells), SPECS["C03v"]["file"]


C06_CONFIG = (VALIDATION_CONFIG
              .replace("pre-registered in docs/PLAN_C05_validation.md", "pre-registered in docs/PLAN_C06_validation_fix.md")
              .replace("SEC_PER_TASK = 465                            # 12b mean wall time per task in notebooks/C01_smoke_timing__L4x4.ipynb",
                       "SEC_PER_TASK = 575                            # 12b mean wall time of C05's runs that did not crash")
              .replace("MAX_SESSION_HOURS = 2.5", "MAX_SESSION_HOURS = 2.9")
              + "SAMPLING_OVERRIDES = {'max_output_tokens': 8192}   # THE change vs C05: prompt limit 32768 - 8192 = 24576 tokens\n")
assert C06_CONFIG.count("PLAN_C06") == 1 and "SEC_PER_TASK = 575" in C06_CONFIG and "MAX_SESSION_HOURS = 2.9" in C06_CONFIG

C06_LOOP = (VALIDATION_LOOP
            .replace("/kaggle/working/C05_validation_12b.json", "/kaggle/working/C06_validation_fix_12b.json")
            .replace("'notebooks/C05_validation_12b__L4x4.ipynb', 'plan': 'docs/PLAN_C05_validation.md',",
                     "'notebooks/C06_validation_fix_12b__L4x4.ipynb', 'plan': 'docs/PLAN_C06_validation_fix.md', "
                     "'sampling_overrides': SAMPLING_OVERRIDES,")
            .replace("agent_dir = kr.prepare_agent_dir(MODEL, BUDGET)", "agent_dir = kr.prepare_agent_dir(MODEL, BUDGET, SAMPLING_OVERRIDES)"))
assert "C06_validation_fix_12b.json" in C06_LOOP and "SAMPLING_OVERRIDES)" in C06_LOOP and "'sampling_overrides'" in C06_LOOP

C06_ANALYSIS = """
# ---- standalone analysis: docs/PLAN_C06_validation_fix.md §6, code pilot_c/analyze_c06.py (frozen before this run).
# Numbers only. Inputs: this session's output, C05's committed results and the 12b probe predictors (both inlined above),
# and the summaries under private/ (only numbers are extracted from them).
from pilot_c import analyze_c06 as a6
A = a6.main('/kaggle/working/C06_validation_fix_12b.json', '/kaggle/working/pilot/results/C05_validation_12b.json',
            '/kaggle/working/pilot/results/C06_predictors_12b.json', '/kaggle/working',
            '/kaggle/working/private/runs/12b/*/summaries.jsonl')
print('figures:', A['figures'], '| setting check:', A['setting_check'])
"""


def validation_fix_nb() -> tuple[dict, str]:
    cells = [first_cell("C06")]
    cells += code_cells(extra=("results/C05_validation_12b.json", "results/C06_predictors_12b.json"))
    cells.append(code(PRECHECK_03.replace("{extra}", "")))
    cells.append(code(SETUP.format(gpu="True", only="None")))
    cells.append(code(C06_CONFIG))
    cells.append(code(C06_LOOP))
    cells.append(code(C06_ANALYSIS))
    cells.append(md(RESULTS_NOTE.format(out=SPECS["C06"]["output"]).replace(
        "and commit it", "plus `C06_analysis.json`, `C06_tables.md` and the three `C06_fig*.png`, and commit them")))
    return _nb(cells), SPECS["C06"]["file"]


def followup_nb() -> tuple[dict, str]:
    cells = [first_cell("C04")]
    cells += code_cells(extra=("common/stats.py", "pilot_c/analyze_c03.py", "pilot_c/analyze_c04.py"))
    cells.append(code(PRECHECK_03.replace("{extra}", "kr.find_input_json('probe_records.jsonl'); kr.find_input_json('probe_contexts.json')")))
    cells.append(code(SETUP.format(gpu="True", only="None")))
    cells.append(code(FOLLOWUP_CONFIG))
    cells.append(code(FOLLOWUP_RUN))
    cells.append(code(FOLLOWUP_ANALYSIS))
    cells.append(md(RESULTS_NOTE.format(out=SPECS["C04"]["output"]).replace(
        "and commit it", "plus `C04_analysis.json`, `C04_tables.md`, `C03C04_analysis.json`, `C03C04_tables.md` and the "
        "`C04_fig*` / `C03C04_fig*` images, and commit them")))
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


HELDOUT_PRECHECK = """
# Held-out data (fails fast if D0b's output is not attached). Task data come from pilot D's export; the agent and the
# sandbox from the competition. The merged directory must exist before kr.set_env() in the next cell.
import os, sys, json
from pathlib import Path
sys.path.insert(0, '/kaggle/working/pilot')
from pilot_c import heldout as ho
EXPORT = ho.find_export()
_ex = json.loads((EXPORT / 'EXPORT.json').read_text())
print('held-out export:', EXPORT, {k: _ex.get(k) for k in ('tasks', 'repos', 'probe_eligible', 'needs_issue_text')})
_d0 = ho.find_optional('D0_summary.json')
print('D0_summary.json:', _d0, (json.loads(_d0.read_text()).get('valid_kaggle') if _d0 else 'not found'))
DATA = ho.merged_data_dir(EXPORT, ho.competition_dir(), Path('/kaggle/working/heldout_data'))
print('data dir:', DATA, sorted(p.name for p in DATA.iterdir()))
"""

D1_CONFIG = """
# ---- configuration (only edit here) — docs/PLAN_D1_heldout_probe.md (frozen at {plan_commit})
PLAN_COMMIT = '{plan_commit}'
DEPTH2 = True                # main version. False = fallback version (depth 1 only); change nothing else
N_TASKS = int(os.environ.get('PILOT_D_N', 24))                # PILOT_D_N: local dry runs only
SIZES = ['gemma-4-31b-it-qat-w4a16-ct', 'gemma-4-e4b-it-qat-w4a16-ct', 'gemma-4-12b-it-qat-w4a16-ct']   # 31b writes the words
FIND = ('L0', 'L1', 'L2', 'W', 'G-json', 'G-null', 'X-func', 'X-graph')   # depth 1, S-find
USE = ('L0', 'L2', 'W', 'T', 'L5', 'G-json', 'G-null')                    # depth 1, S-use
D2_FIND = ('L0', 'L2', 'G-json', 'X-graph', 'G-null')                     # depth 2, 1 sample each
D2_USE = ('L0', 'L2', 'L5')                                               # depth 2, 2 samples each
RESERVE_MIN_PER_SIZE = 20    # depth 2 of a size starts only if this many minutes are left per remaining size
PROBE_GPU_UTIL = 0.75        # probe-server settings of C03/C04 (scheduling/memory only)
PROBE_VLLM_ARGS = ('--max-num-batched-tokens', '1024')
BUDGET = dict(timeout_seconds=120, max_tool_calls=40, max_time_minutes=15)   # capture runs the real agent config
MAX_SESSION_HOURS = 2.2 if DEPTH2 else 1.6
WORKERS = 16
from pilot_c import analyze_d1 as ad
assert (FIND, USE, D2_FIND, D2_USE) == (ad.FIND, ad.USE, ad.D2_FIND, ad.D2_USE), 'config differs from the frozen analysis'
print('version:', 'main (depth 1 + depth 2)' if DEPTH2 else 'fallback (depth 1 only)', '| target tasks:', N_TASKS)
"""

D1_RUN = """
from pilot_c import probe_runner as pr
from pilot_c import probe as pb
from common import server_watchdog as wd
OUT = Path('/kaggle/working/D1_heldout_probe.json')
summary = {'pilot': 'C', 'notebook': 'notebooks/D1_heldout_probe__L4x4.ipynb', 'plan': 'docs/PLAN_D1_heldout_probe.md',
           'plan_commit': PLAN_COMMIT, 'env': kr.env_info(), 'depth2': DEPTH2,
           'export': {k: _ex.get(k) for k in ('format', 'tasks', 'repos', 'graph_generator', 'embeddings')},
           'sizes': [], 'd1': [], 'd2': [], 'freezes': [], 'stopped': None}
def save():
    summary['summary'] = pr.summarize(summary['d1'], summary['d2'])
    summary['session_elapsed_h'] = round((time.time() - SESSION_T0) / 3600, 3)
    OUT.write_text(json.dumps(summary, indent=1)); print('saved', OUT, summary['session_elapsed_h'], 'h')

# 1: task selection (CPU): docs/D_SPECS.md rules 1-6 + the seeded sample; the records are C's probe records
SEL, recs = ho.select_tasks(EXPORT, N_TASKS, ho.find_optional('val_subprocess.jsonl'))
Path('/kaggle/working/D_selection.json').write_text(json.dumps(SEL, indent=1))
print(json.dumps({k: v for k, v in SEL.items() if k != 'selected'}, indent=1))
summary['selection'] = SEL
assert len(recs) >= int(os.environ.get('PILOT_MIN_TASKS', 12)), f'only {len(recs)} held-out tasks qualify: stopping before any GPU work'
# 2: harness graph output (CPU) and the unrelated-graph control
pr.attach_graphs(recs)
pb.assign_null_graphs(recs)
summary['controls'] = {r['instance_id']: {k: v for k, v in r['wrong'].items() if k.endswith('ratio')} for r in recs}
summary['null_controls'] = {r['instance_id']: {k: r['null_graph'][k] for k in ('from', 'len_ratio', 'within_tol')}
                            for r in recs if r.get('null_graph')}
summary['outside_edits'] = {r['instance_id']: r['outside_edits'] for r in recs}
# 3: the agent's exact contexts with the real harness loop (CPU, no model)
ctxs = pr.capture_contexts(recs, BUDGET)
summary['context_checks'] = {r['instance_id']: pr.context_check(r, ctxs[r['instance_id']]) for r in recs if r['instance_id'] in ctxs}
summary['capture_missing'] = [r['instance_id'] for r in recs if r['instance_id'] not in ctxs]
recs = [r for r in recs if r['instance_id'] in ctxs]
summary['task_ids'] = [r['instance_id'] for r in recs]
kr.PRIVATE.mkdir(parents=True, exist_ok=True)
(kr.PRIVATE / 'probe_contexts.json').write_text(json.dumps(ctxs))
save()
assert recs, 'no contexts captured: stopping before any GPU work'

# 4: one vLLM server per size: depth 1, then depth 2 if time is left for the remaining sizes' depth 1.
# Each size is isolated (own try/finally, own output file). Freeze protection as in C03/C04.
deadline = SESSION_T0 + MAX_SESSION_HOURS * 3600
MAX_FREEZES, selfcheck_fail_streak = 2, 0
d1_cells = [(r, st, c, 1, {}) for r in recs for st, conds in (('find', FIND), ('use', USE)) for c in conds]
d2_cells = ([(r, 'find', c, 1) for r in recs for c in D2_FIND] + [(r, 'use', c, 2) for r in recs for c in D2_USE]) if DEPTH2 else []
print('cells per size: depth 1', len(d1_cells), '| depth-2 cells', len(d2_cells))

def retry_failed(rows, cells, depth, server, model, dl, samples_file=None):
    \"\"\"One retry of the cells that failed with a request error (not unavailable, time guard or a frozen server).\"\"\"
    keep = [r for r in rows if r.get('ok') or r.get('why') in ('unavailable', 'time_guard')]
    ck = (lambda c: (c[0]['instance_id'], c[1], c[2], c[3])) if depth == 1 else (lambda c: (c[0]['instance_id'], c[1], c[2]))
    rk = (lambda r: (r['task'], r['state'], r['cond'], r.get('rep', 1))) if depth == 1 else (lambda r: (r['task'], r['state'], r['cond']))
    done = {rk(r) for r in keep}
    miss = [c for c in cells if ck(c) not in done]
    if not miss or wd.TRIPPED.is_set() or time.time() > dl - 120:
        return rows, 0
    print(f'retrying {len(miss)} depth-{depth} cells that failed with a request error')
    rr = pr.run_cells(server, model, recs, ctxs, dl, *((miss, []) if depth == 1 else ([], miss)), WORKERS, samples_file=samples_file)
    return keep + rr['d1' if depth == 1 else 'd2'], len(miss)

for k, model in enumerate(SIZES):
    size = kr.SHORT[model]
    if summary['stopped'] or time.time() > deadline - 600:
        summary['sizes'].append({'model': model, 'size': size, 'skipped': summary['stopped'] or 'session time guard'}); continue
    res, startup, server, dog = {'size': size, 'd1': [], 'd2': [], 'skipped': []}, None, None, None
    try:
        wd.reset()
        agent_dir = kr.prepare_agent_dir(model, BUDGET)
        server, models, adapters, startup = kr.start_server(agent_dir, gpu_memory_utilization=PROBE_GPU_UTIL,
                                                            extra_args=PROBE_VLLM_ARGS)
        dog = wd.Watchdog(kr.server_root(server), lambda srv=server, tag=size: kr.stop_server(srv, tag=tag))
        dog.start()
        res = pr.run_cells(server, model, recs, ctxs, deadline, d1_cells, [], WORKERS, write_words_here=(size == '31b'))
        res['d1'], res['retried_d1'] = retry_failed(res['d1'], d1_cells, 1, server, model, deadline)
        if d2_cells:
            d2_deadline = deadline - RESERVE_MIN_PER_SIZE * 60 * (len(SIZES) - 1 - k)
            if wd.TRIPPED.is_set():
                res['skipped'].append('depth2 (server frozen)')
            elif time.time() > d2_deadline - 300:
                res['skipped'].append('depth2 (time reserved for the remaining sizes)')
            else:
                r2 = pr.run_cells(server, model, recs, ctxs, d2_deadline, [], d2_cells, WORKERS,
                                  samples_file=f'probe_samples_D1_{size}.jsonl')
                res['d2'], res['retried_d2'] = retry_failed(r2['d2'], d2_cells, 2, server, model, d2_deadline,
                                                            f'probe_samples_D1_{size}_retry.jsonl')
                res['d2_minutes'], res['skipped'] = r2.get('d2_minutes'), res['skipped'] + r2['skipped']
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
    Path(f'/kaggle/working/D1_heldout_probe_{size}.json').write_text(json.dumps(
        {'pilot': 'C', 'notebook': 'notebooks/D1_heldout_probe__L4x4.ipynb', 'plan_commit': PLAN_COMMIT, 'size': size,
         'task_ids': summary['task_ids'], 'entry': entry, 'd1': d1, 'd2': d2, 'summary': pr.summarize(d1, d2)}, indent=1))
    summary['d1'] += d1; summary['d2'] += d2
    summary['sizes'].append(entry)
    save()
    if res.get('error'):
        print(f'[{size}] FAILED: {res["error"][:300]}')
save()
summary['words_written'] = sum(bool(r.get('words')) for r in recs)
with open(kr.PRIVATE / 'probe_records.jsonl', 'w') as f:   # with the words: input of notebooks/D1v_test_verify__CPU.ipynb
    for r in recs: f.write(json.dumps(pb.public_record(r)) + '\\n')
save()
print('L4x4 hours used by this session (wall clock):', summary['session_elapsed_h'], '| freezes:', len(summary['freezes']),
      '| stopped:', summary['stopped'])
"""

D1_ANALYSIS = """
# ---- standalone analysis: docs/PLAN_D1_heldout_probe.md §5, code pilot_c/analyze_d1.py (frozen with the plan; tested on
# synthetic data). Re-runnable offline: python -m pilot_c.analyze_d1 D1_heldout_probe.json results/D1_dev_reference.json <out>
from pilot_c import analyze_d1 as ad
AD = ad.main('/kaggle/working/D1_heldout_probe.json', '/kaggle/working/pilot/results/D1_dev_reference.json', '/kaggle/working')
print('figures:', AD['figures'])
"""

D_RESULTS_NOTE = """
**When it finishes:** download {files} (numbers and our own task ids only) and commit them to `results/` on branch
`pilot/c-bottleneck`. Everything under `/kaggle/working/private/` (contexts, records, sampled edits, summaries) and
`/kaggle/working/heldout_data/` (links to the export) is task-derived: keep it on Kaggle, never commit it.
"""


def d1_nb(plan_commit: str) -> tuple[dict, str]:
    cells = [first_cell("D1")]
    cells += code_cells(extra=("common/stats.py", "pilot_c/analyze_c03.py", "pilot_c/analyze_d1.py", "pilot_c/heldout.py",
                               "results/D1_dev_reference.json"))
    cells.append(code(HELDOUT_PRECHECK))
    cells.append(code(SETUP.format(gpu="True", only="None")))
    cells.append(code(D1_CONFIG.replace("{plan_commit}", plan_commit)))
    cells.append(code(D1_RUN))
    cells.append(code(D1_ANALYSIS))
    cells.append(md(D_RESULTS_NOTE.format(files="`D1_heldout_probe.json`, the three `D1_heldout_probe_<size>.json`, "
                                          "`D_selection.json`, `D1_analysis.json`, `D1_tables.md` and the two `D1_fig*.png`")))
    return _nb(cells), SPECS["D1"]["file"]


D2_CONFIG = """
# ---- configuration (only edit here) — docs/PLAN_D2_heldout_rollouts_12b.md (frozen at {plan_commit})
PLAN_COMMIT = '{plan_commit}'
N_TASKS = int(os.environ.get('PILOT_D_N', 24))          # PILOT_D_N / PILOT_D2_BATCH: local dry runs only
MODEL = 'gemma-4-12b-it-qat-w4a16-ct'
CONDITION = 'O0'                                         # no hint
BATCH = int(os.environ.get('PILOT_D2_BATCH', 12))        # results are saved after each batch
BUDGET = dict(timeout_seconds=120, max_tool_calls=40, max_time_minutes=15)   # same agent config as C05/C06
CONCURRENCY = 5
SAMPLING_OVERRIDES = {'max_output_tokens': 8192}         # C06's change: prompt limit 32768 - 8192 = 24576 tokens
SEC_PER_TASK = 728                                       # C06's no-hint mean wall time per task
MAX_SESSION_HOURS = 2.0                                  # a batch starts only if it fits (SEC_PER_TASK x 1.3)
TESTWHEELS = ho.install_test_wheels(EXPORT)              # test-only deps the image lacks: offline, --no-deps, nothing replaced
print('test wheels:', TESTWHEELS)
"""

D2_RUN = """
# ---- 12b rollouts: one vLLM server (starter settings), batches of BATCH tasks. Freeze protection as in C05/C06.
from common import server_watchdog as wd
out = Path('/kaggle/working/D2_heldout_rollouts_12b.json')
summary = {'pilot': 'C', 'notebook': 'notebooks/D2_heldout_rollouts_12b__L4x4.ipynb', 'plan': 'docs/PLAN_D2_heldout_rollouts_12b.md',
           'plan_commit': PLAN_COMMIT, 'env': kr.env_info(), 'budget': BUDGET, 'model': MODEL, 'condition': CONDITION,
           'concurrency': CONCURRENCY, 'sampling_overrides': SAMPLING_OVERRIDES, 'test_wheels': TESTWHEELS,
           'batches': [], 'runs': [], 'servers': [], 'freezes': [], 'restarts': 0, 'stopped': None}
# 1: the D1 task set (deterministic rule); D1's list wins if its output is attached
SEL, _ = ho.select_tasks(EXPORT, N_TASKS, ho.find_optional('val_subprocess.jsonl'))
TASKS = SEL['selected']
_d1 = ho.find_optional('D_selection.json')
if _d1 is not None:
    _d1sel = json.loads(_d1.read_text())['selected']
    summary['d1_selection_matches'] = (_d1sel == TASKS)
    if _d1sel != TASKS:
        _known = {json.loads(l)['instance_id'] for l in open(EXPORT / 'tasks.jsonl')}
        assert set(_d1sel) <= _known, 'D1 selected tasks that are not in this export: attach the same D0b output as D1'
        print('D1 selected a different list; using D1 list:', _d1sel)
        TASKS = _d1sel
summary['selection'], summary['task_ids'] = SEL, TASKS
Path('/kaggle/working/D_selection.json').write_text(json.dumps({**SEL, 'used_by_D2': TASKS}, indent=1))
assert len(TASKS) >= int(os.environ.get('PILOT_MIN_TASKS', 12)), f'only {len(TASKS)} held-out tasks: stopping before any GPU work'
gold = kr.build_gold(TASKS)
BATCHES = [TASKS[i:i + BATCH] for i in range(0, len(TASKS), BATCH)]
MAX_FREEZES = 2

def save():
    rows = [x for r in summary['runs'] for x in r['rows']]
    summary['resolved'], summary['runs_done'] = sum(bool(x['resolved']) for x in rows), len(rows)
    summary['session_elapsed_h'] = round((time.time() - SESSION_T0) / 3600, 3)
    summary['saved_utc'] = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())
    out.write_text(json.dumps(summary, indent=1)); print('saved', out, summary['session_elapsed_h'], 'h')

def start_watched():
    wd.reset()
    agent_dir = kr.prepare_agent_dir(MODEL, BUDGET, SAMPLING_OVERRIDES)
    server, models, adapters, startup = kr.start_server(agent_dir)   # starter settings (gpu_memory_utilization 0.90)
    dog = wd.Watchdog(kr.server_root(server), lambda srv=server: kr.stop_server(srv, tag='12b'))
    dog.start()
    summary['servers'].append({'model': MODEL, 'startup_s': round(startup, 1)})
    return agent_dir, server, models, adapters, dog

server = dog = None
try:
    agent_dir, server, models, adapters, dog = start_watched()
    summary['agent'] = kr.describe_agent(agent_dir)
    for bi, bt in enumerate(BATCHES, 1):
        need_h = len(bt) * SEC_PER_TASK / CONCURRENCY / 3600 * 1.3
        if summary['stopped'] or (time.time() - SESSION_T0) / 3600 + need_h > MAX_SESSION_HOURS:
            summary['batches'].append({'batch': bi, 'tasks': bt, 'skipped': summary['stopped'] or
                                       f'session time guard (needs ~{need_h:.2f} h)'}); continue
        if wd.TRIPPED.is_set():   # the previous batch froze the server: restart it for this one
            dog.stop(); kr.stop_server(server, tag='12b')
            agent_dir, server, models, adapters, dog = start_watched()
            summary['restarts'] += 1
        run = kr.run_condition(agent_dir, models, adapters, bt, gold, CONDITION, 1, CONCURRENCY, tag=f'b{bi}')
        run['batch'] = bi
        if wd.TRIPPED.is_set():
            run['server_frozen'] = True
            summary['freezes'].append({'batch': bi, **wd.state()})
            if len(summary['freezes']) >= MAX_FREEZES:
                summary['stopped'] = 'second inference-server freeze'
        summary['runs'].append(run)
        agg = run['aggregate']
        summary['batches'].append({'batch': bi, 'tasks': bt, 'resolved': agg['resolved'], 'batch_wall_s': run['batch_wall_s']})
        if not wd.TRIPPED.is_set() and agg['n_tasks'] and agg['errors'] == agg['n_tasks'] and not agg['tool_calls_mean']:
            summary['stopped'] = 'every task failed without a single tool call (agent cannot reach the model)'
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
# failed-edit replay (CPU, counts only; pilot_c/edit_failures.py as for C06)
import glob
from pilot_c import edit_failures as ef
_traces = sorted(glob.glob(str(kr.PRIVATE / 'runs' / '12b' / '**' / 'trace_*.json'), recursive=True))
if _traces:
    ef.main('/kaggle/working/D2_failed_edits.json', str(out), *_traces)
print('L4x4 hours used by this session (wall clock):', summary['session_elapsed_h'], '| resolved', summary.get('resolved'),
      'of', summary.get('runs_done'), '| stopped:', summary['stopped'])
"""

D2_ANALYSIS = """
# ---- standalone analysis: docs/PLAN_D2_heldout_rollouts_12b.md §5, code pilot_c/analyze_d2.py (frozen with the plan; tested
# on synthetic data). Re-runnable offline: python -m pilot_c.analyze_d2 D2_heldout_rollouts_12b.json results/D2_dev_reference.json <out> D2_failed_edits.json
from pilot_c import analyze_d2 as a2
A2 = a2.main('/kaggle/working/D2_heldout_rollouts_12b.json', '/kaggle/working/pilot/results/D2_dev_reference.json', '/kaggle/working',
             '/kaggle/working/D2_failed_edits.json', '/kaggle/working/private/runs/12b/*/summaries.jsonl')
print('figures:', A2['figures'], '| setting check:', A2['setting_check'])
"""


def d2_nb(plan_commit: str) -> tuple[dict, str]:
    cells = [first_cell("D2")]
    cells += code_cells(extra=("pilot_c/heldout.py", "pilot_c/edit_failures.py", "pilot_c/analyze_d2.py",
                               "results/D2_dev_reference.json"))
    cells.append(code(HELDOUT_PRECHECK))
    cells.append(code(SETUP.format(gpu="True", only="None")))
    cells.append(code(D2_CONFIG.replace("{plan_commit}", plan_commit)))
    cells.append(code(D2_RUN))
    cells.append(code(D2_ANALYSIS))
    cells.append(md(D_RESULTS_NOTE.format(files="`D2_heldout_rollouts_12b.json`, `D_selection.json`, `D2_failed_edits.json`, "
                                          "`D2_analysis.json`, `D2_tables.md` and the two `D2_fig*.png`")))
    return _nb(cells), SPECS["D2"]["file"]


D1V_RUN = """
# Verify D1's sampled S-use edits (records and samples are next to each other in D1's attached output)
from pilot_c import probe_runner as pr
print('test wheels:', ho.install_test_wheels(EXPORT))   # the subprocess sandbox uses this image's packages
sample_files = sorted(Path(os.environ.get('PILOT_INPUT_ROOT', '/kaggle/input')).glob('**/private/probe_samples_D1_*.jsonl'))
assert sample_files, 'no sampled edits found: attach the output of notebooks/D1_heldout_probe__L4x4.ipynb'
recs_path = sample_files[0].parent / 'probe_records.jsonl'
print('records', recs_path, 'samples', [p.name for p in sample_files])
OUTV = Path('/kaggle/working/D1v_test_verify.json')
res = pr.verify_samples(recs_path, sample_files, OUTV)
res['rows'] = [{**r, 'source': 'D1'} for r in res['rows']]
res['notebook'] = 'notebooks/D1v_test_verify__CPU.ipynb'
OUTV.write_text(json.dumps(res, indent=1))
print(json.dumps(res['summary'], indent=1))
"""

D1V_ANALYSIS = """
# ---- analysis (pilot_c/analyze_d1v.py; tested on synthetic data). Re-runnable offline:
# python -m pilot_c.analyze_d1v D1v_test_verify.json D1_heldout_probe.json results/D1v_dev_reference.json <out>
from pilot_c import analyze_d1v as avd
_d1 = sample_files[0].parent.parent / 'D1_heldout_probe.json'
AV = avd.main(str(OUTV), str(_d1 if _d1.exists() else kr.find_input_json('D1_heldout_probe.json')),
              '/kaggle/working/pilot/results/D1v_dev_reference.json', '/kaggle/working')
"""


def d1v_nb() -> tuple[dict, str]:
    cells = [first_cell("D1v")]
    cells += code_cells(extra=("pilot_c/heldout.py", "pilot_c/analyze_c03v.py", "pilot_c/analyze_d1v.py",
                               "results/D1v_dev_reference.json"))
    cells.append(code(HELDOUT_PRECHECK))
    cells.append(code(SETUP.format(gpu="False", only="kr.CPU_WHEELS")))
    cells.append(code(D1V_RUN))
    cells.append(code(D1V_ANALYSIS))
    cells.append(md(D_RESULTS_NOTE.format(files="`D1v_test_verify.json`, `D1v_analysis.json` and `D1v_tables.md`")))
    return _nb(cells), SPECS["D1v"]["file"]


def _nb(cells: list[dict]) -> dict:
    for i, c in enumerate(cells):
        c["id"] = f"cell-{i:03d}"  # nbformat >= 4.5 requires cell ids
    return {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                                         "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}


# Frozen-plan commits written into the D notebooks (the commit that froze each plan and its analysis code).
PLAN_COMMITS = {"D1": "682a34f01fc90908e786b75845de382d9d2cce49", "D2": "682a34f01fc90908e786b75845de382d9d2cce49"}


def main() -> None:
    out = ROOT / "notebooks"
    builds = [gold_check_nb, smoke_nb, probe_nb, followup_nb, validation_nb, validation_fix_nb, probe_verify_nb,
              lambda: d1_nb(PLAN_COMMITS["D1"]), lambda: d2_nb(PLAN_COMMITS["D2"]), d1v_nb]
    for build in builds:
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
