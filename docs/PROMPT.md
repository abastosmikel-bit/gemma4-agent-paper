# Pilot D: improved prompt

## What I changed and why

| Change | Why |
|---|---|
| Plan for **12 days** (today is 2026-10-31; paper due 2026-11-12, internal target 2026-11-09), not months. Go/no-go is decided in this session, and the full version must fit in about 5 working days. | The original prompt implied a long horizon. "100–150 tasks" is only useful if it can be finished before 9 Nov and leaves the other pilots time to use it. |
| "Valid" now means **the harness's own check passes, using the harness's own code** (`swegemma.harness.verification.verify_task` with the gold patch), in the **subprocess backend** the Kaggle starter and scorer use. Docker is a second opinion. | The prompt said "Docker if available, otherwise venvs". The harness wheel shows that the subprocess backend skips the editable install and dependency injection, and that it inherits the host's site-packages. A task that only passes in Docker is not valid for this competition. |
| Treat the host's `swegemma` wheel as the format spec, ahead of the README. | The README and the code disagree in places. For example, tasks.jsonl has no FAIL_TO_PASS field, while the loader accepts one and drops unknown keys. |
| Check the dev set's own gold patches in the same setup, on a sample, and test the src-layout hypothesis. | Other pilots measure on the dev set. If some dev tasks are unsolvable on Kaggle, everyone's numbers are noisy. The held-out set also needs a sound instrument. |
| Each task ships **intervention-ready annotations**: code/test split, F2P/P2P, each hunk mapped to its enclosing function or class **as a graph node id**, a runnable reproduction test with the module-level code it needs, and a problem-statement provenance flag (issue or PR body). The same annotator runs on the dev set locally, and its outputs are never committed. | The other three pilots are converging on "replay, inject, continue" and need exactly these fields. Adding them makes the resource useful to the paper this month, not only as a generic benchmark. |
| Repo selection adds three criteria: **flat package layout, or a src-layout fix proven to work in the subprocess backend**; zero or near-zero runtime dependencies; and a test suite that runs in seconds. | These follow from how the subprocess sandbox resolves imports. Without them, gold patches can fail for environment reasons. |
| Graph fidelity is **measured**: regenerate graphs for dev commits with our generator and diff them against the released graphs (node and edge overlap). | "Same schema" is a claim, and a fidelity number makes it verifiable (a judging criterion). |
| Embeddings: report the consequence that without an `.npz` the harness drops the "Code Intelligence Tools" prompt section. Decide whether to ship embeddings from an open model, clearly labelled as such. | "No embeddings" silently changes the agent's prompt, which is a distribution shift. |
| The research question is broadened to resource plus protocol: is a held-out, harness-faithful, intervention-annotated set a credible **Best New Resource** entry, or should it be the out-of-distribution test inside the main paper? | The user asked me to lead on the framing, and CLAUDE.md's ambition rule ranks new mechanisms above measurement-only work. |

Kept unchanged: all fixed constraints (verbatim below), the shared metrics list, the `common/` rule, and no paper prose.

---

## The prompt

### Fixed constraints (verbatim from the user, not rewritten)
- Before anything else, confirm two things and stop if either fails:
  - The repo is abastosmikel-bit/gemma4-agent-paper.
  - Kaggle access works: curl -s -o /dev/null -w "%{http_code}\n" https://www.kaggle.com/api/v1/competitions/data/list/gemma-4-developer-agent with no auth header of your own. 200 means it works, 401 means the credential isn't being added, 403 means my account hasn't accepted the rules. Don't test with datasets/list: it answers without credentials.
- The credential is a network secret: the proxy adds it for *.kaggle.com, so KAGGLE_API_TOKEN is absent on purpose. Never add the token as an environment variable.
- Work on the orphan branch pilot/d-heldout. Don't modify main or other branches, and never force-push. If the session assigns its own branch, push the orphan history to pilot/d-heldout with a plain push and tell me.
- Competition data never goes into git: no tasks, snapshots, patches, traces or task IDs. Commit only code, schemas and aggregate numbers.
- No GPU use without my OK and an hours estimate.
- Don't write paper prose.
- Finish with REPORT.md and stop: what you did, the numbers, surprises, closest prior work, a go/no-go recommendation, and the cost of the full version.

### Goal
Build and validate a pilot of a **held-out, harness-faithful, intervention-ready** task set: fresh Python bug-fix tasks from repos outside fastapi/rich/requests/httpx, in the exact competition format. Any competition agent should run on it unchanged, and the other pilots should be able to replay and inject on it. Decide go/no-go and the paper framing today.

### Steps
1. **Inventory**: python, docker (CLI and daemon), kaggle access, free disk, GitHub reachability.
2. **Format from code**: get the harness wheels (`swegemma`, `adk-eval-core`, `adk-submission`) from the starter's wheelhouse dataset. Document tasks.jsonl fields (required and optional), the snapshot layout, the graph schema, the subprocess and Docker setup sequences, and the Phase 2 pass criterion, citing module and function names. Only schema notes go in git.
3. **Instrument check**: run `verify_task` with gold patches on a sample of dev tasks in the subprocess backend (and in Docker). Test the src-layout and dependency hypotheses. Report pass and fail counts only.
4. **Prior work**: SWE-rebench, SWE-bench-Live, SWE-smith, SWE-Gym, codegraph-loc, plus any 2026 equivalents and public competition notebooks. One table, then the gap.
5. **Repos (2)**: permissive licence; pure Python; pytest; active; not in the dev set; flat layout or a proven src-layout fix; minimal dependencies; fast tests; issue-linked PRs merged after 2026-05-01. Record dates and licences.
6. **Pipeline (`common/`, no pilot-specific logic)**: mine PRs, split code and test, build the snapshot exactly like the host (truncated `git fast-export` history, branch `main`), and compute F2P/P2P. Validate with the harness's `verify_task` (gold passes, empty patch fails), in subprocess and Docker. Log the yield at every filter and the time per task.
7. **Annotations**: hunk → enclosing symbol → graph node id; a runnable reproduction test; problem-statement provenance. Run the annotator on dev tasks locally (outputs not committed).
8. **Graphs**: generate them in the released node-link schema, and measure fidelity against released dev graphs. Credit codegraph-loc if its code is reused. Embeddings: report the prompt-gating consequence and recommend.
9. **Local runner check**: load one held-out task with `swegemma.models.load_tasks` and validate it without a model, via `verify_task` and the CLI's `--skip-agent-patch`.
10. **Kaggle-side check (prepared, not run)**: a CPU-only notebook that rebuilds tasks from public GitHub and validates them in the real Kaggle image. This uses no GPU quota, but the user runs it.
11. **REPORT.md**: what was done, the numbers, surprises, GPU hours (0), prior work, framing decision with reasons, go/no-go, and the cost of the full version in days and hours. Then stop.

### Rules carried over
Shared metrics schema; reusable code in `common/`; plain-language explanations; nothing from the competition data in git; the open question about regenerated graphs (see REPORT).
