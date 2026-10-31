# Pilot C — Where does a small agent break? (interim report)

Status: **CPU stage done. You approved notebook 01 (smoke + timing, hard stop 1.75 L4x4 h), a 50-call / 15-min budget, and small single-file tasks.** GPU hours used so far: **0**.
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
at least once, so Kaggle's environment is probably more permissive than mine; notebook 00 gives the real number.
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
  the gold-solvable subset measured **on Kaggle**. Notebook 00 measures this, using no GPU.
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

| Step | Accelerator | Estimate (L4x4 h) | Hard stop | Status |
|---|---|---|---|---|
| 00 gold check, all 129 tasks | CPU | 0 | — | ready |
| 01 smoke + timing: 3 tasks × 4 sizes at O0, + e4b O-all | L4x4 | ≈1.3 (range 1.0–1.75) | 1.75 | **needs your OK** |
| 02 pilot: e4b × 15 tasks × {O0, O-func, O-all, O0 rerun} | L4x4 | ≈1.2–3 (re-estimated after 01) | 3.9 | after 01 |

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

`common/` shared code · `pilot_c/` hints, selection, Kaggle runner · `notebooks/` generated
notebooks + how to run · `tests/` unit tests, mock-LLM end-to-end and notebook dry runs ·
`results/` aggregate JSONs only.
