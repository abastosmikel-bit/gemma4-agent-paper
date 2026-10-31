# Pilot C — Where does a small agent break? Oracle ablations across Gemma 4 sizes

Branch `pilot/c-bottleneck` (orphan). Start with **REPORT.md**.

- `common/` — reusable, pilot-agnostic: diff parsing, AST scope mapping, gold locations, trace parser, shared metrics.
- `pilot_c/` — oracle hints (O0, O-file, O-func, O-test, O-all), task selection, Kaggle runner.
- `notebooks/` — generated Kaggle notebooks (see `notebooks/README.md`).
- `tests/` — unit tests; local end-to-end test with a mock LLM; notebook dry-run.
- `results/` — aggregate numbers only. No competition data is ever committed (see `.gitignore`).
