# Pilot C — 12b rollout validation: pre-registered plan (`notebooks/C05_validation_12b__L4x4.ipynb`)

Status: written 2026-11-01, before any validation run. Frozen when committed; the commit hash goes into `DECISIONS.md`
on `paper/main`. Later changes go into §10 with date and reason.
This implements `docs/PLAN.md` §8 and tests H6 of `docs/PLAN.md` §6. The probe results (`results/C03_probe.json`), which
supply the predictors, are already known. No validation outcome has been seen.

## 1. Question

Do the probe's per-task numbers predict which tasks a location hint makes 12b solve in full agent runs? This is the
only link in Pilot C from the probe (log-likelihoods, single next actions) to the outcome the main track scores.

## 2. Tasks

- The 30 probe tasks, in C03's pre-registered order (`task_ids` in `results/C03_probe.json`).
- Stage 1 = the first 15 tasks; stage 2 = the remaining 15.

## 3. Agent, model, server

- Model: `gemma-4-12b-it-qat-w4a16-ct`.
- Agent: the official sample agent with adapters removed, the same as `notebooks/C01_smoke_timing__L4x4.ipynb`. Budget:
  40 tool calls / 15 min per task, 120 s per command.
- Server: the starter's vLLM settings (`gpu_memory_utilization` 0.90; not the probe settings).
- Concurrency 5. One seed per condition.
- Freeze protection as in every GPU notebook: per-request timeouts, a `/health` watchdog, one restart, and a stop after
  the second freeze.

## 4. Conditions

| Id | Task prompt |
|---|---|
| O0 | as given |
| O-all | + gold file, gold function (dotted name, def line) and the names of the required tests, appended to the problem statement by `pilot_c/hints.py` (same renderer as C01's O-all) |

Each stage runs O0, then O-all, as separate batches on the same server.

## 5. Outcome and logged metrics

- `resolved` per task, scorer rule: the harness resolves the task AND the patch is non-empty.
- Common metrics per task: wall time, tool calls, repeated-call share, malformed-call share, failed edits, skill
  invocations, plus compaction counts (`common/metrics.py`, `common/runtime_probes.py`).

## 6. Sequential rule (`docs/PLAN.md` §8)

After stage 1, count discordant tasks (resolved under exactly one condition). With fewer than 2, the session stops: the
validation is reported as uninformative for H6, and stage 2 is not run.

## 7. Analyses (code: `pilot_c/analyze_c05.py`, written and tested on dry-run output before the run)

1. **H6 (registered in `docs/PLAN.md` §6, unchanged).**
   - Predictor: Δ_use(L3−L0) for 12b, per task, from C03 depth 1. For the 3 tasks C03's time guard cut, the value comes
     from `notebooks/C04_probe_followup__L4x4.ipynb` if that has run; otherwise those tasks drop out (complete cases).
   - Outcome, operationalized now: the AUC is computed over the tasks **unresolved at O0** (only these can flip fail →
     pass). Positive = resolved at O-all; negative = still unresolved.
   - Secondary version: over all tasks, positive = fail → pass, negative = everything else.
   - Criterion: AUC ≥ 0.65, with a 95% bootstrap CI (10,000 task resamples; resamples without both classes are dropped,
     and their count is reported).
   - Minimum for an informative AUC: ≥ 4 positives (`docs/PLAN.md` §8: ≥ 6 discordant tasks with ≥ 4 fail → pass).
     With fewer, the counts are reported and H6 is "not testable".
   - Known before the run: for 12b this predictor is near zero (median −0.2 nats, IQR −3.3 to +4.5), and C03's L0
     re-score differs by up to 5.6 nats. So a low AUC is plausible.
2. **Exploratory second predictor (coordinator's decision, 2026-11-01).** Δ_find(L2−L0) for 12b, from C03, with the same
   AUC computation. It is labelled exploratory everywhere. Reason: O-all is mostly location, and the probe found that
   location changes the find step (median +25 nats for 12b), not the use step.
3. **Descriptive.** Resolve rate per condition; exact McNemar O-all vs O0 (not powered: about 9 vs 1 discordant would be
   needed); common metrics per condition.

## 8. Exclusions

None beyond the probe set. Harness errors count as unresolved, as the scorer would count them, and are listed.

## 9. Cost (L4x4 hours, estimated)

Based on 12b's wall time per task in `notebooks/C01_smoke_timing__L4x4.ipynb`: mean 465 s, median 281 s, max 870 s
(n = 3, concurrency 3).

| Item | Estimate |
|---|---|
| one batch (15 tasks, concurrency 5), simulated by resampling C01's three 12b times | mean 0.48 h (p90 0.56 h); 0.58 h if concurrency 5 slows each task by 20% |
| install, gold locations, server start (196 s in C01), stop | 0.09 h |
| **full run (2 stages × 2 conditions)** | **≈ 2.0 h (range 1.6–2.4)** |
| stopped by the sequential rule after stage 1 | ≈ 1.05 h |
| hard stop | 2.5 h: a stage starts only if both of its batches fit before it |

## 10. Deviations

None yet.
