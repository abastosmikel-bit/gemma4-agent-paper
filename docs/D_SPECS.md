# D0 / D1 / D2: held-out re-checks of the claims (specs for pricing)

Owner: pilot D (`pilot/d-heldout`). Version 1, 2026-11-02. Written so pilot C can price D1/D2 and, if the coordinator
approves, build them as variants of C's notebooks. **No GPU has been used for D, and none will be without the
coordinator's OK.**

Naming. D0, D1 and D2 are pilot D's notebooks, under the notebook naming rule. They are unrelated to the "D1–D3
directions" in `REPORT.md` §8.5 on `pilot/c-bottleneck`.

## What each one re-checks, and why
`docs/HISTORY.md` says pilot D is needed to re-check **claims 1, 3 and 5** out of distribution. The coordinator's decision
of 2026-10-31 says claims tuned on the dev tasks must be re-checked on tasks none of the pilots tuned on.

| notebook | accelerator | re-checks (`docs/CLAIMS.md`) | built by |
|---|---|---|---|
| `notebooks/D0a_heldout_fetch__CPU.ipynb` then `notebooks/D0b_heldout_export__CPU.ipynb` | CPU; D0a Internet ON without competition data, D0b Internet OFF with it | **claim 5** (validity audit) on held-out tasks; D0b's output is the input of D1/D2 | pilot D (`pilot/d-heldout`), ready |
| `notebooks/D1_heldout_probe__L4x4.ipynb` | L4x4 | **claims 1 and 3**, depth 1 and depth 2 | pilot C (a C03/C04 variant reading D0's output) |
| `notebooks/D2_heldout_rollouts_12b__L4x4.ipynb` | L4x4 | **claims 2 and 4** (compaction erases the task; the 8192 fix prevents crashes), plus the held-out solve rate of the paper's agent configuration | pilot C (a C06 variant) |

Why D2 is O0 only: C06 showed that, without crashes, the hint effect is +4 net on 30 dev tasks (p = 0.29). A held-out
O0-vs-O-all comparison at N ≈ 24 cannot test it, so O-all is an add-on, not part of the main version. Claims 2 and 4 are
measured in every run, whatever the condition.

## D0a + D0b: the held-out export (CPU, no GPU)
- **Why two notebooks:** Kaggle refuses Internet for a notebook with this competition attached, even on CPU.
  - D0a (Internet ON, nothing attached) downloads everything external into its output: pool, snapshots, issue text,
    wheels for what the image lacks, codegraph-loc, and the bge-small model.
  - D0b (Internet OFF, competition + wheelhouse + D0a's output attached) installs with `--no-index` only and does the
    rest.
  - **The output layout is unchanged:** D1/D2 attach D0b's output and read `heldout_export/` (Level A) and
    `D0_summary.json`.
- **What it does.**
  - Rebuilds pilot D's pool from public GitHub, using the commits in `pilot_d/manifest.json`.
  - Validates every task in the real Kaggle image with the harness's own `verify_task`: gold passes, empty patch fails.
  - Fetches issue text from the GitHub API, computes F2P/P2P, gold locations and verified reproduction tests.
  - Writes released-rule graphs and substitute embeddings.
  - Output: `docs/PROBE_INPUT.md` Level A + `heldout_meta.jsonl` + `EXPORT.json`. Summary: `D0_summary.json`.
- **Runs:** both in the starter's pinned Python 3.12 environment. D0a ≈ 1–3.5 h; an optional Kaggle Secret
  `GITHUB_TOKEN` avoids waiting for the API's hourly reset. D0b ≈ 2–3 h.
- **Local papermill dry runs** (fake `/kaggle`, 2 repos × 2 tasks, GitHub API stubbed in D0a):
  - D0a passes 10/10 checks, including an offline install + embedding self-check.
  - D0b passes 10/10 checks inside a network namespace with a socket/DNS guard, with **0 network attempts**; the guard's
    positive control logs and blocks a lookup.
  - Scripts: `tests/d0a_dryrun.sh`, `tests/d0b_dryrun.sh` (`pilot/d-heldout`).
- **Local check of the format against C's own code, unmodified:** C's `pilot_c/build_gold.py`, `select_tasks.eligible` and
  `probe.build_probe_record` (`pilot/c-bottleneck` 71c6622) were run unmodified on the 101-task local export.
  - Eligibility: 61/101, and pilot D's own mirror of the rule agrees on 101/101.
  - Probe records: 51 build `ok`; 10 fail C's 150-line read-window rule; 40 are not eligible.
  - Script: `pilot_d/c_compat.py` (`pilot/d-heldout`). `build_gold.py` resumes from an existing output file, so delete
    it before re-running on a changed export.

## Task set (shared by D1 and D2), fixed before any GPU run
Pool = D0 tasks that pass all of:
1. **valid in the Kaggle image** (gold passes, empty patch fails; subprocess backend);
2. C's `probe.build_probe_record` returns `ok` (C's eligibility rule + canonical edit inside the 150-line read window);
3. the problem statement is a real **issue** (`problem_statement_source = issue#…`), not a PR description, so it carries
   no fix hints;
4. the no-patch run does not hit the 300 s verification timeout (one hang-bug task did: each failed attempt costs 300 s);
5. at least 2 pool tasks from the same repo (G-null and the cross-task "wrong" controls need a same-repo partner);
6. the task's graph has ≤ 20,000 nodes. This rule exists because of the harness's embedding cache:
   - it is an LRU of 50,000 entries, filled with node ids **and** node texts;
   - above ~25k nodes the ids are evicted, and every per-node lookup in `get_graph` becomes a linear scan, so loading
     is O(N²);
   - measured: 1.2 s for an 8.1k-node graph vs > 5 min for sympy's 39.5k (not finished);
   - every graph tool call (D1's graph cells, D2's agent tools) would stall on such a task.

   This excludes sympy from D1/D2. It stays in the export and in the claim-5 audit.

**Selection:** a seeded (20261102), repo-stratified random sample of **N = 24**, at most 12 per repo (half of N), from at
least 3 repos. If the pool is smaller, take all of it and price per task (see the formula below).
Script: `pilot_d/select_d_tasks.py` (`pilot/d-heldout`). Its local dry run selected 22 tasks from 3 repos, using git issue
references in place of issue text.
**Pool estimate (local, before the API links PR-only fixes to issues, which can only add tasks):**
  - 101 valid tasks from 5 repos: sqlglot 46, tomlkit 20, networkx 16, sympy 11, pyparsing 8.
  - 51 probe-ready by C's code: sqlglot 21, tomlkit 15, networkx 8, sympy 7.
  - After rules 3–6, with issue links found in git alone: 30 (sqlglot 20, networkx 5, tomlkit 5).
  - With the cap: **22 today**, up to 32 once D0's API step links the 13 probe-ready tasks that have no git issue
    reference yet (tomlkit 10, networkx 3).
  - **Expect N = 24.** Details: `results/heldout_pool_local.json` on `pilot/d-heldout`.

## D1: held-out information-ladder probe (claims 1 and 3)
- **Sizes:** e4b, 12b, 31b (C04's set).
- **Depth 1, 15 cells per task and size:**
  - S-find (8): L0, L1, L2, W, G-json, G-null, X-func, X-graph;
  - S-use (7): L0, L2, W, T, L5, G-json, G-null.

  This is C's depth-1 core plus X-graph (find) and T (use), so every depth-1 number in claims 1 and 3 has a held-out
  counterpart.
- **Depth 2, sampled first action, 11 samples per task and size:**
  - S-find: L0, L2, G-json, X-graph, G-null, 1 sample each. These give "reads the gold file / function" (claims 1 and 3,
    depth-2 numbers).
  - S-use: L0, L2, L5, 2 samples each. These give P(edit now) and on-target / exact edits (31b's "defers edits" finding).
  - "Solves" for sampled edits is checked on CPU against D0's export (a C03v-style check, no GPU).
- **Contexts:** captured with the real agent loop, as in C03. Task prompts contain the "Code Intelligence Tools"
  section because D0 ships embeddings (see below), so prompts have the same shape as on dev.
- **Replication criteria (proposed; C freezes them in its plan before the run):**
  - **R1, claim 1 / H1:** Δ_find(L2−L0) − Δ_use(L2−L0) > 0 for each size; Holm-adjusted p < 0.05. Dev: supported for
    all three, p < 0.001.
  - **R2, claim 1:** median Δ_use(W−L0) > 0, and median Δ_use(L5−L0) > median Δ_use(W−L0), for each size.
    Dev: W +11 to +15, L5 +29 to +42.
  - **R3, claim 3, find:** median Δ_find(G-json − G-null) > 0, and |median Δ_find(G-json − X-graph)| < median
    Δ_find(L2 − X-func), for each size. Dev: +4.6 to +9.8 vs +1.0 to +1.5 vs +11 to +20.
  - **R4, claim 3, use:** median Δ_use(G-null − L0) ≥ median Δ_use(G-json − L0) − 2 nats, i.e. graph content adds
    nothing at the use step.
  - **R5, depth 2 (descriptive):** "reads the gold function" at L0 vs L2, and "reads the gold file" at L0 → G-json →
    X-graph → G-null, per size. Compared with dev (claims 1 and 3), no test.

## D2: held-out rollouts, 12b, C06 configuration (claims 2 and 4; held-out solve rate)
- **Agent:** the official sample agent at 12b, exactly as in C06: `max_output_tokens` 8192 and C06's instrumentation
  (where the task-prompt marker sits after compaction, statement retention in summaries, failed-edit replay).
  40 calls / 15 min, concurrency 5, 1 seed.
- **Condition:** O0 on the 24 D1 tasks.
- **Measures:**
  - resolved (non-empty patch only);
  - how runs ended (`ContextWindowExceeded` count; **claim 4**: expected ≈ 0 with the fix);
  - compaction frequency, share of post-compaction requests that still contain the original statement, summary
    retention (**claim 2**: dev 0/1,472 and median 5-gram retention 0%);
  - failed edits after compaction;
  - the shared metrics (wall time, tool calls, repeated-call share, malformed calls) and the share of
    `search_similar_code` calls (that tool runs on substitute embeddings, see below).
- **Criteria (proposed):**
  - **R6, claim 2:** 0 post-compaction requests contain the original statement in held-out runs that compact.
  - **R7, claim 4:** at most 1 of 24 runs ends in `ContextWindowExceeded`.
  - Solve rate: reported with a Wilson CI. No test against dev, because the repos differ.

## Versions and units
C prices these with its measured rates. My estimates use C's per-unit numbers: REPORT "D estimates", C04's 1.41 h, and
C06's 2.71 h for 60 runs.

| version | D1 | D2 | units | estimate (L4x4 h) |
|---|---|---|---|---|
| **Main (≈3 h)** | 24 tasks × 3 sizes: depth 1 (15 cells) + depth 2 (11 samples) | 12b, O0, same 24 tasks | 1,080 depth-1 cells; 792 depth-2 samples; 24 rollouts | D1 ≈ 1.2 + 0.4 = 1.6; D2 ≈ 1.2; **total ≈ 2.8** (range 2.4–3.4) |
| **Fallback (≈1.2 h)** | 24 tasks × 3 sizes, depth 1 only (15 cells) | none (claims 2/4 stay dev-only, labelled so) | 1,080 cells | **≈ 1.2** (range 1.0–1.5) |
| Floor | 16 tasks × 3 sizes, depth 1 only | none | 720 cells | ≈ 0.9 |

**Per-task formula** (main version): ≈ 0.42 + 0.098 × N L4x4 h, i.e. N = 20 → ≈ 2.4 h, N = 24 → ≈ 2.8 h.
**Fallback:** ≈ 0.32 + 0.036 × N.

How the estimates are built (to be re-priced by C):
- **D1, fixed per session:** 0.32 h (3 server starts, 31b words step, install and stops).
- **D1, depth 1:** 0.027 h per task for 13 cells × 3 sizes, scaled to 15 cells, gives ≈ 0.031 h per task; plus 0.005 h
  per task for records and capture.
- **D1, depth 2:** C's full − depth-1 rates (0.10 − 0.06 h per task for 26 samples × 3 sizes) give ≈ 0.0015 h per sample
  for 3 sizes, so 11 samples ≈ 0.017 h per task.
- **D2:** C06 used 2.71 h for 60 runs, ≈ 0.045 h per run all-in. 24 runs ≈ 1.1 h, plus the part of setup that does not scale with runs ≈ 1.2 h.
- **Why the upper range:** held-out test files are larger (sqlglot), so verification and reads may run longer than on dev.

**Add-ons** (only if the main version prices under budget):
- D2 O-all on the same 24 tasks, ≈ +1.1 h (exploratory hint effect, direction only);
- D1 or D2 extra tasks, ≈ +0.05 h (D1 full) and +0.045 h (D2) per task.

## The missing-embeddings confound: fixed in D0's export
- **Cause.** The harness adds the "Code Intelligence Tools" section to the task prompt only when
  `embeddings/<repo>_<base_commit>.npz` (> 100 bytes) exists next to the graph (`build_agent_prompt`, swegemma 0.2.11).
  The released embeddings come from an undisclosed Google-internal model, so they cannot be regenerated for new tasks.
  Without a file, held-out prompts would lack a section that dev prompts have.
- **Fix in D0.**
  - D0 ships a disclosed substitute: `BAAI/bge-small-en-v1.5` (MIT; safetensors; no remote code), one vector per graph
    node, computed on "node id + node text" (`common/embed_nodes.py`, cached across commits).
  - Checked with the harness's own prompt builder (`pilot_d/check_prompt_parity.py`): the section is present for **101/101** held-out tasks with the substitute file and **0/101** without it. The graph tools answer on the gold node in 8/8 sampled tasks (2 per repo); sympy's 11 were skipped because of graph size (rule 6).
  - The same check passes on a dev task with its released file (positive control).
  - D0 repeats the check on Kaggle and writes it into `D0_summary.json`.
- **What still differs, and how D1/D2 handle it.**
  - `search_similar_code` answers differently. On 4 dev graphs the substitute shares 17% of each node's top-10
    neighbours with the released vectors (random 0.9%; gte-modernbert 18%), and top hits score ≈ 0.93 instead of ≈ 0.999.
  - A linear map into the released geometry *lowered* agreement for every model tried (leave-one-repo-out), so none is
    used. bge was chosen over gte for speed: 22 vs 5 texts/s on 4 CPUs, measured.
  - **D1 is unaffected beyond prompt shape.** Its graph cells use `get_code_subgraph` / `get_code_neighbors`, which read
    only the graph.
  - **D2** reports the share of `search_similar_code` calls. If it is not negligible, rollout differences between dev
    and held-out may partly reflect this tool.
- **Evidence:** `results/embedding_parity.json`, `docs/FORMAT.md` §3 (pilot/d-heldout).

## What the paper may claim from D0–D2
Replication or non-replication of claims 1, 3 and 5 (and 2, 4 with D2) on N ≈ 24 post-cutoff tasks from repos outside
the dev set: single run, labelled as such, with the repos named. Every number goes into `RESULTS.md` first.
