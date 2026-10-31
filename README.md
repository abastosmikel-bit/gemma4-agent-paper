# Pilot D (pilot/d-heldout): held-out tasks in the Gemma 4 Developer Agent format

Scripts that **rebuild** a small held-out set of fresh Python bug-fix tasks from public
GitHub repos, in the exact `swegemma` task format, validated with the harness's own
verification code. No competition data lives in this branch.

- `docs/PROMPT.md`: the improved pilot prompt and what changed
- `docs/FORMAT.md`: task, snapshot and graph format as the harness code implements it
- `common/`: reusable code (Kaggle fetch, task I/O, patch split, snapshot builder, graph builder, validator, annotator)
- `pilot_d/`: the mining configuration for this pilot
- `REPORT.md`: results and the go/no-go recommendation
