# Claim sheet — every claim of the draft thesis, with its number, source, caveat and where it is shown

Owner: pilot C. Branch for sources: `pilot/c-bottleneck` (files under `results/`, figures under `results/figures/`).
Status: **supported** (measured, single run unless noted) · **partial** · **pending** (waits for a run). A number not
listed here or in `RESULTS.md` is not used. Pull before editing.

---

## 1. Where vs what: location information helps the *find* step, not the *use* step; what to change helps the *use* step

- **Numbers.** Probe, depth 1. Δ log p of the canonical action, in nats; median [95% bootstrap CI]; sizes e4b / 12b / 31b.
  - **S-find, file + function hint (L2 − L0):** +19.4 [17.5, 24.1] / +25.3 [21.3, 29.3] / +33.4 [26.6, 45.6]. The target is
    the correct `read_file`.
  - **S-use, same hint (L2 − L0):** +1.9 [1.0, 3.4] / −1.7 [−3.4, 2.3] / −1.5 [−3.0, 0.6]. The target is the canonical
    edit, after the agent has read the gold code.
  - **Find minus use (H1, pre-registered):** +17.2 / +25.8 / +37.9. Holm p < 0.001 for every size; supported.
  - **S-use, other rungs:**
    - change in words, W − L0: +11.4 / +15.0 / +11.6;
    - full ladder with the exact diff, L5 − L0: +29.2 / +42.4 / +33.8;
    - reproduction test, T − L0: +1.5 / +2.0 / +0.4.
  - **Depth 2 (sampled first action):** the file + function hint raises "reads the gold function" from 13% to 97% (e4b)
    and from 10% to 93% (31b).
- **Source.** `results/C03_probe.json` (9bef339); analysis `results/C03_tables.md` T1, T2, T3 and
  `results/C03_analysis.json` (70e8d9b). Plan `docs/PLAN.md` (frozen at 168d115).
- **Shown in.** `results/figures/C03_fig1_depth1_deltas.png`; tables T1-find, T1-use, T2.
- **Caveats.**
  - Single run, 30 tasks; 12b has 27–28 tasks until C04 completes it; no e2b.
  - It is the likelihood of one canonical action, not a solve rate.
  - The S-use context is the captured state right after reading the gold span.
  - The words rung was written by 31b from the gold diff.
  - The link to agent outcomes is not established. H6 failed in C05 (AUC 0.43, confounded by crashes) and again in C06
    without crashes: AUC 0.27 [0.05, 0.56] over the 19 no-hint failures with a predictor value (6 positives). The
    exploratory find-step predictor gave 0.45 [0.16, 0.76]. So the probe's per-task numbers do not predict which tasks
    the hint rescues in full runs (`results/C06_analysis.json` A4).
- **Status.** Supported at depth 1. **Pending:** C04 (12b complete, which replaces the 12b numbers), C06 (rollout
  validation without crashes), D (held-out tasks).

## 2. Compaction erases the task from the agent's context

- **Numbers.**
  - **Frequency:** compaction fired in 45/60 12b runs in C05 (O0 23/30, O-all 22/30), first at tool call 4–23 (median
    10). In C01 it fired in 3/3 runs of 12b and of 31b, 2/3 of e4b and e2b without hints, and 0/3 of e4b with hints.
  - **The task prompt goes into the summary:** the event holding the task prompt was compacted in every compacted run
    (C05 45/45, C01 10/10).
  - **The header comes back only through the summary:** after compaction, 66/806 C05 requests (O0 47/421, O-all 19/385)
    and 6/147 C01 requests still contained `Problem Statement:`. They all come from 5 runs, and within each run every later
    request has it.
  - **C06 measured it directly** (instrumented, `max_output_tokens` 8192):
    - compaction in 58/60 runs (O0 30/30, O-all 28/30); the prompt event was compacted in 58/58;
    - of 1,472 post-compaction requests (O0 759, O-all 713), **0** still contain the original task statement;
    - the header appears in 63 of them (25 + 38), always inside a summary;
    - 201 summaries (115 + 86): the median summary keeps **0% of the statement's word 5-grams** (O0 0.0, O-all 0.003;
      max 0.50) and **about a third of its words** (median word recall 0.34 / 0.32); 5 of 201 contain the header.
  - **Consequence for editing (exploratory):** with no-hint runs no longer crashing, failed edits rose from 6 (C05) to
    33 (C06), in 8 runs. Replaying each run's file states (harness matcher):
    - 32 of 33 failed `old_string`s never matched the file in any version;
    - 31 of 33 came after the run's first compaction;
    - none had appeared verbatim in an earlier read of that file;
    - 15 repeated an `old_string` that had already failed (11 in one run).

    The model is quoting code that is not there, mostly after compaction removed the file views. It is not the edit tool:
    1 of 33 is accepted by the matcher on replay.
- **Source.**
  - `results/C05_validation_12b.json`, `results/C05_analysis.json` (exploratory section; 0c3b204).
  - `results/C01_smoke_timing.json` (e0c8055).
  - Mechanism: google-adk 1.36.1 `apps/compaction.py` and `apps/llm_event_summarizer.py` (the summary is free text) and
    `flows/llm_flows/contents.py` (the summary is shown to the model as a user message `For context: [model] said: …`).
- **Shown in.** `results/figures/C06_fig3_summary_retention.png`; `results/C06_tables.md` A5; `results/C06_analysis.json`
  A5; `results/C06_failed_edits.json` (8b675fb); `REPORT.md` §17 (check 2).
- **Caveats.**
  - 12b only, single runs.
  - Retention is measured on word 5-grams and words (≥ 4 characters), so it is lexical; a summary can paraphrase the task.
    Word recall of about a third bounds how much vocabulary survives.
  - The failed-edit replay does not see file changes made through `run_command`.
- **Status.** Supported (C05 + C06; 113/113 compacted runs compacted the prompt event; 0/1,472 C06 post-compaction requests
  contain the original statement).

## 3. The graph tool's gain is mostly the file name

- **Numbers.** Probe, S-find; e4b / 12b / 31b.
  - Node names are dotted module paths (e.g. `fastapi.sse._check_id_no_null`), so every `get_code_subgraph` output names
    the file. Seen in the harness tool output used to build `probe_records`.
  - **Right vs wrong focus in the same file:** via graph, G-json − X-graph: +1.0 [0.2, 1.8] / +1.6 [−0.3, 3.0] /
    +1.2 [−0.5, 4.0]. Via text, L2 − X-func: +11.4 / +18.5 / +20.1.
  - **Graph vs text file hint:** G-json − L0: +11.0 / −1.3 / +7.4. L1 − L0 (text file): +6.3 / +8.2 / +6.9.
  - **Depth 2:** "reads the gold file", L0 → G-json: e4b 37% → 83%, 31b 43% → 70%. "Reads the gold function": 13% → 33%
    and 10% → 20%; with the text function hint, 97% and 93%.
- **Source.** `results/C03_tables.md` T1-find, T3, T6; `results/C03_analysis.json` → `exploratory.graph` (70e8d9b).
- **Shown in.** `results/figures/C03_fig3_graph_vs_text.png`; T6.
- **Caveats.**
  - Exploratory.
  - Graph contexts end in a tool response, text contexts in a user turn (and for 31b/12b the scoring mode differs). At
    S-use a graph turn adds +5 (31b) and +8 (12b) whatever its focus, so part of the graph gain may be this ending
    effect.
  - Single run.
- **Status.** Partial. **Pending: C04** (G-null control with the same ending, X-graph at depth 2, the action/arguments
  split of the gain).

## 4. Context-window crashes: the effective prompt limit is 16,384 tokens, and compaction can't keep up

- **Numbers.**
  - **Limit:** 32,768 (vLLM `max_model_len`) − 16,384 (the agent's `max_output_tokens`) = 16,384 tokens. Compaction
    triggers when the *previous* request's prompt is ≥ 14,336, a gap of 2,048 tokens.
  - **C05 (12b):** 14/30 no-hint and 9/30 hinted runs ended with `ContextWindowExceeded`; 11 of the 23 before any
    compaction, at 5–23 tool calls.
  - **Link to the hint effect:** all 7 fail→pass tasks are tasks whose no-hint run crashed. The hint rescued 7/14 crashed
    tasks vs 0/10 that failed otherwise (Fisher p = 0.019, post hoc).
  - **C01:** 2/15 runs (e2b 1/3, 12b 1/3).
  - **C06, the same 30 tasks with `max_output_tokens: 8192`:**
    - crashes fell from 14 to 0 (O0) and from 9 to 2 (O-all); exact McNemar p = 0.0001 and 0.016;
    - the largest prompt per run had median 17.0k tokens (O0) and 16.2k (O-all), above the old 16,384 limit;
    - resolved: O0 6 → 9; O-all 13 → 13;
    - hint effect: **+4 net** (6 fail→pass, 2 pass→fail; McNemar p = 0.29). C05 showed +7, and 0 on its 10 crash-free
      task pairs (6/10 vs 6/10).
  - **Errors that are not crashes:** O0 logged 2 context errors but 0 crashes. Both happened inside the `code_analyzer`
    sub-agent:
    - in rich_3480 and rich_4075 it was the first tool call, and its result carries the context-window error;
    - the main agent went on (one timed out, one submitted);
    - ADK's `AgentTool` runs the sub-agent in its own `Runner` without the app's compaction config, so its history is
      never compacted;
    - these were the only 2 O0 runs that called the sub-agent.
  - **The 2 O-all crashes** happened after a single step pushed the prompt from 19,460 and 15,785 tokens past 24,576.
- **Source.**
  - `results/C05_analysis.json` (0c3b204); `results/C01_smoke_timing.json`.
  - vLLM 0.19.1 `entrypoints/openai/engine/serving.py` (prompt + requested output > `max_model_len` → rejected).
  - google-adk 1.36.1 `apps/compaction.py` (`_latest_prompt_token_count`, threshold on the last observed prompt).
  - swegemma `config.py` (default `max_output_tokens` 16384) and the starter notebook (`token_threshold=14336`,
    `event_retention_size=5`).
  - Minimal CPU repro: `repro/context_window/` on `pilot/c-bottleneck` (private until submission).
- **Shown in.** `results/figures/C06_fig1_how_runs_ended.png`, `results/figures/C06_fig2_hint_effect.png`;
  `results/C06_tables.md` A1–A3, A6 (8b675fb); `REPORT.md` §17, check 1.
- **Caveats.**
  - Single runs of 12b; runs are not seeded per request, so part of the C05→C06 change is run-to-run variation.
  - The C05 flip link is post hoc.
  - With the fix, the hint's net effect (+4) is not significant on 30 tasks.
- **Status.** Supported: mechanism (code + repro) and fix (C06).

## 5. Benchmark audit: 71 of 129 dev tasks are valid in the official sandbox

- **Numbers (Kaggle, C00).**
  - The gold patch resolves 74/129. Valid (gold passes AND no patch fails): 71/129.
  - By repo: fastapi 29/67, rich 42/48, requests 0/13, httpx 0/1.
  - 3 tasks pass with no patch.
  - 34 fastapi tasks fail on a missing `inline_snapshot` (28) or `dirty_equals` (9) (3 miss both).
  - 8 requests tasks need the missing `httpbin` fixture.
  - **Reasons for all 58 invalid tasks** (`results/C00_audit.md`):

    | Category | Tasks |
    |---|---|
    | A. test module missing from the image (`inline_snapshot`, `dirty_equals`) | 34 |
    | B1. tests import the host's installed copy of requests/httpx instead of the repo (src layout); valid once the repo's `src/` is imported | 6 |
    | B2. the same import problem, and the httpbin fixture is also missing | 8 |
    | C. async test plugin missing | 2 |
    | D. environment-dependent styled output (rich) | 5 |
    | E. required test skipped on the sandbox's Python 3.12 | 1 |
    | F. tests pass with no patch | 2 |

  - **The import problem** (pilot D's finding, checked here): in all 14 requests/httpx tasks the test run imports the
    host's installed copy (requests 2.34.2, httpx 0.28.1 locally), so the patch cannot change the outcome. With the
    repo's `src/` first, 6 of them pass with the gold patch and fail without it. This covers all 4 requests tasks whose
    gold patch fails, httpx_3672, and requests_6644 (which passed with no patch on Kaggle). Controls (fastapi, rich;
    package at the repo root) import the repo's copy.
- **Source.** `results/C00_gold_check.json` (e0c8055), from `notebooks/C00_gold_check__CPU.ipynb` at 6cbc071.
  Per-task reasons in `results/C00_audit.md` and `results/C00_audit.json` (9a7d533; `pilot_c/audit_table.py`). Import
  check in `results/C00_audit_imports.json` (`pilot_c/audit_imports.py`, local Python 3.12 + wheelhouse).
- **Shown in.** `results/C00_audit.md` (one row per invalid task); `RESULTS.md` rows of 2026-10-31.
- **Caveats.**
  - The sandbox venv inherits the host's site-packages (`system_site_packages=True`), so validity depends on the image:
    73/129 locally vs 74/129 on Kaggle.
  - Valid means only that the tests can tell the gold patch from no patch; the scorer's hidden test set is a different
    set.
  - The import check ran locally (Python 3.12, the same wheelhouse), not on Kaggle. The Kaggle image has a different
    installed requests, which is why gold/no-patch outcomes differ between local and Kaggle for the same tasks. That
    difference is itself evidence that the patch has no effect.
  - Category D's causes are "likely" (IPython lexer) or "not verified" (markdown styling), per task in the table.
- **Status.** Supported for the dev set on the Kaggle image. **Pending: D** (held-out tasks).
