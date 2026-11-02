# Pilot C — D1 held-out information-ladder probe: pre-registered plan (`notebooks/D1_heldout_probe__L4x4.ipynb`)

Status: written 2026-11-02, before any D1 run and before D0b's output exists. Frozen when committed, together with the
selection code `pilot_c/heldout.py`, the analysis code `pilot_c/analyze_d1.py` and the dev reference
`results/D1_dev_reference.json`. The commit hash is written into the notebook (`PLAN_COMMIT`) and into `docs/HISTORY.md` on
`paper/main`. Later changes go into §10 with date and reason.

Spec this follows: `docs/D_SPECS.md` on `paper/main` (02381e4), pilot D. Known before the run: every dev result of C03,
C04 and C03v (`docs/CLAIMS.md`, claims 1 and 3). Nothing is known about the held-out tasks beyond pilot D's local pool
estimate (`results/heldout_pool_local.json` on `pilot/d-heldout`).

## 1. Question

Do claims 1 and 3 hold on tasks none of the pilots tuned on (held-out repos, post-cutoff fixes)?
- Claim 1: naming the location helps the model **find** the code much more than it helps it **write** the fix; writing
  needs content (words help, the diff helps more).
- Claim 3: a code graph helps finding by its content, and the symbol it is about matters less than a named location;
  at the edit step graph content adds nothing.

## 2. Design

- **Tasks:** pilot D's held-out export (D0b output), selected by `pilot_c/heldout.py`, i.e. `docs/D_SPECS.md` rules 1–6:
  1. valid in the Kaggle image (the export holds valid tasks only);
  2. probe-ready by C's own code: `select_tasks.eligible` without its dev-repo filter, and `probe.build_probe_record` ok;
  3. problem statement from an **issue** (`problem_statement_source` starts with `issue#`). PR-body statements often
     describe the fix and would leak "where" and "what" into L0; those tasks still count in pilot D's validity audit;
  4. no 300 s hang without a patch (validation rows if attached; else pilot D's known hang tasks);
  5. at least 2 pool tasks from the same repo;
  6. graph ≤ 20,000 nodes. **sympy is also excluded by name** (its graph stalls the harness's graph tools).

  Then a seeded (20261102), repo-stratified sample of N = 24, at most 12 per repo. The sampling code is pilot D's
  (`pilot_d/select_d_tasks.py`, 04dd8d1), unchanged; `tests/test_heldout_select.py` checks equality on synthetic data.
  If fewer than 24 tasks qualify, all are used. The selection is written to `D_selection.json` (ids and counts).
- **Sizes and order:** 31b (writes the words for W and L5), then e4b, then 12b. One vLLM server per size, with C03/C04's
  probe-server settings (`gpu_memory_utilization` 0.75, `--max-num-batched-tokens 1024`).
- **Contexts:** captured with the real agent loop against the capture server, as in C03 (the official sample agent,
  40 calls / 15 min). The held-out export ships substitute embeddings, so the task prompt has the same "Code Intelligence
  Tools" section as on dev.
- **Depth 1 (log p of the correct action, nats), 15 cells per task and size:**
  - S-find (8): L0, L1, L2, W, G-json, G-null, X-func, X-graph;
  - S-use (7): L0, L2, W, T, L5, G-json, G-null.
- **Depth 2 (sampled first action; main version only), 11 samples per task and size:**
  - S-find: L0, L2, G-json, X-graph, G-null, 1 sample each;
  - S-use: L0, L2, L5, 2 samples each.
- **Rungs and controls** are C's, unchanged (`pilot_c/probe.py`): words by 31b with the same prompt and leak check;
  X-func and X-graph = another function in the gold file, matched on length; G-null = another selected task's gold
  subgraph (same repo first) with no node in this task's gold module, matched on length.
- **Order inside a size:** depth 1 first, then depth 2. Depth 2 of 31b and e4b starts only if 20 min per remaining size
  are left, so depth 1 of every size runs before any depth 2 can crowd it out.
- **Fallback version:** the same notebook with `DEPTH2 = False` (depth 1 only). R5 is then not run.

## 3. Outcomes

- Depth 1: `logp` per cell (sum over the target turn's tokens). Δ_state(A−B) = logp(A) − logp(B) per task.
- Depth 2: S-find `hit_file`, `hit_func`, `followed_wrong`; S-use `edit_gold_file` (edits the gold file now), `applies`,
  `on_target`, `exact`.
- Whether sampled S-use edits **pass the tests** is checked on CPU after the run by
  `notebooks/D1v_test_verify__CPU.ipynb` (exploratory, §6).

## 4. Replication criteria (frozen; from `docs/D_SPECS.md`, made exact)

A size is **evaluable** for a criterion if at least 12 tasks have every cell the criterion needs. A criterion
**replicates** if it holds for all three sizes; otherwise the verdict says how many sizes hold and how many were not
evaluable. Medians are over tasks; CIs are 95% percentile bootstrap (10,000 resamples).

- **R1 — claim 1 / H1 (the dev test, unchanged).** Per size: median Δ_find(L2−L0) − Δ_use(L2−L0) > 0, median
  Δ_use(L2−L0) < median Δ_find(L2−L0), and the Holm-adjusted p of a two-sided Wilcoxon signed-rank test on the per-task
  difference < 0.05 (Holm within size over {Δ_find > 0, Δ_find − Δ_use > 0}, as on dev). Dev: holds for all three sizes,
  p < 0.001.
- **R2 — claim 1, content.** Per size, on tasks with L0, W and L5: median Δ_use(W−L0) > 0 and median Δ_use(L5−L0) >
  median Δ_use(W−L0). Dev: W +11 to +14, L5 +29 to +42.
- **R3 — claim 3, find.** Per size: median Δ_find(G-json−G-null) > 0, and |median Δ_find(G-json−X-graph)| < median
  Δ_find(L2−X-func). Dev: +4.6 to +9.8; +1.0 to +1.5 vs +11 to +20.
- **R4 — claim 3, use.** Per size: median Δ_use(G-null−L0) ≥ median Δ_use(G-json−L0) − 2 nats. Dev: holds for all
  three sizes (G-json − G-null: e4b +1.3, 12b −1.9, 31b −4.4).
- **R5 — depth 2, descriptive (no test).** Per size: "reads the gold function" at S-find L0 vs L2; "reads the gold file"
  at L0 → G-json → X-graph → G-null; S-use edit-now, applies, on-target and exact at L0, L2, L5. Shown next to dev.

The dev column of every table comes from the same code run on C03 + C04 (`results/D1_dev_reference.json`): all four
criteria hold on dev for all three sizes.

## 5. Analysis (code: `pilot_c/analyze_d1.py`; the notebook's last cell; tested on synthetic data)

- R1–R4 tables with held-out and dev side by side, verdicts, R5 tables, every depth-1 contrast (descriptive), cell
  health (failed cells by reason, score modes).
- Figures: `D1_fig1_criteria.png` (the criteria's medians with CIs, held-out filled vs dev open), `D1_fig2_depth2.png`
  (S-find gold-file reads and S-use exact edits per cell).
- Outputs: `D1_analysis.json`, `D1_tables.md`, the two figures. Numbers only.

## 6. Exploratory (not criteria)

- `notebooks/D1v_test_verify__CPU.ipynb` (CPU, after D1): applies each sampled S-use edit alone and runs the scorer's
  verification, as C03v did. Reports per size and rung: edit rate, pass rate, pass given an edit, and passing edits that
  are not exact. There is no threshold analysis: D1 samples only L0, L2 and L5 at S-use.

## 7. Exclusions

- Cells that cannot be built (`unavailable`, e.g. no words because 31b failed) or fail (`time_guard`, server errors) are
  dropped pairwise, as on dev. They are listed under cell health.
- Tasks whose contexts cannot be captured are dropped before any GPU work (`capture_missing`).

## 8. What it can and cannot show

- A single run on N ≈ 24 post-cutoff tasks from 3 repos outside the dev set (sqlglot, tomlkit, networkx expected),
  labelled as such, with the repos named.
- Held-out graphs come from pilot D's re-implementation of the released generator (100% node-id match on 7/7 dev
  graphs), and embeddings from a disclosed substitute model. D1's graph cells read only the graph.

## 9. Cost (L4x4 hours, from C03's and C04's measured rates)

Measured per cell (3 sizes, seconds): depth 1 = 3.66 (31b) + 1.51 (e4b) + 2.05 (12b); depth 2 per sample = 2.29 +
1.39 + 1.65. Server starts 343 + 264 + 197–256 s. Fixed part ≈ 0.44 h (3 starts and stops, install, selection,
records, graphs, capture, words).

| version | per task | N = 24 | range | hard stop |
|---|---|---|---|---|
| main (depth 1 + depth 2) | 0.030 + 0.016 h | **≈ 1.55 h** | 1.3–2.0 | 2.2 h |
| fallback (depth 1 only) | 0.030 h | **≈ 1.15 h** | 1.0–1.5 | 1.6 h |

The upper range allows held-out contexts 25% longer than dev (sqlglot's larger files) and a slower selection step.

## 10. Deviations

None yet.
