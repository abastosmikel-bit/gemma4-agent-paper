# RESULTS register

Every reported number points to what produced it: notebook (path + Kaggle version) or script, the git commit
of that code, and the committed results file. Status: measured (real runtime) · local (measured outside Kaggle)
· estimated. A number not in this register is not reported. Pull before editing.

| Date | Pilot | Number | Meaning | Produced by (notebook version / script) | Code commit | Results file | Status |
|---|---|---|---|---|---|---|---|
| 2026-10-31 | C | 91/129, 68/129 | gold patch touches exactly 1 source file / exactly 1 function or class | `pilot_c/gold_stats.py` | 39a3577 | `results/gold_stats_dev129.json` (pilot/c-bottleneck) | local |
| 2026-10-31 | C | 32/129 | tasks whose verification test files are all new | `pilot_c/gold_stats.py` | 39a3577 | `results/gold_stats_dev129.json` | local |
| 2026-10-31 | C | 129/129 | required-test-name rule equals the scorer's function | `pilot_c/check_test_names.py` | 39a3577 | (stdout, re-runnable) | local |
| 2026-10-31 | C | 73/129 | gold patch resolves in a LOCAL subprocess sandbox (py3.13) | local gold check loop (`pilot_c/kaggle_runner.gold_check`) | 97e9744 | `results/gold_check_local_summary.json` | local |
| 2026-10-31 | C | 21/129 | hidden test needs a new name/message absent from the issue (heuristic) | `pilot_c/info_checks.py spec` | d507550 | `results/info_spec_dev129.json` | local |
| 2026-10-31 | C | 5.3 / 4.5 bits | median location information of a file hint / a function hint given the file (82 tasks) | `pilot_c/info_checks.py bits` | d507550 | `results/info_location_bits_dev129.json` | local |
| 2026-10-31 | C | 5/72 | gold-passing tasks that also pass with NO patch, LOCAL sandbox (67 valid) | local loop over `pilot_c/kaggle_runner.gold_check(baseline=True)` | fb5ef4c (code) | `results/no_patch_check_local_summary.json` (211a36c) | local |
| 2026-10-31 | C | 9/10 | local tasks whose canonical edit equals the gold patch (10th differs only by its out-of-function gold changes) | `pilot_c/probe.py` validation (CPU) | 8cea51f | (re-runnable check; see PLAN §11 item 2) | local |
| 2026-10-31 | C | 0 vs 15 | compaction events in the harness trace vs seen by the summarizer probe (mock LLM, ADK compaction triggered on purpose) | `notebooks/C01_smoke_timing__L4x4.ipynb` papermill dry run | 8cea51f | (dry run only, not a result about real models) | local (mechanism check) |
| 2026-10-31 | C | ≈0.29 L4x4 h | quota used by the failed first run of the probe (stopped after ~17.5 min: 31b HTTP 500, then e4b start failed on leaked GPU memory); 0 cells scored | `notebooks/C03_probe__L4x4.ipynb` Kaggle run (coordinator's log) | 168d115 plan; notebook before 1257629 | (log only; partial `C03_probe.json` has no results) | measured (operational) |
