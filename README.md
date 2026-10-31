# Pilot D (pilot/d-heldout): held-out tasks in the Gemma 4 Developer Agent format

This branch holds scripts that **rebuild** a small held-out set of fresh Python bug-fix tasks from public GitHub repos
(sqlglot, networkx), in the exact `swegemma` task format, validated with the harness's own verification code.
No competition data lives in this branch.

- `REPORT.md`: results, surprises, go/no-go, cost (**start here**)
- `docs/PROMPT.md`: the improved pilot prompt and what changed
- `docs/FORMAT.md`: task, snapshot, graph and verification format, as the harness code implements it
- `docs/PRIOR_WORK.md`: prior work and the gap
- `common/`: reusable code
  - `kaggle_fetch.py`: Kaggle downloads through the proxy
  - `mining.py`: git miner with yield funnel
  - `snapshot.py`: dev-layout snapshots
  - `validate.py`: harness `verify_task` with empty and gold patches, subprocess or Docker
  - `testmap.py`: F2P/P2P
  - `annotate.py`: gold locations as graph node ids, plus verified reproduction tests
  - `graph_build.py`: released-schema graphs (codegraph-loc + exact released rules) and the fidelity scorer
  - `github_text.py`: issue text
  - `export_swebench.py`: SWE-bench export
  - `gharchive_issues.py`: GH Archive probe (too sparse in 2026; kept for the record)
- `pilot_d/`: the manifest of the 26 pilot tasks, declared test environments, the build/finalize scripts, the dev-sample
  audit, the graph-fidelity check, and the Kaggle notebook generator
- `notebooks/pilot_d_kaggle_cpu.ipynb`: CPU-only Kaggle notebook (dev audit in the real image + held-out rebuild)
- `results/`: aggregate numbers only (dev audit counts, graph fidelity, held-out pilot table)
