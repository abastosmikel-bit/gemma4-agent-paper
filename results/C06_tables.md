# C06 validation rerun (max_output_tokens 8192) — tables (data only)

Plan: `docs/PLAN_C06_validation_fix.md`. Tasks run in both conditions: 30. Stopped: None. Session: 2.708 h. Setting check (requested output tokens seen): [8192] → OK.

## A1. How runs ended, C05 vs C06 (same tasks)

| Condition | Run | resolved | context_crash | time_budget | tool_call_budget | unresolved_other | crash McNemar (C05→C06) |
|---|---|---|---|---|---|---|---|
| O0 | C05 | 6 | 14 | 3 | 4 | 3 |  |
| O0 | C06 | 9 | 0 | 9 | 5 | 7 | 14 vs 0, p=<0.001 |
| O-all | C05 | 13 | 9 | 3 | 2 | 3 |  |
| O-all | C06 | 13 | 2 | 5 | 7 | 3 | 7 vs 0, p=0.016 |

## A2–A3. Hint effect (O-all vs O0)

| Run | Tasks | crashes | O0 resolved | O-all resolved | fail→pass | pass→fail | McNemar p |
|---|---|---|---|---|---|---|---|
| C06 | 30 | all tasks (crash = failure) | 9 | 13 | 6 | 2 | 0.289 |
| C05 | 30 | all tasks (crash = failure) | 6 | 13 | 7 | 0 | 0.016 |
| C06 | 28 | crashes removed | 9 | 13 | 6 | 2 | 0.289 |
| C05 | 10 | crashes removed | 6 | 6 | 0 | 0 | — |

## A4. Probe predictors of fail→pass (C06 outcomes)

| Predictor | Set | n | positives | AUC [95% CI] | criterion ≥ 0.65 |
|---|---|---|---|---|---|
| H6_d_use_L3-L0 (pre-registered (H6)) | primary_unresolved_at_O0 | 19 | 6 | 0.2692 [0.0452, 0.5556] | False |
| H6_d_use_L3-L0 (pre-registered (H6)) | secondary_all_tasks | 27 | 6 | 0.2857 [0.0652, 0.5476] | — |
| x_d_find_L2-L0 (exploratory) | primary_unresolved_at_O0 | 20 | 6 | 0.4524 [0.1562, 0.7647] | False |
| x_d_find_L2-L0 (exploratory) | secondary_all_tasks | 28 | 6 | 0.5379 [0.2604, 0.8076] | — |

## A5. Compaction: where the task-prompt marker sits after compaction; summary retention

| Condition | runs compacted | prompt event compacted | requests after | marker: original prompt | summary only | elsewhere only | original prompt present | summaries (with marker) | 5-gram recall median [IQR] (max) | word recall median |
|---|---|---|---|---|---|---|---|---|---|---|
| O0 | 30/30 | 30 | 759 | 0 | 25 | 0 | 0 | 115 (2) | 0.0 [0.0, 0.0054] (0.5) | 0.3393 |
| O-all | 28/30 | 28 | 713 | 0 | 38 | 0 | 0 | 86 (3) | 0.0028 [0.0, 0.0065] (0.0545) | 0.3232 |

## A6. Context numbers

| Condition | requested output tokens | max prompt tokens per run, median [IQR] (max) | context errors | prompt tokens before first error |
|---|---|---|---|---|
| O0 | [8192] | 16999.0 [15732.25, 18635.0] (24462.0) | 2 | [23882, 24462] |
| O-all | [8192] | 16185.0 [15623.25, 17838.5] (19553.0) | 2 | [15785, 19460] |

## A7. Common metrics

| Run | Condition | runs | resolved | wall s mean | tool calls mean | repeat share | malformed share | failed edits | skill calls |
|---|---|---|---|---|---|---|---|---|---|
| C06 | O0 | 30 | 9 | 728.133 | 35.5 | 0.167 | 0.008 | 33 | 0 |
| C06 | O-all | 30 | 13 | 655.807 | 33.467 | 0.177 | 0.012 | 13 | 0 |
| C05_same_tasks | O0 | 30 | 6 | 482.15 | 23.6 | 0.114 | 0.004 | 6 | 0 |
| C05_same_tasks | O-all | 30 | 13 | 486.8 | 21.933 | 0.113 | 0.013 | 6 | 0 |
