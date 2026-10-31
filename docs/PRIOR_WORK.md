# Prior work for Pilot D (held-out tasks)

Collected 2026-10-31 by a Sonnet scout; links were checked by the scout. Items marked **UNVERIFIED** were not readable (Kaggle
pages render titles only). Merge this into `research/novelty-map.md` on main.

## Task-set resources
| resource | mining / validation | freshness | graph | function-level labels | separate repro test | oracle hints |
|---|---|---|---|---|---|---|
| SWE-bench-Live (NeurIPS'25 D&B, arXiv 2505.23419) | issue to PR via RepoLaunch, Docker, F2P/P2P | claims monthly; HF dump to 2025-08 | no | no | no | no |
| SWE-rebench V1/V2 (2505.20411, 2602.23866) | GH Archive issue to PR, LLM-built env, Docker F2P/P2P | V1 monthly splits; V2 static (2025-10) | no | no | no | no |
| SWE-Gym (2412.21139) | SWE-bench recipe, 11 repos | static (2024) | no | no | no | no |
| SWE-smith (2504.21798) | synthetic bug injection | no longer updated | no | no | no | no |
| R2E-Gym | commits plus LLM-written issues | static | no | partial | no | no |
| SWE-MERA (2507.11059) | 2025 Python issue to PR, Docker | to 2025-06 | no | no | no | no |
| Loc-Bench / LocAgent (2503.09089) | 560 issues | to early 2025 | method graph | **yes** | no | no |
| **codegraph-loc** (Kaggle'26, Apache-2.0, D. Mantiglia) | dev-repo commits plus SWE-bench Lite and pymatgen held-out sets; no gold execution | to Sep 2026 | **yes, competition schema** | **yes** | no | no |
| **ORACLE-SWE** (2604.07789) | oracle signals on Verified, Live and Pro | n/a | no | location | **F2P test as a signal** | **yes: 5 signals appended to the prompt** |

## Inside this competition (public)
- **OOD-45** (`rodrigospalma/ood45-bugfix-split`): "Leakage-Audited Bug-Fix Tasks for Gemma 4", a post-release split in competition format. **UNVERIFIED**; this is the closest direct competitor.
- `fjcarmona78/gemma4-agent-noise-study`: 216 local tasks converted from SWE-rebench V1/V2 plus OOD-45. No oracle injection.
- `dreamyang-liu/kaggle-gemma-eval`: local scorer replica, 106/129 dev gold patches pass. `usp787/Gemma4_paper_track`: 111/129.
- Graph audits (taken): codegraph-loc, gemma4-hub-prior-audit, gemma4-tool-surface-repro, atlas-gemma4-paper-track, callset, graphfaultbench.

## Stage-attributable evaluation (injecting information into a run)
- ORACLE-SWE (2604.07789): location, repro test, regression test, execution context and API usage. The repro test helps most.
- Loc2Repair (2606.30963): file-level gold localization, 44.7% → 52.4% on Verified.
- From Finding to Fixing (2610.25826): better localization does not reliably raise repair success.
- Test-overfitting on SWE-bench (2511.16858): revealing the gold tests.

## Dating
Gemma 4 was released 2026-03-31 (E2B, E4B, 31B) and the 12B on 2026-06-03. The model card states a training cutoff of
**January 2025**. All pilot tasks were merged between 2026-05 and 2026-10, so they are post-cutoff and post-release.

## Gap this pilot can honestly claim
No public resource found combines: (1) validation with **the competition harness's own `verify_task` in the scorer's
subprocess backend**; (2) graphs that reproduce the **released generator exactly**, its bugs included (100% node ids on 7/7
released graphs); (3) per-task **verified** reproduction tests and gold locations in the graph's id space, ready for
injection; (4) rebuild-from-public scripts with no redistribution. Each ingredient exists separately (codegraph-loc: graphs
and labels; ORACLE-SWE: oracle signals; OOD-45 and the noise-study: extra tasks). The combination, and the fidelity to the
harness, is the delta.
