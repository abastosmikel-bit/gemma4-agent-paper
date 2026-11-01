# Pilot C — Where does a small agent break? (interim report)

Status: **CPU stage done; notebooks ready and dry-run (§10, §11).** GPU hours used so far: **0**. Notebooks are named by full path (`notebooks/C00_gold_check__CPU.ipynb`, `notebooks/C01_smoke_timing__L4x4.ipynb`, `notebooks/C03_probe__L4x4.ipynb`, `notebooks/C03v_test_verify__CPU.ipynb`); run order and inputs: `notebooks/README.md`.
Branch: `pilot/c-bottleneck` (orphan, as requested; the environment allowed this branch name).

## 1. What I did

Terms used once: an *oracle hint* is ground truth handed to the agent (here: where the bug is,
or which tests check it). An *ablation* turns one hint on at a time and measures the change in
*resolve rate* (share of tasks whose hidden tests pass). *Gold patch* = the reference fix.

1. **Environment.** Python 3.13, no Docker daemon, no `KAGGLE_API_TOKEN`, but the network proxy
   authenticates Kaggle API calls, so the Kaggle CLI works with a dummy key. Disk: 31 GB free.
2. **Read the real harness.** I downloaded the harness wheels (`swegemma 0.2.11`, `adk-eval-core`,
   `adk-submission`, `google-adk`) from the official wheelhouse and read the code paths that
   matter: prompt construction, tool errors, trace format, test selection, verification.
3. **Oracle hints from gold data (CPU, all 129 tasks).** `common/` parses each gold patch, maps
   every changed line to its enclosing `def`/`class` with `ast` on the snapshot file, and takes the
   required test names from `test_patch` with the scorer's own rule (my re-implementation matches
   the scorer's function on 129/129 tasks). Hints contain only paths, symbol names, def line numbers
   and test names, never patch content. Hint conditions: O0 (none), O-file, O-func (file + function,
   so it contains O-file), O-test (test file + test names), O-all (O-func + O-test).
4. **Local runner that reproduces the scorer.** `pilot_c/kaggle_runner.py` copies the official
   starter: the same `Evaluator`, subprocess sandbox, vLLM flags (`max_model_len=32768`, gemma4
   tool/reasoning parsers), the same compaction and cache settings, and the unchanged sample agent.
   It changes only the model alias, the per-task budget, hinted task copies, and concurrency. The
   sample's dummy LoRA adapters are removed for **all** sizes, so every size runs the plain base model.
5. **End-to-end test without a GPU.** I ran the real harness locally against a scripted mock LLM
   server. Confirmed from the actual requests:
   - the hint reaches the prompt only in hinted conditions;
   - tool set = the 9 harness tools + `code_analyzer_agent`;
   - thinking on with a 4,096-token budget, `max_tokens` 16,384, temperature 0.2, top_p 0.95
     (= sample `sampling.yaml`);
   - context length 32,768 is set on the vLLM server exactly as in the starter (verified by code
     reading only: no vLLM run yet).

   Every metric comes out at its expected value: 6 calls, 1 repeat, 1 malformed, 1 failed edit,
   gold file viewed at call 0, gold function edited. All three notebooks pass a local dry run.
6. **Gold-patch check.** I applied each gold patch through the scorer's verification code in a
   local subprocess sandbox to find tasks that no agent can solve here.

Reusable code in `common/` (no pilot logic): `diffs.py` (diff parsing, scorer test-name rule),
`locate.py` (AST scope mapping), `tasks.py` (task loader, snapshot reader, gold locations),
`trace.py` (ATIF/legacy trace parser), `metrics.py` (common metric set, paired McNemar).

## 2. Numbers so far (CPU only, measured)

Gold-location statistics, 129 dev tasks (`results/gold_stats_dev129.json`):

| Property | Count |
|---|---|
| Gold patch touches exactly 1 source file | 91 / 129 |
| Gold patch adds a new source file | 11 |
| Exactly 1 enclosing function/class changed | 68 (0 functions: 7; ≥3: 38) |
| Some change outside any def/class (imports, constants, new top-level defs) | 54 |
| All verification test files are new (agent cannot run them before the fix) | 32 |
| Median gold patch size | 12 changed lines (IQR 4–44.5) |
| Pilot-eligible (1 existing file, 1–2 functions, ≤40 lines, ≥1 test name) | 70 (43 also gold-pass locally) |

Gold-patch check in a **local** sandbox (python 3.13; not yet Kaggle, not the scorer's Docker image;
`results/gold_check_local_summary.json`): the gold patch resolves only **73 / 129** tasks: rich 39/48,
fastapi 31/67, requests 3/13, httpx 0/1. Of the 70 pilot-eligible tasks, 43 pass. Forum runs solved roughly 81 tasks
at least once, so Kaggle's environment is probably more permissive than mine; `notebooks/C00_gold_check__CPU.ipynb` gives the real number.
Causes in the failures I inspected:
- `requests`: the test file needs the `pytest-httpbin` plugin, absent from the wheels and from the
  official Dockerfiles;
- `fastapi_14360`: imports `dirty_equals`, which is not in the wheels;
- `rich_4079`: the expected ANSI output depends on the installed `pygments` version.

## 3. Surprises

- **Many dev tasks look unsolvable even with the gold patch**, for environment reasons. The
  sandbox venv inherits the host's site-packages (`system_site_packages=True`), so solvability
  depends on the host image. Local, the Kaggle notebook, and the real scorer (Docker,
  python:3.13-slim) can each differ. Consequence: every solve-rate number must be read against
  the gold-solvable subset measured **on Kaggle**. `notebooks/C00_gold_check__CPU.ipynb` measures this, using no GPU.
- **O-test is weaker than it sounds.** In 32/129 tasks the required tests live in new files the
  agent can't run, and test names can leak interface information. Forum thread 748482 reports 12
  of 43 failures due to hidden tests needing names absent from the issue. Both effects need
  separating in the analysis: test file exists vs. new.
- **Function-level hints are incomplete for 54 tasks** that also change module-level code. In
  those tasks, the "fix" stage includes adding imports or constants.
- The scorer's task concurrency isn't documented (`inference.py` isn't shipped). The 12 h covers
  all ~120 tasks including setup.

## 4. GPU hours used

None. Estimates for the prepared runs are in §6.

## 5. Closest prior work

Checked on arXiv by the search agent. I personally re-opened the three closest (✓).

| Work | What they did | Gap for this question |
|---|---|---|
| SWE-bench (2310.06770) | "Oracle" retrieval = gold files given to a non-agent model | File level only, no agent, old models |
| Agentless (2407.01489) | Staged file→function→line localization; reports how often gold survives each stage | No gold-fed (oracle) condition |
| SWE-agent (2405.15793) | Interface ablations | No localization or test oracle |
| SWE-Fixer (2501.05040) | Editor with gold files: 20.0% vs 16.3% full pipeline; says editing is the bottleneck | One size, file level only |
| ✓ Loc2Repair (2606.30963, Jun 2026) | Gold modified-file set as a hint, 3 backbones incl. Gemma4-26B-A4B, SWE-bench Verified. Pooled resolve rate: 44.7% → 52.4% with gold files | **Closest.** File level only; no function or test oracle; no size ladder |
| ✓ Beyond Localization (2603.29067) | Oracle localization for 3 RAG repair systems; oracle success < 50% | No test oracle, no sizes |
| ✓ SWE-Ladder (2610.33667, 24 Oct 2026) | Same 3-way split (localization / fail-to-pass tests / patch) used as **training** evidence for Qwen3-4B | Training method, not an inference-time diagnosis; one size. Not yet in novelty-map |
| SWE-smith (2504.21798) | Fail-to-pass test as issue text (training-data ablation); failure analysis names localization | Observational for agents |
| Understanding Code Agent Behaviour (2511.00197) | Trace study: failed runs still find the right files 72–81% | Observational, no intervention |

Competition forum (read via Kaggle's JSON endpoint; single runs, not verified by me):
- [Thread 750974](https://www.kaggle.com/competitions/gemma-4-developer-agent/discussion/750974): same agent on 31 tasks.
  31B 9–11/31, 12B 4/31, **E4B 0/31**; E4B edits the wrong file in 13/31.
- [Thread 749198](https://www.kaggle.com/competitions/gemma-4-developer-agent/discussion/749198) "Found, not fixed": on 31B, the gold
  file was usually found, but the fix failed. The author plans a paper-track writeup, so this is a **direct competitor** for the "it's the
  fix, not localization" story at 31B.
- [Thread 747168](https://www.kaggle.com/competitions/gemma-4-developer-agent/discussion/747168): 15% of tasks flip between two identical 31B runs (noise).
- No public oracle-hint experiment found.

Bottom line: no published stage-wise oracle ablation across sizes of one model family. File-level
oracles are covered (Loc2Repair). Our difference: function- and test-level oracles, four sizes of
one family, and intervention rather than observation.

## 6. Plan, cost, and provisional go/no-go

> Superseded in part by §8.6: run `notebooks/C01_smoke_timing__L4x4.ipynb` with 40 calls; replace the e4b rollout pilot notebook (removed; was `pilot_c_pilot_e4b`) by the D1 probe (`notebooks/C03_probe__L4x4.ipynb`) + a 12b validation slice.

| Step | Accelerator | Estimate (L4x4 h) | Hard stop | Status |
|---|---|---|---|---|
| `notebooks/C00_gold_check__CPU.ipynb`: gold check, all 129 tasks | CPU | 0 | — | ready |
| `notebooks/C01_smoke_timing__L4x4.ipynb`: 3 tasks × 4 sizes at O0, + e4b O-all | L4x4 | ≈1.3 (range 1.0–1.75) | 1.75 | **needs your OK** |
| the e4b rollout pilot notebook (removed; was `pilot_c_pilot_e4b`): e4b × 15 tasks × {O0, O-func, O-all, O0 rerun} | L4x4 | ≈1.2–3 | 3.9 | dropped |

How the 01 estimate is built (estimated, not measured):
- install + checks: ~0.1 h;
- vLLM startups: 3–5 min per small model, 8–10 min for 31B;
- per-task batches at concurrency 3: 8–15 min per size; 31B is likely to hit the 15-min cap.

Full version (provisional; recomputed from 01's measured minutes per task). Cost formula:
L4x4 h = Σ over size, condition and seed of `n_tasks × min_per_task(size) ÷ speedup(concurrency)` + startups.
- **Cheapest design that still answers the question:**
  - 40 gold-solvable tasks, the same for every size;
  - sizes e4b, 12b, 31b with O0×2, O-func, O-test, O-all×2;
  - e2b at O0 and O-all only (if it stays at 0 with all hints, finer conditions add nothing);
  - O-file only where O-func moves a lot.
- With guessed effective minutes per task (e2b/e4b 0.7, 12b 1.2, 31b 2.0), that is
  ≈ 0.8 + 2.8 + 4.8 + 8.0 ≈ **16 L4x4 h**. Over a week of your shared 15 h/week, so 31B would
  likely drop to O0 + O-all (≈5.3 h, total ≈ 11 h).
- Calendar: pipeline is built; runs ≈ 3–4 days of quota, analysis 1–2 days. This fits before the
  9 Nov internal target only if 02 runs by ~2 Nov.

Provisional go/no-go (fixed before seeing data):
- **GO** if e4b O-all beats O0 by ≥3 of 15 tasks and the O0 rerun flips ≤2 tasks: the hints move
  small models, and the stage split is measurable.
- **NO-GO for this as a paper core** if O-all ≈ O0 ≈ 0: that alone says "small models can't write
  the fix even when told where", and the forum already suggests it.

Caveat, from your CLAUDE.md: an oracle ablation is a measurement study, which the ambition rule
rejects as the core contribution. Its best use is as the diagnosis that motivates and targets a
new mechanism (e.g. a localization method if O-func dominates, or an edit or verification method
if only O-all helps).

## 7. Files

`common/` shared code · `pilot_c/` hints, selection, Kaggle runner, CPU information checks ·
`notebooks/` generated notebooks + how to run · `tests/` unit tests, mock-LLM end-to-end and
notebook dry runs · `results/` aggregate JSONs only.

## 8. Rethink (no GPU used)

### 8.1 The question one level up

Problems with "which stage binds at each size", including your framing:
- **It assumes a serial pipeline with one bottleneck.** Agents don't work like that. A test name
  also localizes, a location hint changes what gets read, and a hint given at step 0 changes the
  whole trajectory. So O-x measures the effect of a piece of information on the whole run, not "a stage".
- **"Binding" is relative to the budget and the scaffold.** With 50 calls, running out of calls can
  be the binding stage. The sample agent (10 tools, a sub-agent, thinking 4,096) is tuned for 31B,
  so a small model may break on the scaffold, not on any stage.
- **Both ends are nearly known.** For 31B the forum says "found, not fixed". For e4b, 0/31 means
  everything fails. Resolve rate on 15 tasks moves in steps of 7 points: too coarse to rank stages.
- **"Size" is not one clean variable.** E2B/E4B are "effective-parameter" models and 12B needs an
  architecture override, but within one family it is as clean as it gets.

The higher-level question:
> **For a model of size S, how much of its failure comes from missing information (which a tool
> or harness could supply), and how much from being unable to use information it already has?
> And which of the missing information can be found in the repository at all?**

Put operationally: per task and size, what is the cheapest piece of information that turns a
failure into a success (its *information threshold*)? How does that threshold move with size?

Why this is useful outside the competition:
- **Headroom.** The gap between oracle and no-hint is the most any retrieval or localization tool
  can buy at size S. That tells tool builders where to invest for small models.
- **Training.** The gap between "information supplied" and "information used" tells trainers which
  privileged evidence is worth distilling at which size. SWE-Ladder makes exactly this choice by hand.
- **Benchmarks.** Separating unfindable information (only in the hidden test) from agent failure
  matters to anyone building SWE-style benchmarks.

### 8.2 What the CPU data checks already say (measured; heuristics marked)

| Check | Result | What it means for the question |
|---|---|---|
| Gold-patch ceiling (local sandbox) | 73/129 tasks solvable | Failures fall into three buckets, not two: missing information, can't use it, and environment. Headroom must be measured against the gold ceiling, not 100%. |
| Unfindable requirement (heuristic; `results/info_spec_dev129.json`) | 21/129 tasks (16%): hidden test needs a new name (12) or exact message (16) the issue never states. 3/70 among pilot-eligible tasks | Part of any O-test gain is specification leak, not "reproduction". No search can close that gap. |
| Location information (`results/info_location_bits_dev129.json`, 82 single-file tasks) | File hint ≈ **5.3 bits**, function hint ≈ **4.5 more bits** (medians); ≈10 bits total, about 1 definition in 1,000 | The two hints carry similar amounts of information. The forum says 31B opens the gold file by call 2–3 in ~84% of runs, so the first ~5 bits are cheap for 31B. Open: do small models find the other ~4.5, and can they use them? |
| Tests that exist before the fix | 97/129; in 32 the test files are all new | "Reproduction" is undefined for a quarter of the tasks. Better axes: **WHERE** (location), **WHAT** (expected behaviour, required names and messages), **HOW** (the change). |
| Sub-agent visibility (ADK source, confirming pilot A) | `code_analyzer_agent` calls are invisible in the root trace | Process metrics such as "viewed gold file" are lower bounds. A replay instrument must treat the sub-agent's answer as a fixed observation. |

### 8.3 One instrument instead of three studies

All three pilots hold content fixed and vary one thing. They can be written as one intervention
`(state, information, channel)` with an outcome measured at some `depth`:

| Axis | Values |
|---|---|
| state *s* | step 0 (issue only), or a replayed prefix of the model's own trajectory (after reading the gold function, just before the first edit, …) |
| information *x* (a ladder) | none → WHERE-file → WHERE-function → WHAT (test names, required names and messages) → HOW in words → HOW exact (the diff) |
| channel *c* | issue text · skill text (the only one also legal in a real submission) · tool output or user turn at step *t* |
| depth *d* | 1: teacher-forced log-likelihood of the reference action. Prefill only, continuous, cannot floor. 2: one sampled next action, checked (right file? edit applies? tests pass?). 3: full rollout (resolved) |

- Pilot C = (step 0, WHERE/WHAT, issue text, depth 3).
- Pilot A = (replayed step *k*, skill, skill channel, depth 3).
- Pilot B = (state at the edit, HOW exact, prompt, depth 2).

One harness, one task set, one budget. The O0 runs then become shared baselines and pool across
pilots for the noise estimate. Per (task, size), the instrument yields an information threshold:
the lowest rung that works. It is ordinal, so it can be analysed like item difficulty. The
continuous version, likelihood gain per rung, is close to "usable information" (V-information:
Xu et al. 2020; Ethayarajh et al. 2022). That is to be cited; not re-verified this session.

### 8.4 If e4b solves nothing without hints

- **Where the ladder switches on.** If e4b only succeeds at HOW-exact, the failure is expression
  (Pilot B's question). If it fails even there, the failure is agent mechanics: look at malformed
  calls, failed edits, budget exhaustion.
- **Depth 1 never floors.** The log-likelihood gain of the gold action per rung is measurable even
  at 0% resolved.
- **Process metrics.** Viewed gold file, edited gold file or function, first gold-view call,
  repeat share. The forum says e4b edits the wrong file in 13/31, so it often edits something.
- **A clean "can't use even the exact change" is itself a result**, and actionable for the
  small-footprint bonus.

### 8.5 Directions

| | D1 Information-ladder probe | D2 Findable vs unfindable, and hint trust | D3 Counterfactual replay for failure attribution |
|---|---|---|---|
| Claim | Per size: how much each rung raises the chance of the correct action (find vs use), and the per-task threshold | Oracle gains split into findable vs unfindable parts. Smaller models are hurt more by a wrong hint, so retrieval for small models must favour precision (a gating rule) | Injecting the missing fact at step *k* of a failed run and continuing finds the earliest step that flips the outcome: interventional failure attribution with no LLM judge |
| Design | 40 gold-solvable tasks × ~7 rungs × 2 states × 4 sizes, depths 1–2. Depth-2 edits are verified in a free CPU notebook | Rollouts. 12b: O0, WHERE-func, WHAT-unfindable-only, WRONG-WHERE (a plausible wrong function in the same file). 31b: O0 and WRONG-WHERE | Failed O0 runs of e4b/12b, injection at {0, first read, first edit, before submit}, continuation rollouts; reuse pilot A's replayer |
| New vs Loc2Repair | Full ladder up to the exact diff (Loc2Repair: correct file set only), one family, four sizes, floor-free measure | Wrong hints and the findable/unfindable split (Loc2Repair has neither) | Injection mid-trajectory (Loc2Repair injects at step 0 only) |
| New vs SWE-Ladder | Measures at inference which evidence each size can use: the choice SWE-Ladder hard-codes for one 4B model | Inference-time; SWE-Ladder only trains on correct evidence | SWE-Ladder never replays |
| L4x4 cost (estimated) | **≈2 h** (range 1.5–3; D1-lite: 20 tasks, depth 1, three sizes ≈0.8 h) | ≈5 h | 10-task demo ≈3–4 h; full ≈8–10 h |
| Engineering | ~1.5 days: rebuild the agent's exact chat context (tool schema, chat template) from real traces; vLLM `prompt_logprobs` | ~0.5 day: two new hint renderers; runner reused | 2–3 days; depends on pilot A's replayer |
| Main risk | Depth 1–2 may not predict rollouts (hence validation) | 12b may also sit near the floor | Cost; sandbox replay fidelity |

How the D1 cost is built:
- ~280 contexts per size of ~10k tokens (prefill), plus one short generation each;
- 4 server start-ups ≈ 25 min;
- 31B ≈ 1 h; 12b ≈ 0.5 h; e2b/e4b ≈ 10–15 min each.

These are guesses until `notebooks/C01_smoke_timing__L4x4.ipynb` has measured real throughput.

### 8.6 Recommendation

1. **Make D1 the core**, with one D2 slice as validation:
   - 12b at O0 vs O-all on the same 35–40 tasks (≈1.5 h). This reuses the built pilot notebook
     with a different PLAN.
   - It tests whether depth-1/2 probe gains predict rollout gains. If they do, future studies can
     use probes at a fraction of the cost. That is the general, reusable part, and a
     Best-New-Resource candidate: scripts that rebuild the ladder for any SWE-style dataset with
     gold patches.
   - Total ≈ 3.5–4 h with 01, against ≈11–16 h for the original grid.
2. **Bridge to a method (hypothesised).**
   - If small models can use WHERE but don't find it: build a localization skill or sub-agent.
     That is a legal channel, and pilot A's.
   - If they can't use even HOW-exact: fix edit expression (pilot B).
3. **`notebooks/C01_smoke_timing__L4x4.ipynb`: run it, but with the budget changed to 40 calls / 15 min (§8.7). Otherwise as
   built.** It still earns its ≈1.3 h because every direction needs:
   - all four servers proven on Kaggle, including 12B's override;
   - real per-size traces to rebuild the probe contexts exactly;
   - per-size minutes per task to price the validation rollouts.

   The e4b O-all arm is a cheap first look at whether hints change behaviour.
4. **Do not run the e4b rollout pilot notebook (removed; was `pilot_c_pilot_e4b`).** 15-task e4b rollouts are the design most likely to floor.
5. **Run `notebooks/C00_gold_check__CPU.ipynb` regardless.** The gold ceiling matters for every direction.

### 8.7 Budget: switch from 50 to 40 calls?

**Yes, switch to 40 calls / 15 min, matching pilot A.**
- Identical O0 settings make the pilots' no-hint runs replicates, which gives a better noise
  estimate for free.
- The process metrics become directly comparable.
- Cost: 40 binds more often for small models that loop. Log the share of runs that exhaust the
  budget (`budget_tool_calls == 40`) so that binding is visible rather than hidden.

I have **not** edited the built notebooks. It is one line (`BUDGET = dict(timeout_seconds=120,
max_tool_calls=40, max_time_minutes=15)`) in the config cell of 01/02. Edit it in the Kaggle UI or
tell me to regenerate. Also worth aligning: use pilot A's shared split (`sample_ids`) intersected
with the gold-solvable tasks, so the baselines cover the same tasks.

## 9. `common/` here vs `pilot/a-skills` (read-only comparison; nothing changed there)

| Topic | pilot A `common/` | pilot C `common/` | Merge suggestion |
|---|---|---|---|
| Files | `tasks.py`, `trace_parser.py`, `metrics.py`, README | `tasks.py`, `trace.py`, `metrics.py`, `diffs.py`, `locate.py` | Keep A's names; add C's `diffs.py` and `locate.py` |
| Task code | Loader + deterministic per-repo split `sample_ids(repo, n, seed)` | Loader + snapshot reader + gold locations (files, AST functions, scorer test names) | Union; use A's split as the shared one |
| Trace parsing | Pairs k-th call with k-th response per tool; also reads tokens, thinking and compaction counts, and agent texts | Same pairing; also reads harness `continuation_nudge` events; no token counts | Use A's parser; add C's nudge events |
| Sub-agent calls | Documented as invisible in the root trace | My docstring claimed they were included. **Wrong**, now corrected | Adopt A's statement |
| `tool_calls` / harness count | `tool_calls`, `harness_tool_calls` | `tool_calls`, `budget_tool_calls` | Rename C to `harness_tool_calls` |
| Error detection | `status=="error"`, or `error_code`/`error` without status (skill tools) | `status=="error"` only, so it misses skill-tool errors | Take A's rule |
| Malformed calls | Unknown tool via the declared tool list; error types incl. skill codes (`INVALID_ARGUMENTS`, `SKILL_NOT_FOUND`, …); `ValueError` containing "not found"/"argument"; raw `<\|tool_call>` text | Fixed error types + message patterns (unknown tool, missing or unexpected arguments, `start_line > end_line`); "unparsed" = the harness's truncated-tool-call nudge | Union of rules. Report raw-marker texts and truncation nudges as separate counts |
| Skill tools | 4 (no `search_skills`), plus load breakdown and `skill_load_rate` | 5 (incl. `search_skills`), count only | A's breakdown, plus `search_skills` |
| Tokens | From trace step metrics | From `TaskResult.total_tokens` (was 0 in my mock run) | A's |
| Aggregates | Pooled shares, `failed_edit_share`, `submit_rate` | Pooled and per-task-mean shares, totals, `submitted_share` | Pooled as primary; agree on names |
| Statistics | `mcnemar_exact`, `paired_bootstrap`, `seed_noise` | `paired_flips` (McNemar keyed by task id) | A's set + keying by task id |
| Localization metrics | — | viewed, edited and first-view of gold file/function (needs gold) | Keep as an optional C module |
| Tests | Builds a trace with swegemma's own `SessionTrace` writer | Synthetic AST tests + full harness run against a mock LLM | Keep both |

Repeat-call and failed-edit definitions are identical. Malformed-call definitions differ (above),
so the pilots' `malformed_share` numbers are **not comparable** until merged.

## 10. Phase 3 status (2026-10-31; no GPU used)

- **Notebooks fixed and dry-run with papermill** (`tests/papermill_dryrun.sh`), in their real dependency order:
  `notebooks/C00_gold_check__CPU.ipynb` → `notebooks/C01_smoke_timing__L4x4.ipynb`, and `notebooks/C00_gold_check__CPU.ipynb` → `notebooks/C03_probe__L4x4.ipynb` → `notebooks/C03v_test_verify__CPU.ipynb`. The cause of the Kaggle failure was empty `%%writefile` cells; the builder now asserts
  that no cell is empty.
- `notebooks/C00_gold_check__CPU.ipynb` also runs the no-patch baseline: valid = gold passes AND no-patch fails. It classifies failures (missing module /
  fixture / test failure / …), counts fastapi tasks failing on `inline_snapshot` / `dirty_equals` (the forum claim), and
  writes the pre-registered task order. `notebooks/C01_smoke_timing__L4x4.ipynb` reads its 3 tasks from `notebooks/C00_gold_check__CPU.ipynb`'s output, uses 40 calls / 15 min, and logs
  compaction through runtime probes.
- **Findings from the checks** (details and sources in `LEARNINGS.md` on `paper/main`):
  - The local Evaluator counts empty patches; the scorer does not. `resolved` now requires a non-empty patch.
  - 5/72 gold-passing tasks pass with no patch (local).
  - Token-threshold compaction is invisible in harness traces (mock run: 0 in trace vs 15 seen by the probe).
  - Compaction also summarizes away the task prompt and hints.
- **Probe:**
  - Plan frozen at `168d115` (`docs/PLAN.md`); deviations found before any GPU run are in its §11.
  - Contexts are captured through the real agent loop. On 4/4 dry-run tasks the captured read output equals the
    harness format.
  - The canonical edit equals the gold patch on 9/10 local tasks; the 10th differs only by out-of-function changes,
    by design.
  - The vLLM 0.19.1 API fields the probe uses were checked in its source.
- **Shared branch `paper/main`:** `LEARNINGS.md`, `DECISIONS.md` (plan hash recorded), `RESULTS.md`,
  `docs/PROBE_INPUT.md` (v2).

## 11. Notebook names (2026-10-31)

Every notebook is named by the rule `<pilot letter><number>_<what>__<accelerator>.ipynb`, flat in `notebooks/`. The
first cell of each says what to attach and what to bring back; `notebooks/README.md` lists them in run order.

| Full path | Was | Output to commit |
|---|---|---|
| `notebooks/C00_gold_check__CPU.ipynb` | `notebooks/pilot_c_gold_check_cpu/gold_check_cpu.ipynb` | `results/C00_gold_check.json` (was `pilot_c_gold_check_kaggle.json`) |
| `notebooks/C01_smoke_timing__L4x4.ipynb` | `notebooks/pilot_c_smoke_timing/smoke_timing.ipynb` | `results/C01_smoke_timing.json` (was `pilot_c_smoke_timing.json`) |
| `notebooks/C03_probe__L4x4.ipynb` | `notebooks/pilot_c_probe/probe.ipynb` | `results/C03_probe.json` (was `pilot_c_probe.json`) |
| `notebooks/C03v_test_verify__CPU.ipynb` | `notebooks/pilot_c_probe_verify_cpu/probe_verify_cpu.ipynb` | `results/C03v_test_verify.json` (was `pilot_c_probe_verify.json`) |
| (removed) | `notebooks/pilot_c_pilot_e4b/pilot_e4b.ipynb` | superseded by `notebooks/C03_probe__L4x4.ipynb`; the 12b validation will get its own C-number |

The per-notebook `kernel-metadata.json` files were dropped with the subfolders, so the notebooks are run through the
Kaggle UI. All four pass a papermill dry run under the new names (`tests/papermill_dryrun.sh … C00 C01 C03 C03v`).

## 12. Kaggle environment fix (2026-10-31)

- **Cause of the failure of `notebooks/C00_gold_check__CPU.ipynb` after 11 s:** a new Kaggle notebook runs Python 3.13,
  and pip rejects the wheelhouse's cp312 wheels (`cbor2-6.1.4-cp312-…`). The official starter runs on a pinned image
  (`gcr.io/kaggle-private-byod/python@sha256:37c64f7d…`, from its kernel metadata) with Python 3.12, per its run log
  (`/usr/local/lib/python3.12/dist-packages`, read through the Kaggle output API). Reproduced locally: 3.13 rejects
  `cbor2` with the same message; 3.12 accepts all wheels.
- **Fix:**
  - Every notebook's first markdown cell and `notebooks/README.md` give the UI steps: Copy & Edit the starter, then
    File → Import Notebook, keep Environment = "Pin to original environment".
  - Every notebook's first code cell prints the Python version and raises at once unless it is 3.12.
  - `install_wheelhouse` refuses, before calling pip, any wheel whose Python tag doesn't fit.
- **CPU notebooks install 5 wheels.** `notebooks/C00_gold_check__CPU.ipynb` and
  `notebooks/C03v_test_verify__CPU.ipynb` install only `swegemma`, `adk_eval_core`, `adk_submission`, `google_adk`
  and `google_genai`. These are the only wheelhouse distributions among the 90 that the gold-check path imports
  (measured under Python 3.12).
- **Dry runs now match Kaggle.** They run under Python 3.12 with the real wheel install from the full 41-wheel
  wheelhouse. A negative test runs C00 under 3.13 and expects the environment check to stop it after one cell.
- **Dry-run results (2026-10-31):**
  - NEG313: stopped by the environment check after 1 cell.
  - C00 and C03v: Python 3.12.3, real install of 5 wheels.
  - C01 and C03: Python 3.12.3, real install of all 41 wheels.
  - All passed under papermill.
  - **Correction (later the same day):** that C01/C03 pass was vacuous. In the 3.12 venv every LLM call failed on a
    local `mcp`/`litellm` mismatch, so C01 made 0 tool calls and C03 captured 0 contexts, and the notebooks still
    finished. The venv is fixed, and the dry run now asserts content: tool calls > 0 and no errored tasks for C01;
    captures, scored cells and samples for C03; verified rows for C03v.
- **Limit of the dry run:** the packages that the Kaggle image itself provides (litellm, pydantic, torch, …) come from
  PyPI in the local venv, not from the image, so library-version differences inside the image are still not covered.
- **Not verified:** that Kaggle's Copy & Edit + Import Notebook keeps the pin, and the menu labels. These come from
  how Kaggle documents and shows these settings; I can't open the UI from here. The first code cell catches any
  mistake within seconds.

## 13. Freeze protection for GPU notebooks (2026-10-31)

- **Before this change:**
  - `notebooks/C01_smoke_timing__L4x4.ipynb` had no request timeout of its own. LiteLLM's default is 6,000 s, and the
    harness retries timeouts up to 5 times.
  - `notebooks/C03_probe__L4x4.ipynb` had only long timeouts (600–1,800 s).
  - Neither had a watchdog, and their time guards ran only between runs.
  - A frozen server would have burned L4x4 time until Kaggle's session limit.
- **The bug is real in vLLM 0.19.1** (reproduced offline). The gemma4 tool parser loops forever on an array nested
  in an array whose string contains `[` or `]`. Flat lists, which is what our only array tool `get_code_subgraph`
  takes, are fine. Details are in `LEARNINGS.md` on `paper/main`.
- **Now** (`common/server_watchdog.py`):
  - **Per-request timeouts:** 900 s for agent requests (= per-task budget); probe: 60 s tokenize, 180 s scoring,
    300 s words, 900 s sampling.
  - **Watchdog:** a thread polls `/health` every 30 s. After 3 failures (~90 s), or when requests are in flight but
    none finished for 20 min, it kills the server. Pending and new requests then fail at once with a non-retryable
    error, and tasks not yet started are skipped.
  - **Restart, then stop:** the next condition (C01) or size (C03) gets a restarted server, and the session stops
    after the second freeze. C01 also stops if every task of a run fails without a tool call.
  - The builder refuses to emit any GPU notebook without the watchdog, so the future 12b validation gets it too.
- **Verified** (papermill under Python 3.12, real 41-wheel install, mock server that hangs on every request including
  `/health`):
  - Standalone: an in-flight request ends ~4 s after the freeze (dry-run settings) and the next one fails in 0.000 s
    with `ServerFrozen`.
  - `notebooks/C01_smoke_timing__L4x4.ipynb` freeze test: 2 freezes, 1 restart, then stop; 3 models skipped;
    107 s in total.
  - `notebooks/C03_probe__L4x4.ipynb` freeze test: 2 freezes, then stop; 12b and e2b skipped, nothing scored for
    them; 103 s.
  - Normal runs with content checks: C01 has 9 tool calls per task and 0 errors in all 5 runs; C03 captured 4/4
    tasks, 456 depth-1 and 404 depth-2 cells; C03v has 308 verified samples.
  - With the production settings (30 s × 3 health checks), detection takes about 90 s.

## 14. Failed Kaggle run of `notebooks/C03_probe__L4x4.ipynb` (2026-10-31) and fixes

**GPU used by the failed run: ≈0.29 L4x4 h** (1,053 s, from the log). GPU hours used in total so far: **≈0.29**.

**What happened (from the log and the partial `C03_probe.json`):**
- Install 58 s; task records + graphs 191 s; capture of the 30 tasks' contexts through the real agent loop 308 s
  (5.1 min, no inference server). All 30 context checks passed; 3 candidates were excluded (change outside the read
  span).
- 31b server up after 366 s. **The 31b step then took 14 s and produced nothing.** The first request of its
  self-check got **HTTP 500**, so 0 cells were scored, 0 samples drawn, and the words rung was never written. About
  10 s of the 14 were `stop()` waiting before it killed the server.
  - The error was raised as a plain `HTTPError`, not as a self-check failure, so the stop rule didn't fire and the
    loop went on.
  - The cause of the 500 was lost: my client dropped the response body, and `VllmServer.stop()` deletes the server
    log. Leading hypothesis, unverified: out of memory in `prompt_logprobs` (PLAN §11, deviation 7).
- `VllmServer.stop()` killed only the API-server process. The EngineCore and the 4 tensor-parallel workers survived
  with ~20 GiB per GPU, so the e4b server found 1.53 GiB free and the notebook crashed on an uncaught startup error.
- **A second bug, found offline afterwards:** with the 31b and 12b templates every S-find cell would have failed the
  token-prefix check (empty thought block in the generation prompt; deviation 8).

**Fixes:**
- **Process groups:** each server starts in its own process group. Stopping saves the log, then sends SIGTERM and
  SIGKILL to the whole group plus the recorded descendants. Before every start, the notebook waits until
  `nvidia-smi` shows enough free memory on all 4 GPUs. If it isn't back within 300 s, the session stops with a clear
  message instead of crashing.
- **Sizes isolated:** each size runs isolated and writes `C03_probe_<size>.json`. A failed start or run is recorded
  and the next size runs. The session stops after two consecutive self-check failures, a second freeze, or memory
  not released.
- **Order stays 31b → e4b → 12b → e2b:** one server start per size is the minimum (the capture step uses no
  server), and 31b must go first because it writes the words rung the other sizes use.
- **Self-check:** it now covers an S-use and an S-find score plus a short 2-sample generation, and any exception in
  it counts as a self-check failure.
- **Diagnostics kept:** HTTP error bodies are recorded, and server logs are saved under `private/server_logs/`
  (error lines printed).
- **Probe server headroom:** `gpu_memory_utilization=0.75`, `--max-num-batched-tokens 1024`.
- **Builder guard:** the builder now compiles every generated code cell before writing the notebook.

**Verified without GPU:**
- `tests/test_server_shutdown.py` uses the real `VllmServer` with a fake vLLM process tree that ignores SIGTERM. The
  library's own `stop()` leaves 5 of 6 processes alive; the new group stop leaves 0. The GPU-memory wait returns,
  times out with the clear error, and is a no-op without a GPU.
- `tests/test_template_scoring.py` uses the real 31b/12b/e4b templates. Every tested cell scores, and the target
  decodes to exactly the intended `read_file` or `edit_file` call.
- **Papermill suite** (Python 3.12, real 41-wheel install):
  - C03: 4/4 captured, 456 depth-1 and 408 depth-2 cells, all four per-size files.
  - C03 with 12b's server failing to start: 31b, e4b and e2b complete with their own files; 12b recorded as failed.
  - C03v: 312 verified samples.
  - Freeze tests: C01 and C03 each stop after 2 freezes, in 100 s and 94 s.
  - C00 and C01 passed with the same code earlier in the day.
- **Not verified:** that the HTTP 500 was an out-of-memory error, and real GPU-memory release timing. Both can only
  show on Kaggle; the next run records them.

**Updated L4x4 estimate for `notebooks/C03_probe__L4x4.ipynb`: ≈2.2 h (range 1.6–3.0), hard stop 2.9 h.**

| Part | Time | Status |
|---|---|---|
| install + records + capture | 0.16 h | measured |
| 31b start | 0.10 h | measured |
| other three starts | ~0.17 h | estimated |
| GPU-memory waits | ≤ 0.07 h | estimated |
| words | 0.05 h | estimated |
| depth 1 | ~0.75 h | estimated; contexts are ~4–4.5k tokens per the real templates, smaller than the 7k assumed, which offsets the smaller prefill chunks |
| depth 2 | ~0.85 h | estimated |
