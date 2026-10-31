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
