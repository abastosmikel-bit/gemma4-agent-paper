# Task format, as the harness code implements it

These are schema notes only; no competition data is included. Sources are the host's wheels
`swegemma 0.2.11`, `adk-eval-core 0.1.0` and `adk-submission 0.2.13` (Kaggle dataset
`metric/gemma-4-developer-agent-wheelhouse`), the competition's `HARNESS_README.md`,
`docker/Dockerfile.*` and `sandbox/setup.py`, and aggregate inspection of the public files.
Where the README and the code disagree, the code wins.

## 1. `tasks.jsonl`
Loader: `swegemma.models.task.load_tasks` builds a frozen `Task` dataclass and **silently drops
unknown keys**. Extra annotation fields can therefore share the file without breaking the harness.

| field | required | notes |
|---|---|---|
| `instance_id` | yes | dev convention `<repo_short>_<PR number>` |
| `repo` | yes | `owner/name`; `repo_short` = lower-cased name, used in graph and embedding file names |
| `base_commit` | yes | upstream SHA. The snapshot's own HEAD hash differs (history is re-imported). |
| `problem_statement` | yes | dev: 129/129 have one. The text is issue text or a PR description (≥24/129 contain PR-template headers). |
| `patch` | default `''` | gold code patch, never shown to the agent |
| `test_patch` | default `''` | applied in Phase 2. Its files are the pytest targets. |
| `hints_text` | default `''` | dev: empty for all 129. When non-empty it goes into the prompt and `session.state['hints']`. |
| `created_at` | default `''` | dev range 2023-07 → 2026-06; 31/129 dev tasks predate Gemma 4's stated Jan-2025 cutoff |
| `FAIL_TO_PASS`, `PASS_TO_PASS` | optional | **absent in dev**, accepted as a JSON string, list or CSV. When present they replace the test names scraped from `test_patch` as the "required nodes". |
| `environment_setup_commit` | optional | unused by Phase 2 |

**Patch text style (dev, all 129):** only `--- a/X` / `+++ b/X` headers. There are no `diff --git` or `index`
lines and no `/dev/null`: new files also use `--- a/X` with `@@ -0,0 …`. There is no trailing newline. Patches never
touch test files, and test patches never touch non-test files. `common/mining.to_dev_style` reproduces this style.

## 2. Snapshots: `snapshots/<instance_id>.tgz`
- A gzip tar rooted at `./`, containing a git repo built by `git fast-export <base>` piped into `git fast-import`. There is
  no future history, but past depth varies (dev examples: 4 commits and 6,205 commits).
- Branches are `export_ref` and `main` (checked out). `.git/config` has `user.email=agent@eval`, `user.name=Agent`.
- Lookup is `snapshots/<instance_id>.tar.gz` or `.tgz`, plus an optional dedup form (base archive + binary patch;
  `swegemma.deduplication`). `common/snapshot.py` reproduces the plain form.

## 3. Graphs: `graphs/<repo_short>_<base_commit>.json` (embeddings: same stem `.npz`)
networkx node-link JSON: `{"directed": true, "multigraph": true, "graph": {"repo_name": "<repo_short>_<base_commit>"}, "nodes": [{"id","name","text"}], "edges": [{"type":"calls","source","target","key":0}]}`.

The released generator's rules, reverse-engineered and verified (`common/graph_build.py`):

| aspect | rule |
|---|---|
| node kinds | classes and sync functions/methods only; **no module nodes, no `async def`** |
| module names | package-relative inside packages, otherwise the repo path (`src/` and non-package dirs like `docs_src/` drop out) |
| **ids** | a single "current class" variable, **reset to None (not restored) after any class body**. Methods defined after a nested class therefore become `<module>.<name>`, and closures inside methods become `<module>.<Class>.<name>`. |
| text | functions: source from `def` onward, original indentation kept, decorators excluded. Classes: header, cleaned docstring or `None`, then `@decorators` and `def sig:` with `...` bodies. |
| edges | only type `calls`; **every edge is stored in both directions** (100% reciprocal in the 7 graphs checked). Content: class↔its direct methods, plus calls resolved via module, import and local names. There are no `self.`, typed or `super` resolutions. |

Fidelity of `graph_build.py` (faithful mode) against 7 released dev graphs, from all 4 repos (`results/graph_fidelity_dev.json`):
node ids 100% recall and 100% precision in 7/7; node text exact 96–99%; undirected edge recall 84–96%; edge precision 78–98%.
The generator is codegraph-loc (Apache-2.0, D. Mantiglia) used as a library, with our id, text and edge rules on top.
`--fixed` keeps async defs, uses a proper class stack, and adds `self.`/typed calls.

**Embeddings gate the prompt.** `agent_runner` adds the "Code Intelligence Tools" prompt section only if a graph `.json`
**and** an embeddings `.npz` larger than 100 bytes exist. The `.npz` is a dict of node name → float32 vector
(`embedding_utils.load_embeddings_from_npz`, `allow_pickle=False`). Shipping a graph without an `.npz` silently removes that
section from the agent's prompt.

## 4. Phase 2 verification (`swegemma.harness.verification.verify_task`)
1. Fresh sandbox; extract the snapshot; git exclude; editable install and dependency injection (**Docker only**, see §5); write
   `/workspace/pytest.ini` + `/workspace/conftest.py` (`setup_workspace_test_config`); commit `eval_baseline`.
2. Strip protected paths from the agent patch (`test_*.py`, `*_test.py`, `.py` under `tests/ test/ testing/`,
   `conftest.py`, `pytest.ini`, `pyproject.toml`, `tox.ini`, `setup.cfg`, `.pytest.ini`, `sitecustomize.py`,
   `usercustomize.py`, `*.pth`), then apply it with a 4-pass fallback (`git apply` variants, then `patch`).
3. Reset `test_patch` files and protected files to HEAD; apply `test_patch`; refresh the test config (overwrite).
4. `PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s -m pytest <.py files of test_patch, excluding conftest> --junitxml … -p no:anyio -o timeout=0 -o python_classes="Test* *Test" -q`
5. **Resolved iff** exit code 0 **and** the JUnit report has passed > 0, failures = errors = 0, and every
   required node passed and was not skipped. Required nodes are F2P+P2P if present, else the `test_*` names added in `test_patch`.

Consequences for task construction:
- The **whole touched test file** must pass after the gold patch (P2P is implicit).
- A test patch that only touches fixtures (no `.py` test file) makes pytest receive a non-`.py` path and fail.
- The harness's `pytest.ini` takes precedence over the repo's `[tool.pytest.ini_options]`, so repo pytest settings are ignored.
- Gold patches that edit protected config files (for example `pyproject.toml`) are stripped like an agent's would be.
- The host's own task-validity rule (`harness/sample_verification.py`): baseline exit ≠ 0 **and** gold exit = 0.

## 5. Sandbox backends: what actually differs
| | Docker (`ContainerManager`, image `swebench-sandbox:latest`) | Subprocess (`SubprocessManager`; **used by the Kaggle starter**) |
|---|---|---|
| Python | image's 3.13 | host interpreter (Kaggle: 3.12, inferred from the cp312 wheels in the wheelhouse) in a per-task venv with **`system_site_packages=True`** plus `_host_env.pth` |
| repo import | `pip install -e /workspace --no-deps` plus `workspace_paths.pth` | **none**: `PYTHONPATH=<workspace>` only |
| dependencies | wheels from `wheels_dir` unpacked into site-packages: all wheels < 20 MiB, larger ones only if imported | **whatever the host env has**: `install_test_dependencies` returns early |
| network | `network_mode=none` | host network |
| `sandbox/setup.py` | required: next to `tasks.jsonl` or `snapshots/`, or set via `KAGGLE_SANDBOX_DIR` | not needed |

**Import shadowing (verified).** In both backends `/workspace` reaches `sys.path` before site-packages only for **flat layouts**:
pytest prepends the directory of the harness's root `conftest.py`. A `src/`-layout package is shadowed by any installed copy:
the host's site-packages in subprocess mode, the injected wheels in Docker. Observed in the subprocess sandbox: `import requests`
and `import httpx` resolve to site-packages, while `rich` and `sqlglot` resolve to the workspace.

**Wheel-cache gotcha (verified).** Docker-mode dependency tarballs are cached under
`$TMPDIR/swegemma_sp_cache_v8/sp_base.tar` by **name only**. Running a second task set with a different `wheels_dir` on the same
machine silently reuses the first set's wheels. Use a separate `TMPDIR` per wheel set.
