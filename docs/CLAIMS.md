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
  - The link to agent outcomes is not established: H6 failed in C05 (AUC 0.43), confounded by context-window crashes
    (claim 4).
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
- **Source.**
  - `results/C05_validation_12b.json`, `results/C05_analysis.json` (exploratory section; 0c3b204).
  - `results/C01_smoke_timing.json` (e0c8055).
  - Mechanism: google-adk 1.36.1 `apps/compaction.py` and `apps/llm_event_summarizer.py` (the summary is free text) and
    `flows/llm_flows/contents.py` (the summary is shown to the model as a user message `For context: [model] said: …`).
- **Shown in.** `REPORT.md` §17 (check 2); `results/C05_analysis.json` → `exploratory.by_condition`. To come:
  `C06_fig3_summary_retention.png`, table A5.
- **Caveats.**
  - The probe checks a marker string, not content. How much of the statement a summary keeps is not measured yet.
  - In the 5 runs the header was most likely re-stated by the summarizing model; that is inferred from the pattern, not
    observed.
  - 12b only in C05.
- **Status.** The "prompt event is compacted" part is supported (55/55 runs). **Pending: C06** (where the marker sits per
  request; statement retention per summary; summaries saved).

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
- **Source.**
  - `results/C05_analysis.json` (0c3b204); `results/C01_smoke_timing.json`.
  - vLLM 0.19.1 `entrypoints/openai/engine/serving.py` (prompt + requested output > `max_model_len` → rejected).
  - google-adk 1.36.1 `apps/compaction.py` (`_latest_prompt_token_count`, threshold on the last observed prompt).
  - swegemma `config.py` (default `max_output_tokens` 16384) and the starter notebook (`token_threshold=14336`,
    `event_retention_size=5`).
  - Minimal CPU repro: `repro/context_window/` on `pilot/c-bottleneck` (private until submission).
- **Shown in.** `REPORT.md` §17, check 1 (table). To come: `C06_fig1_how_runs_ended.png`, `C06_fig2_hint_effect.png`,
  tables A1–A3.
- **Caveats.**
  - The mechanism is verified in code and by the repro. C05 did not log per-request token counts (C06 does).
  - The flip link is post hoc, 7 tasks, single run.
  - The fix (`max_output_tokens: 8192`) is untested until C06.
- **Status.** Mechanism supported. **Pending: C06** (crashes with the fix; the hint effect without crashes).

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
