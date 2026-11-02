# Pilot D: held-out tasks in the competition's format (REPORT)

Branch `pilot/d-heldout` (orphan). The session was assigned `claude/cool-archimedes-nbw020`; per your instruction the orphan
history was pushed to `pilot/d-heldout` with a plain push, and nothing else was touched. **GPU hours used: 0.**
The improved prompt I worked from is `docs/PROMPT.md`.

## 0. Round 2 (2026-11-02): D1/D2 specs, the embeddings confound, the Level A export

**Asked:**
1. D1/D2 specs on `paper/main` (`docs/D_SPECS.md`) so pilot C can price them: a version that fits ≈ 3 L4x4 h and a
   cheaper fallback.
2. Fix the missing-embeddings confound.
3. The held-out export in `docs/PROBE_INPUT.md` format.

**GPU used: 0.**

**Delivered:**
- **`docs/D_SPECS.md` on `paper/main`:** D0 (CPU export, claim 5), D1 (probe, claims 1 and 3), D2 (12b rollouts, C06
  configuration, claims 2 and 4).
  - Main version ≈ 2.8 L4x4 h at N = 24 (≈ 0.42 + 0.098 N h).
  - Fallback ≈ 1.2 h (D1 depth 1 only); floor ≈ 0.9 h.
  - Pricing units and replication criteria are included.
- **Embeddings confound fixed.** The export ships disclosed substitute embeddings (bge-small, chosen by measured
  neighbour agreement and speed). The harness's own prompt builder shows "Code Intelligence Tools" for 101/101 tasks (0/101 without the file); the graph tools answer on 8/8 sampled tasks.
- **Level A export (local, outside git):** 101 valid held-out tasks from 5 repos, with graphs, embeddings, test-only
  wheels, `heldout_meta.jsonl` and `EXPORT.json`. Pilot C's own probe code runs on it unmodified: eligibility 61/101
  (my mirror agrees 101/101), 51 probe records build ok, 10 fail C's read-window rule.
  - The copy for C is produced on Kaggle by `notebooks/D0_heldout_export__CPU.ipynb`, which also fetches the issue text
    this session cannot reach.
  - Its papermill dry run (2 repos, fake `/kaggle`) passes all 8 content checks.

**Decisions I took, with reasons:**
- **D2 is O0 only.** C06 left the dev hint effect at +4 net (p = 0.29), so a held-out O0-vs-O-all test at N ≈ 24 is
  uninformative. Claims 2 and 4 are measured in every run. O-all is an add-on (+1.1 h).
- **D1 includes depth 2.** Claims 1 and 3 quote depth-2 behaviour ("reads the gold function 13% → 97%"), and those
  effects are large enough for N ≈ 24. Cost +0.4 h.
- **Task set:** probe-ready, issue-linked (no fix hints), no hang bug, ≥ 2 tasks per repo, graph ≤ 20k nodes; N = 24,
  at most 12 per repo. Today's pool gives 22 (sqlglot 12, networkx 5, tomlkit 5); D0's API linking can raise it to 32.
- **Added tomlkit** (MIT, flat, pytest only; 20/20 valid) as a third repo. The graph-size rule removed sympy from
  D1/D2.
- **Embeddings:**
  - bge-small-en-v1.5, raw, no map. Open models agree on 17–18% of released top-10 neighbours (random 0.9%).
  - A cross-validated linear map lowered agreement, so none is used.
  - bge is 4× faster than gte on CPU (measured), at equal agreement.
- **F2P/P2P stay out of `tasks.jsonl`.** With them, the scorer would use them as the required tests instead of the
  test-patch rule dev tasks use. They are in `heldout_meta.jsonl`.
- **Dropped xarray** (1/12 valid; optional backends) and **Python-Markdown** (2/9; entry points need an installed copy).
- **Declined:**
  - running code from Hugging Face model repos (`trust_remote_code`): the safety check refused it, and I switched to
    models that need none;
  - accepting the EmbeddingGemma licence on your Kaggle account: your decision.

**Numbers** (local, single run; `results/heldout_pool_local.json`, `results/embedding_parity.json`):

| repo | valid / built | probe-ready (C's code) |
|---|---|---|
| sqlglot | 46/50 | 21 |
| networkx | 16/21 | 8 |
| sympy | 11/14 (0/14 before declaring `hypothesis`) | 7 |
| pyparsing | 8/9 | 0 |
| tomlkit | 20/20 | 15 |
| xarray (dropped) | 1/12 | |
| Python-Markdown (dropped) | 2/9 | |

**Surprises:**
1. **My first export did not match the dev hunk-header convention.**
   - Dev patches use git's Python diff driver (hunk headers `def …`). Mine used the default driver (`class …`).
   - The scorer takes required tests from those headers when a test patch adds no new test function. So my first tasks
     had weaker verification, and 29 of 48 probe-ineligible tasks failed only on "no required test name".
   - Fixed. Re-mined patches are identical apart from the headers, and all 81 tasks stay valid under the stricter
     required tests.
2. **The released embeddings have one near-constant dimension** (≈ 3.37 in dimension 199), so `search_similar_code`
   scores ≈ 0.999 for all top hits. A linear map into that space lowers neighbour agreement.
3. **The harness's graph tools stall on large graphs.**
   - swegemma's embedding cache is an LRU of 50,000 entries, filled with node ids and texts. Above ~25k nodes the ids
     are evicted, and `get_graph` degrades to an O(N²) lookup.
   - Measured: 1.2 s for 8.1k nodes vs > 5 min, unfinished, for sympy's 39.5k. Dev graphs (≤ 4.3k) are unaffected.
   - sympy's AST also hit Python's recursion limit in codegraph-loc; the limit is raised in `graph_build`.
4. **Two dry-run failures were environment problems,** not notebook bugs:
   - missing `google.cloud` in my local venv (the Kaggle image has it);
   - missing `pytest`.

   D0 now installs pytest and pytest-timeout if missing.

**Open tasks (round 2)** — [you] = your decision or action, [C] = pilot C, [D] = pilot D:
- [x] [D] Split D0, which Kaggle refused because Internet is not allowed with the competition attached:
  - `notebooks/D0a_heldout_fetch__CPU.ipynb`: Internet ON, nothing attached.
  - `notebooks/D0b_heldout_export__CPU.ipynb`: Internet OFF; competition, wheelhouse and D0a's output attached.
  - Local dry runs pass 10/10 each. D0b's ran in a network namespace with 0 network attempts.
  - D0b's output layout is unchanged for D1/D2.
- [ ] [you] Run D0a on Kaggle (≈ 1–3.5 h; a `GITHUB_TOKEN` secret makes the issue-text step take minutes, not hours).
  Then run D0b with D0a's output attached (≈ 2–3 h). Bring back `D0a_summary.json` and `D0_summary.json`.
- [ ] [C] Price D1/D2 from `docs/D_SPECS.md` (`paper/main`, bd2ead0). Main ≈ 2.8 L4x4 h at N = 24 (≈ 0.42 + 0.098 N),
  fallback ≈ 1.2 h.
- [ ] [you] GPU OK for D1/D2: main or fallback, after C's price. No GPU used so far.
- [ ] [C] Build `D1_heldout_probe__L4x4.ipynb` (C03/C04 variant) and `D2_heldout_rollouts_12b__L4x4.ipynb` (C06
  variant) on D0's output.
  - Select the tasks with `pilot_d/select_d_tasks.py`. Local dry run: 22 tasks, 3 repos; D0's issue text should
    raise it to 24.
  - Freeze criteria R1–R7 in C's plan before the run.
- [ ] [D] After D0: compare Kaggle validity with local (101 valid); register the Kaggle numbers in `RESULTS.md`; update
  `docs/D_SPECS.md` if N changes.
- [ ] [D] D2 caveat to carry into the analysis: `search_similar_code` runs on substitute embeddings (17% neighbour
  agreement with the released ones). Report its call share.
- [ ] [you, from round 1] Ask the host whether graphs regenerated from public upstream repos are fine with a citation and a
  link to the Kaggle dataset.
- [ ] [you, optional] EmbeddingGemma needs a licence click on your Kaggle account. Not needed now (bge-small is in use).
- Not done, on purpose: no GPU; no tokens added; competition data stays out of git (leak scan: 0 dev ids, commits or
  statements in tracked files); sympy stays in the export but out of D1/D2 (graph size).

*Round 1 (2026-10-31) follows unchanged.*

## 1. Bottom line
- **It works and it is cheap.** From two new repos, **22 of 26 built tasks are valid**. Valid means the competition harness's
  own verification code fails them without a fix and passes them with the gold fix. Docker and the Kaggle-style subprocess
  sandbox agree on **26/26** verdicts. Building and validating takes **~3–4 CPU-minutes per task** and no GPU.
- **Not novel on its own.** Extra tasks in competition format already exist (OOD-45, a public 216-task set), oracle
  "injection" exists (ORACLE-SWE), and a graph generator exists (codegraph-loc). What is new is the *fidelity*:
  - validation by the harness's own code in the scorer's backend;
  - graphs that reproduce the released generator exactly, bugs included;
  - verified injection payloads.
- **Recommendation: GO, as the evaluation substrate of the main paper, not as its headline.** It gives the other pilots'
  replay-inject experiment an out-of-distribution test (the *generality* criterion) and ready-made, verified payloads. Keep a
  standalone "Best New Resource" entry as the fallback if the main method fails (§7).
- **Surprise worth your attention:** in the public setup, many *dev* gold patches cannot pass, for mechanical reasons I
  isolated (§4). If the real Kaggle image confirms it (a CPU notebook is ready), every pilot's dev numbers carry this noise.

Terms used once: *gold patch* = the real upstream fix. *F2P / P2P* = tests that fail before and pass after the fix / pass both times.
*Subprocess backend* = the harness runs the agent's sandbox as plain processes, as the Kaggle starter does. *Snapshot* = the
repo at the commit before the fix.

## 2. What I did
1. **Checks:** confirmed the repo; the Kaggle API answered 200 through the proxy (no token in env).
2. **Format from code, not docs:** I found the starter notebook installs the harness from the dataset
   `metric/gemma-4-developer-agent-wheelhouse` (`swegemma 0.2.11`, `adk-eval-core`, `adk-submission`). I read the loader,
   sandbox, setup and verification code and wrote **`docs/FORMAT.md`**.
3. **Instrument check:** gold-patch validity on a stratified sample of 36 dev tasks, in both backends, using the harness's own
   `verify_task` (§4).
4. **Prior work:** a Sonnet scout surveyed it; the result is in **`docs/PRIOR_WORK.md`**.
5. **Repos:** **sqlglot** (MIT; SQL parser and transpiler) and **networkx** (BSD-3; graph algorithms). Both are pure Python
   with pytest, very active, have zero runtime dependencies, use a **flat layout** (required, see §4), and are outside the dev set.
6. **Pipeline** (`common/`, reusable, nothing pilot-specific):
   - `mining.py`: git-only miner with a counted funnel;
   - `snapshot.py`: snapshots in the dev layout;
   - `validate.py`: the harness's `verify_task` with an empty patch and with the gold patch;
   - `testmap.py`: F2P/P2P;
   - `annotate.py`: gold locations as graph node ids, plus a *verified* minimal reproduction test;
   - `graph_build.py`: released-schema graphs plus a fidelity scorer;
   - `github_text.py`: issue text;
   - `export_swebench.py`: SWE-bench format.
7. **Local runner check:** `swegemma eval --skip-agent-patch` (the host's CLI) loads a held-out task, runs it, and reports
   `resolved=False, exit 1, no errors`, which is the expected baseline. `load_tasks` accepts the extra fields.
8. **Kaggle CPU notebook**, prepared, not run: `notebooks/pilot_d_kaggle_cpu.ipynb` (generated by
   `pilot_d/make_kaggle_notebook.py`). I smoke-tested Part B locally on 2 tasks, end to end.

## 3. Numbers (held-out pilot, `results/heldout_pilot.json`)
**Mining funnel** (fix commits merged 2026-05-01 → 2026-10-31):

| step | sqlglot | networkx |
|---|---|---|
| first-parent commits | 1,123 | 149 |
| fix-type message | 534 | 26 |
| touches tests **and** code | 472 | 22 |
| has a `.py` test file (harness requirement) | 401 | 22 |
| code change = Python inside the package, no protected config | 400 | 22 |
| ≤3 files, ≤200 changed lines | **345** | **21** |
| issue reference in message or test diff | 50 | 9 |

**Built, validated and annotated** (14 issue-linked sqlglot tasks spread over the period, 12 networkx tasks):

| | sqlglot | networkx | all |
|---|---|---|---|
| valid (subprocess / Docker) | 14/14 | 8/12 | **22/26 / 22/26** |
| verified repro test (fails before gold, passes after) | 14 | 7 | **21/22** |
| every edited symbol is a graph node | | | 19/22 |
| single-function fix / single-file fix | | | 14/22 / 17/22 |
| median F2P / P2P tests | | | 1 / 30.5 |

- **Invalid tasks:** 2 with no failing test (the PRs only refactored tests), and 2 where a required test is skipped because an
  optional dependency was not declared.
- **Time per task:** build 9 s (median); validation 10 s in subprocess and 60 s in Docker (median); F2P mapping and annotation
  about 1–2 min each, measured under CPU contention, so upper bounds.
- **Dates:** fixes from 2026-05-04 to 2026-10-20, all after Gemma 4's release (2026-03-31) and its stated training cutoff (Jan 2025).

**Graph fidelity** against 7 released dev graphs from all 4 dev repos (`results/graph_fidelity_dev.json`):
- node ids: **100% recall and 100% precision on 7/7 graphs**;
- node text: 96–99% exact;
- edges: recall 84–96%, precision 78–98%.

## 4. Surprises
1. **src-layout shadowing (verified mechanism).** Neither backend installs the task repo in a way that beats an installed copy.
   Only a *flat* package directory is found first, because pytest prepends the directory of the harness's root `conftest.py`.
   For `src/` layouts (requests, httpx), `import requests` resolves to **site-packages**; I printed `module.__file__` inside the
   sandbox. Result on the dev sample, in both backends:
   - **requests 0/13 valid;**
   - in **3/13 the empty patch already passes**, because the installed requests 2.34.2 already contains the fix;
   - **httpx 0/1** (`module 'httpx' has no attribute 'Stream'`).
2. **Missing test dependencies in the public environment:**
   - fastapi in Docker: 0/10 (`typing_inspection` is absent from the public wheels);
   - fastapi in subprocess: 3/10 (`inline_snapshot` and `dirty_equals` absent);
   - requests needs the `pytest-httpbin` fixture.

   The real scorer probably uses a private, richer wheel set (the code references `gemma-4-developer-agent-metric-data`). Two
   public replicas report 106–111/129. **This is unconfirmed on the real Kaggle image; notebook Part A settles it.**
   Dev-sample totals: subprocess 14/36, Docker 11/36; rich is fine at 11/12.
3. **The released graph's id bug, exactly.** The generator keeps *one* "current class" variable and resets it to `None` after
   any class body. So methods that come after a nested class become module-level, and closures inside methods are labelled as
   methods. Reproducing this gives the 100% node-id match. Also, **every released edge is stored in both directions**, which is
   why codegraph-loc measured only ~32% directed-edge overlap.
4. **Harness wheel-cache bug.** Docker-mode dependency tarballs are cached by a fixed file name, not by wheel directory. My first
   held-out Docker run silently reused the dev set's wheels and reported 14/26 valid. With an isolated `TMPDIR` it is 22/26.
5. **Embeddings gate the prompt.** Without an `.npz`, the harness drops the "Code Intelligence Tools" section from the agent's
   prompt. A held-out set with graphs only is therefore a *different prompt*. The full version should ship an open-model
   embedding file, labelled as such, or report the shift.
6. **The whole touched test file must pass**, not just F2P. A test patch that only touches fixtures breaks the harness, so I
   filter those out (71 sqlglot candidates). The harness's own `pytest.ini` overrides the repo's pytest config.
7. **AI-written gold patches.** 85 of 345 sqlglot candidates carry agent markers (`[CODEX]` and similar); 2 of the 22 valid tasks
   do. This is flagged per task. A 2026 benchmark now partly measures agents against other agents' fixes.
8. **A hang bug** (sqlglot, an infinite parser loop) costs the full 300 s harness timeout per failed attempt. It also broke naive
   F2P labelling (no JUnit report on timeout); this is fixed with a per-test timeout for labelling only.
9. **Issue text is the one blocked step here.** The GitHub API for third-party repos is not available in this session. I asked
   once for API access via `add_repo` (push level) and it was **denied by policy**; I did not retry. WebFetch only paraphrases.
   GH Archive's 2026 feed is too sampled: 1 event in a week for two very active repos. The fetch script is ready and runs in
   the Kaggle notebook (Part B) or on your laptop.
10. **31/129 dev tasks predate Gemma 4's stated training cutoff.** That is a contamination risk the held-out set avoids.

## 5. Closest prior work (details in `docs/PRIOR_WORK.md`)
- **OOD-45** (Kaggle dataset, "Leakage-Audited Bug-Fix Tasks for Gemma 4", UNVERIFIED) and **gemma4-agent-noise-study**
  (216 tasks converted from SWE-rebench): the closest "extra tasks" competitors. Neither shows harness-backed validation,
  graph-exact fidelity, or verified payloads.
- **codegraph-loc** (Apache-2.0): graph generator plus localization labels, with no gold execution. **I reuse it as a library,
  with credit**, and add the exact released id, text and edge rules.
- **ORACLE-SWE** (arXiv 2604.07789): injects gold location, repro test and other signals. It finds the repro test helps most.
  This is the main novelty threat to a "graded hints" framing; our verified repro tests are its payload type, in this harness.
- SWE-rebench, SWE-bench-Live, SWE-Gym and SWE-smith: continuous or static mining with Docker F2P/P2P. None targets this
  harness, ships graphs, or ships verified repro payloads.

## 6. Framing decision (I led; reasons)
| option | novelty | generality | relevance | verifiability | verdict |
|---|---|---|---|---|---|
| A. Standalone resource paper | low–mid (overlaps OOD-45, noise-study, ORACLE-SWE, codegraph-loc) | mid | high | high | **fallback** |
| B. Substrate of the main method paper: OOD test set + verified injection payloads + instrument audit | comes from the method | **raises it** (non-dev repos, post-cutoff) | high | **raises it** | **recommended** |
| C. Dev-set validity audit as its own contribution | mid if confirmed on Kaggle; partly known (106–111/129 replicas) | low | high | high | fold into B |

**Why B:**
- CLAUDE.md's ambition rule wants a new mechanism as the core. This pilot produces infrastructure, not a mechanism.
- The judges' *Quality = generality beyond this competition* criterion is where the main paper is weakest, since every pilot
  measures on fastapi, rich, requests and httpx. A held-out set from different domains, validated by the harness itself, fixes
  that at near-zero GPU cost.
- The verified repro tests and graph-id gold locations are exactly the "inject a test / a location" payloads the other pilots need.

## 7. Go/no-go and cost of the full version
**GO**, on two conditions:
1. Notebook Part B reproduces ≥90% of these verdicts in the real Kaggle image.
2. Issue text can be fetched (Kaggle with Internet ON, or your laptop).

**Full version: 100–120 valid tasks from 6 repos, about 2.5–3 working days (Nov 1–3), 0 L4x4 hours to build.**
- **Day 1:** screen and add 4 more flat-layout, low-dependency repos with ≥20 issue-linked fixes since May. Candidates to
  screen: pygments, Python-Markdown, pyparsing, sqlparse, more-itertools, sympy. Cap each repo at about 25 tasks so sqlglot
  does not dominate. From two repos alone I project about 65 issue-linked valid tasks, from the measured yields of 100% for
  sqlglot and 67% for networkx.
- **Day 2:** the run itself. About 150 candidates through build, validate, map, annotate and graphs: ~8–10 CPU-hours, ~2.5 h
  wall with 4-way parallelism. Also embeddings from a small open model, labelled as such.
- **Day 3:** fetch issue text; screen problem statements for leakage (automated check plus a spot check); write the datasheet;
  you run the Kaggle CPU notebook (~1–2 h, CPU only).

**Using it** (the other pilots' runs) is what costs GPU. *Estimate from the scorer's 12 h / 120 tasks envelope:* ~6 min per
task on 4×L4, so a 40-task subset is ≈4 L4x4-hours and all 120 tasks ≈12 L4x4-hours, which is most of a week's 15. I suggest a
40-task held-out subset per headline comparison.

## 8. Questions only you can answer
1. **Run the Kaggle CPU notebook?** No GPU. Part A needs only competition data; Part B needs Internet ON. It attaches
   competition data to an internet-enabled, non-submission notebook. I believe that is allowed, but it is a rules question, so
   your call.
2. **If Part A confirms that requests/httpx dev tasks are unsolvable on Kaggle:** report it to the host? That touches the
   competition, so your call.
3. **Open question to confirm with the host:** the host said regenerated graphs from public upstream repos should be fine with
   citation and a link to the Kaggle dataset. Please get that confirmed in writing before we release graphs. (Graphs for *non-dev*
   repos are our own work, but their schema mirrors the dataset.)
4. GitHub API in this environment: if you want issue fetching here instead of on Kaggle, it needs your decision on credentials.
   I did not and will not add tokens myself.
5. Do you accept the framing change (B over A)? Everything here works either way; only the paper's emphasis changes.

## 9. Reproduce
```bash
python -I common/mining.py <clone> --repo tobymao/sqlglot --pkg sqlglot --since 2026-05-01 --out cand.jsonl --funnel funnel.json
python -I pilot_d/build_tasks.py cand.jsonl <clone> work/heldout --ids $(jq -r '.repos[0].instance_ids[]' pilot_d/manifest.json)
python common/validate.py --tasks work/heldout/tasks.jsonl --snapshots work/heldout/snapshots --backend subprocess --out val.jsonl
python common/testmap.py ... ; python common/annotate.py ... --verify ; python common/graph_build.py build <root> sqlglot <base> graphs/
```
The interpreter must have `swegemma` from the wheelhouse plus `codegraph-loc@1e8e0ab`. For Docker, set `KAGGLE_SANDBOX_DIR` to
the competition's `sandbox/` and give each wheel set its own `TMPDIR`. Log line for `research/log.md` (on main, not modified
here): `2026-10-31 pilot-D build+validate 26 held-out tasks, 0 GPU-h, keep`.
