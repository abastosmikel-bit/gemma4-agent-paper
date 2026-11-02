# Pilot C — 12b validation rerun with `max_output_tokens` = 8192: pre-registered plan (`notebooks/C06_validation_fix_12b__L4x4.ipynb`)

Status: written 2026-11-02, before any C06 run. Frozen when committed, together with the analysis code
`pilot_c/analyze_c06.py`. The commit hash goes into `DECISIONS.md` on `paper/main`. Later changes go into §9 with date
and reason.

Known before the run: C05's results (`results/C05_validation_12b.json`, `results/C05_analysis.json`). In C05:
- 23 of 60 runs ended with `ContextWindowExceeded`.
- All 7 fail→pass tasks were tasks whose no-hint run ended that way.
- On the 10 tasks where neither C05 run crashed, the hint changed nothing (6/10 vs 6/10).

## 1. Question

C05's crashes come from the agent's sampling config. The agent requests 16,384 output tokens, so vLLM's 32,768-token
window leaves 16,384 for the prompt, only 2,048 above ADK's compaction threshold (14,336, checked on the previous
request).

With `max_output_tokens` = 8192 (prompt limit 24,576):
1. Do the crashes go away?
2. What is the location hint's effect when runs are not cut off?
3. Do the probe's numbers predict which tasks the hint rescues?
4. After compaction, where does the task-prompt marker come from (original prompt or summary), and how much of the task
   statement do the summaries keep?

## 2. Design (identical to C05 except the one setting and the added instrumentation)

- **Tasks and stages:** the 30 probe tasks in C03's order. Stage 1 is the first 15, stage 2 the remaining 15.
- **Model, agent, budget:** 12b; the official sample agent with adapters removed; 40 tool calls / 15 min / 120 s per
  command.
- **Server:** the starter's vLLM settings; concurrency 5.
- **Conditions:** O0 and O-all, rendered by `pilot_c/hints.py` as in C05, each run once.
  - Runs are not seeded per request in C05 or C06 (the sampling config has no `seed`), so "same seed" means the same
    configuration. Run-to-run variation is expected.
- **The only change:** `configs/sampling.yaml` gets `max_output_tokens: 8192`. That file is shared by the agent and its
  `code_analyzer` sub-agent. The thinking budget stays at 4,096.
  - The notebook records the output tokens each request asks for, and the analysis checks that every request asked for
    8192 (`setting_check`).
- **Sequential rule, as in C05:** if fewer than 2 tasks are discordant in stage 1, the session stops after stage 1.

## 3. Added instrumentation (`common/runtime_probes.py`; numbers in the output; summary text only under `private/`)

Per request:
- where the `Problem Statement:` marker occurs:
  - in the original prompt (a user message containing the task statement as given to the agent);
  - in a compaction summary (a message containing a recorded summary; ADK shows a summary to the model as a user
    message "For context: [model] said: …");
  - elsewhere;
- whether the original prompt is present at all;
- the requested output tokens;
- the prompt tokens the server reports;
- the exception type if the request failed.

Per compaction summary (visible text only, i.e. what later requests contain):
- share of the task statement's word 5-grams kept;
- share of its distinct words (≥ 4 characters) kept;
- whether it contains the marker.

The statement is the one given to the agent, so for O-all it includes the hint block.

The summaries themselves go to `private/runs/12b/<condition>_r1_s<stage>/summaries.jsonl` (competition-derived; not
committed).

## 4. Outcomes

- `resolved`: scorer rule (harness resolved AND non-empty patch).
- **Crash:** the run ended with `ContextWindowExceeded`.
- How a run ended: resolved / crash / time budget / tool-call budget / other unresolved.

## 5. Expectations (directional, fixed now)

- **E1.** Crashes fall in both conditions, to at most 3/30 each (C05: 14 and 9).
- **E2.** With crashes counted as failures, the hint effect (O-all − O0 resolved) is smaller than C05's +7, because the
  no-hint runs C05 lost to crashes now run to completion.
- **E3.** After compaction, the marker never comes from the original prompt (in C05 and C01 the prompt event was always
  compacted). Any marker after compaction sits in a summary.

## 6. Analyses (code: `pilot_c/analyze_c06.py`; it runs as the notebook's last cell and offline; tested on synthetic data)

- **A1.** Crashes per condition, C06 vs C05, on the same tasks. Counts, how runs ended, and an exact McNemar test per
  condition on the per-task crash indicator (C05 → C06).
- **A2.** Hint effect in C06 with crashes counted as failures: resolved per condition, fail→pass, pass→fail, exact
  McNemar. C05 is shown on the same tasks.
- **A3.** Hint effect **with crashes removed:** only tasks where neither condition's run crashed. Same numbers, for C06
  and for C05.
- **A4.** H6 replicated on C06's outcomes, with the same rules as `docs/PLAN_C05_validation.md` §7:
  - registered predictor Δ_use(L3−L0) and exploratory predictor Δ_find(L2−L0), for 12b;
  - primary set = tasks unresolved at O0; AUC ≥ 0.65; informative only with ≥ 4 positives;
  - predictor values come from C03 (`results/C06_predictors_12b.json`). The 3 tasks C03 did not complete for 12b are
    filled from `notebooks/C04_probe_followup__L4x4.ipynb` when its results exist at analysis time
    (`build_predictors(c03, c04)`); otherwise complete cases are used.
- **A5.** Compaction, per condition:
  - compacted runs; runs whose prompt event was compacted;
  - post-compaction requests by where the marker sits (original prompt / summary only / elsewhere only); requests that
    still contain the original prompt;
  - summaries and summaries with the marker;
  - distribution of the statement's 5-gram and word retention per summary.
- **A6.** Context numbers: requested output tokens seen; maximum prompt tokens per run; context errors; prompt tokens of
  the last request before the first context error.
- **A7.** Common metrics per condition (resolved, wall time, tool calls, repeated-call share, malformed share, failed
  edits, skill invocations), C06 vs C05.
- **Figures:**
  1. How runs ended, C05 vs C06.
  2. Hint effect with and without crashed runs.
  3. Statement retention per summary.

Everything in A1–A7 is descriptive except A4 (the H6 criterion).

## 7. Exclusions

None beyond the probe set. Harness errors count as unresolved, as the scorer counts them.

## 8. Cost (L4x4 hours, estimated from C05's measured task times)

- The batch model reproduces C05's four measured batches exactly. Replacing C05's 23 crashed runs (mean 339 s) by draws
  from its non-crashed runs (mean 575 s) gives batches totalling 2.33 h (p10–p90 2.19–2.47).
- Plus 0.11 h measured overhead (install, gold locations, server start, stop).
- **≈ 2.4 h (range 2.0–2.6; 2.0 if crashes persist as in C05).**
- Stopped by the sequential rule after stage 1: ≈ 1.2 h.
- Hard stop 2.9 h: a stage starts only if both of its batches fit (575 s per task × 1.3).

## 9. Deviations

None yet.
