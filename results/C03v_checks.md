# C03v checks — edit vs correctness, paired W/L2/L0, exact-match undercount (data only, exploratory)

Source: `C03v_test_verify.json` + depth-2 S-use rows of `C03_probe.json` and `C04_probe_followup.json`; `pilot_c/c03v_checks.py`. 1-2 samples per task and cell; CIs resample tasks; no CI on fewer than 5 edits.

## K1. Does it edit, and is the edit right? (first sampled action at S-use)

| Size / condition | samples | edits gold file [95% CI] | edits that pass [95% CI] | pass rate (all samples) | what the other samples do |
|---|---|---|---|---|---|
| e4b/L0 | 60 | 35 (58% [42%, 75%]) | 11/35 (31% [12%, 53%]) | 18% | calls read_file 20, calls run_command 5 |
| e4b/L2 | 60 | 53 (88% [77%, 97%]) | 15/53 (28% [13%, 45%]) | 25% | calls read_file 7 |
| e4b/W | 54 | 40 (74% [59%, 89%]) | 20/40 (50% [29%, 71%]) | 37% | calls read_file 12, calls search_similar_code 1, calls run_command 1 |
| e4b/L5 | 54 | 46 (85% [72%, 96%]) | 30/46 (65% [46%, 83%]) | 56% | calls read_file 8 |
| 12b/L0 | 60 | 2 (3% [0%, 10%]) | 2/2 (100%) | 3% | calls read_file 33, calls run_command 18, calls get_code_neighbors 4, no tool call 3 |
| 12b/L2 | 60 | 1 (2% [0%, 5%]) | 1/1 (100%) | 2% | calls read_file 34, calls run_command 24, calls get_code_neighbors 1 |
| 12b/W | 54 | 3 (6% [0%, 13%]) | 3/3 (100%) | 6% | calls read_file 33, calls run_command 11, no tool call 5, edits another file 2 |
| 12b/L5 | 54 | 16 (30% [15%, 46%]) | 11/16 (69% [38%, 93%]) | 20% | calls read_file 25, calls run_command 5, edits another file 5, no tool call 3 |
| 31b/L0 | 60 | 0 (0% [0%, 0%]) | 0/0 (—) | 0% | calls read_file 32, calls run_command 21, edits another file 5, calls search_similar_code 2 |
| 31b/L2 | 60 | 1 (2% [0%, 5%]) | 1/1 (100%) | 2% | calls read_file 28, calls run_command 18, edits another file 11, calls get_code_neighbors 2 |
| 31b/W | 54 | 11 (20% [7%, 35%]) | 8/11 (73% [33%, 100%]) | 15% | calls read_file 26, calls run_command 16, edits another file 1 |
| 31b/L5 | 54 | 25 (46% [30%, 63%]) | 20/25 (80% [57%, 100%]) | 37% | calls read_file 18, calls run_command 6, edits another file 5 |

## K2. Paired W vs L2 vs L0 on the tasks that have all three

Per-task pass share = passing samples / 2. Δ = mean over tasks of the per-task difference (equals the difference in pass rate). Wilcoxon on the per-task differences, Holm over the three pairs within a size; McNemar on "≥ 1 sample passes"; Cochran's Q on "≥ 1 passes" across L0, L2, W.

| Size | tasks | pass rate L0 / L2 / W | tasks ≥1 pass L0 / L2 / W | pair | Δ pass rate [95% CI] | tasks up / down | Wilcoxon p (Holm) | McNemar p (only first / only second) | Cochran's Q p |
|---|---|---|---|---|---|---|---|---|---|
| e4b | 27 | 20% / 28% / 37% | 7 / 9 / 11 | W-L2 | +9% [+2%, +19%] | 4 / 0 | 0.125 (0.250) | 0.500 (2 / 0) | 0.050 |
| | | | | W-L0 | +17% [+6%, +30%] | 7 / 0 | 0.016 (0.047) | 0.125 (4 / 0) |  |
| | | | | L2-L0 | +7% [-2%, +19%] | 4 / 1 | 0.312 (0.312) | 0.500 (2 / 0) |  |
| 12b | 27 | 4% / 2% / 6% | 1 / 1 / 3 | W-L2 | +4% [+0%, +9%] | 2 / 0 | 0.500 (1.000) | 0.500 (2 / 0) | 0.135 |
| | | | | W-L0 | +2% [-4%, +7%] | 2 / 1 | 1.000 (1.000) | 0.500 (2 / 0) |  |
| | | | | L2-L0 | -2% [-6%, +0%] | 0 / 1 | 1.000 (1.000) | — (0 / 0) |  |
| 31b | 27 | 0% / 2% / 15% | 0 / 1 / 5 | W-L2 | +13% [+2%, +28%] | 5 / 1 | 0.125 (0.250) | 0.219 (5 / 1) | 0.030 |
| | | | | W-L0 | +15% [+4%, +28%] | 5 / 0 | 0.062 (0.188) | 0.062 (5 / 0) |  |
| | | | | L2-L0 | +2% [+0%, +6%] | 1 / 0 | 1.000 (1.000) | 1.000 (1 / 0) |  |

## K3. Passing edits that exact-match grading misses

| Size / condition | samples | pass | exact | pass & exact | pass, not exact | share of passes missed by exact | exact but fails | tasks ≥1 pass / ≥1 exact / pass but no exact |
|---|---|---|---|---|---|---|---|---|
| e4b/L0 | 60 | 11 | 1 | 1 | 10 | 91% | 0 | 7 / 1 / 6 |
| e4b/L2 | 60 | 15 | 2 | 2 | 13 | 87% | 0 | 9 / 2 / 7 |
| e4b/L3 | 60 | 17 | 2 | 2 | 15 | 88% | 0 | 13 / 2 / 11 |
| e4b/L4 | 54 | 22 | 6 | 6 | 16 | 73% | 0 | 12 / 4 / 8 |
| e4b/L5 | 54 | 30 | 25 | 22 | 8 | 27% | 3 | 16 / 14 / 4 |
| e4b/T | 60 | 14 | 2 | 2 | 12 | 86% | 0 | 10 / 1 / 9 |
| e4b/W | 54 | 20 | 5 | 5 | 15 | 75% | 0 | 11 / 3 / 8 |
| e4b/G-json | 60 | 13 | 0 | 0 | 13 | 100% | 0 | 10 / 0 / 10 |
| e4b/X-func | 60 | 9 | 2 | 2 | 7 | 78% | 0 | 6 / 2 / 4 |
| e4b/X-test | 60 | 15 | 0 | 0 | 15 | 100% | 0 | 9 / 0 / 9 |
| 12b/L0 | 60 | 2 | 0 | 0 | 2 | 100% | 0 | 1 / 0 / 1 |
| 12b/L2 | 60 | 1 | 0 | 0 | 1 | 100% | 0 | 1 / 0 / 1 |
| 12b/L3 | 60 | 2 | 1 | 1 | 1 | 50% | 0 | 2 / 1 / 1 |
| 12b/L4 | 54 | 2 | 2 | 2 | 0 | 0% | 0 | 2 / 2 / 0 |
| 12b/L5 | 54 | 11 | 10 | 10 | 1 | 9% | 0 | 7 / 7 / 0 |
| 12b/T | 60 | 0 | 0 | 0 | 0 | — | 0 | 0 / 0 / 0 |
| 12b/W | 54 | 3 | 2 | 2 | 1 | 33% | 0 | 3 / 2 / 1 |
| 12b/G-json | 60 | 2 | 0 | 0 | 2 | 100% | 0 | 1 / 0 / 1 |
| 12b/X-func | 60 | 0 | 0 | 0 | 0 | — | 0 | 0 / 0 / 0 |
| 12b/X-test | 60 | 0 | 0 | 0 | 0 | — | 0 | 0 / 0 / 0 |
| 31b/L0 | 60 | 0 | 0 | 0 | 0 | — | 0 | 0 / 0 / 0 |
| 31b/L2 | 60 | 1 | 0 | 0 | 1 | 100% | 0 | 1 / 0 / 1 |
| 31b/L3 | 60 | 2 | 1 | 1 | 1 | 50% | 0 | 1 / 1 / 0 |
| 31b/L4 | 54 | 3 | 1 | 1 | 2 | 67% | 0 | 2 / 1 / 1 |
| 31b/L5 | 54 | 20 | 17 | 17 | 3 | 15% | 0 | 12 / 11 / 1 |
| 31b/T | 60 | 0 | 0 | 0 | 0 | — | 0 | 0 / 0 / 0 |
| 31b/W | 54 | 8 | 4 | 4 | 4 | 50% | 0 | 5 / 3 / 2 |
| 31b/G-json | 60 | 0 | 0 | 0 | 0 | — | 0 | 0 / 0 / 0 |
| 31b/X-func | 60 | 0 | 0 | 0 | 0 | — | 0 | 0 / 0 / 0 |
| 31b/X-test | 60 | 1 | 0 | 0 | 1 | 100% | 0 | 1 / 0 / 1 |

`exact` compares the edited file with the scored gold edit, which covers only the gold function; the gold patch also changes lines outside it in 11 of 30 tasks (`outside_edits` in `C03_probe.json`), so an exact edit can still fail the tests.
