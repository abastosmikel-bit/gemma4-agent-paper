# History of the experiments (plain notes for writing the paper; not paper prose)

Written by pilot C on 2026-11-02 for someone who was not in the sessions. Chronological. Each entry gives what it asked,
what we ran, what came out, and what it changed in our thinking. Numbers are single runs unless stated. Exact numbers and
their sources are in `docs/CLAIMS.md` and `RESULTS.md`; terms are in `docs/GLOSSARY.md`. GPU time is in L4x4 hours
(4 L4 GPUs on Kaggle, billed at 2× quota).

## Setting

- **The competition:** Kaggle "Gemma 4 Developer Agent". An agent (built on Google's ADK and the official sample agent)
  must fix Python bugs. A fix counts if the task's required tests pass with the agent's patch.
- **Models:** four Gemma 4 sizes, e2b, e4b, 12b and 31b. Served by vLLM on 4 GPUs with a 32,768-token context window.
- **Dev data:** 129 tasks (fastapi 67, rich 48, requests 13, httpx 1).
- **Pilots:** four ran in parallel, A, B, C and D. This file is written from pilot C's side.

## Pilots A, B and D (as far as pilot C knows them)

| Pilot | Topic | What pilot C knows |
|---|---|---|
| A (`pilot/a-skills`) | skills: giving the agent reusable instructions at a fixed point in its run | Uses the 40-tool-call / 15-minute budget that C adopted. Found first that `AgentTool` sub-agent calls do not appear in the main trace, and that compaction drops `load_skill` outputs; C confirmed both. C compared its `common/` code with A's once (REPORT §9). |
| B | expression: can the model write the change once it knows what to change | Named in `DECISIONS.md` as the "exact-change expression" slice of the shared design. C's L5 rung (the exact diff) and the use step overlap with B's question. Nothing else known here. |
| D | held-out tasks: new tasks none of the pilots tuned on, used as the out-of-distribution test set | Exports tasks in the format of `docs/PROBE_INPUT.md`. Found that in src-layout repos (requests, httpx) the tests import the host's installed copy of the library; C confirmed it on all 14 such dev tasks (2026-11-02). D's notebooks D1/D2 are not described anywhere C can read. |

## Pilot C, in order

### 2026-10-31 — Start: oracle hints on full agent runs (planned, then changed)
- **Asked:** for each model size, which stage limits a small agent: finding the file, finding the function, reproducing
  the bug, or writing the fix?
- **Plan:** give the agent the gold location (file, function, test names) as a hint ("oracle hints O0 … O-all") and
  measure how much the solve rate moves.
- **CPU groundwork (no GPU):**
  - computed every task's gold location;
  - matched the scorer's rule for which tests count (129/129);
  - found 21/129 tasks whose tests need a name or message the issue text never mentions;
  - estimated a file hint carries ~5.3 bits and a function hint ~4.5 more.
- **Changed thinking:** small models solve almost nothing, so solve rates floor at 0% and an oracle ablation would show
  nothing for e2b/e4b.

### 2026-10-31 — Rethink: the information-ladder probe
- **Asked:** can we measure what each piece of information is worth without needing the agent to finish a task?
- **Design (frozen in `docs/PLAN.md` at 168d115):** take the agent's real context at two moments.
  - **S-find:** right after reading the task.
  - **S-use:** right after reading the gold function.
  - Add information step by step: L0 nothing, L1 file, L2 + function, L3 + test, L4 + the change in words, L5 + the exact
    diff. Also add single hints and wrong-hint controls.
  - Measure how much more likely the model makes the correct next action, in nats (depth 1), and what it actually does
    when sampled (depth 2).
- **Hypotheses H1–H6** were written before any data.
- **Changed thinking:** this became the spine of the paper (`DECISIONS.md`).

### 2026-10-31 — C00: gold check (CPU on Kaggle)
- **Asked:** which dev tasks are valid in the official sandbox (the gold patch passes and no patch fails)?
- **Ran:** all 129 tasks, each with the gold patch and with no patch.
  - First attempts failed: an empty notebook cell, then Kaggle's default Python 3.13, which rejects the competition's
    Python 3.12 wheels.
  - Fixed by running inside the official starter's pinned environment.
- **Came out:**
  - 74 gold patches resolve; 71 tasks are valid;
  - 34 fastapi tasks miss a test module;
  - no requests or httpx task is valid;
  - 3 tasks pass with no patch.
- **Changed thinking:** only valid tasks can be used, and the sandbox's environment, not the model, decides a lot. This
  started the benchmark-audit thread (claim 5).

### 2026-10-31 — C01: smoke timing (0.84 h)
- **Asked:** how long a task takes per size, and how often ADK compacts the history.
- **Ran:** 3 tasks × 4 sizes, plus e4b with hints.
- **Came out:**
  - 12b takes ~465 s per task;
  - compaction fires in every 12b and 31b run, and the task prompt gets compacted;
  - 2 of 15 runs end with a context-window error.
- **Changed thinking:** compaction is routine, not an edge case. The context errors were noticed but not yet understood.

### 2026-10-31 — Safety work before the big run
- **Freeze protection.** A forum report said vLLM's tool parser can loop forever. We reproduced it offline and added
  per-request timeouts plus a watchdog to every GPU notebook.
- **First C03 attempt failed (0.29 h):**
  - the 31b server returned an error on its first scoring request;
  - stopping it left GPU memory occupied, so the next model could not start.
- **Fixes:** stop servers as process groups, wait for memory before the next start, leave more memory headroom, keep error
  messages, and splice the scored tokens correctly for 31b/12b (their chat templates add an empty "thinking" block).

### 2026-11-01 — C03: the probe (2.92 h)
- **Asked:** H1–H5 on 30 valid tasks for 31b, e4b and 12b. e2b and 12b's sampled actions were cut by the time limit.
- **Came out:**
  - **H1 supported.** Naming the file and function makes the correct read +19 to +33 nats more likely at the find step.
    After the agent has read the right code, the same hint changes the correct edit by only −2 to +2.
  - **What drives the edit:** the change described in words (+11 to +15) and the exact diff (+29 to +42).
  - **Graph:** a graph-tool output mostly told the model the file, not the function.
  - **Wrong hints:** a wrong file hurts. A wrong function in the right file still helps compared with nothing, because
    the file is right.
  - **Behaviour:** 31b rarely edits right after reading the right code (0 of 60 first actions); it reads more or runs
    commands first. e4b edits at once.
  - **H2, H4 trend and H5 not supported.**
- **Changed thinking:**
  - Location is a *finding* problem; once found, the bottleneck is *what to change*.
  - "Is the next action right?" mixes willingness to act with ability, so report them separately.

### 2026-11-01 — C05: does the probe predict real outcomes? (2.02 h)
- **Asked:** H6. Does the probe's per-task number predict which tasks a location hint lets 12b solve in full runs?
- **Ran:** 12b on the 30 tasks, no hint (O0) vs file + function + test names (O-all).
- **Came out:**
  - 6 vs 13 resolved;
  - H6 not supported (AUC 0.43);
  - 23 of 60 runs ended with a context-window error, and all 7 tasks the hint "rescued" were ones where the no-hint run
    had crashed.
- **Found the cause:**
  - the agent asks for 16,384 output tokens, and vLLM refuses any request whose prompt plus that exceeds 32,768, so prompts
    must stay under 16,384;
  - ADK only compacts after the previous prompt passed 14,336, so one large tool output skips straight past the limit.
- **Changed thinking:**
  - the hint's measured benefit was mostly "the run didn't crash";
  - this setup bug affects every agent built on the starter (claim 4).

### 2026-11-02 — CPU work while GPU runs were queued
- **Claim sheet:** `docs/CLAIMS.md`.
- **Repro of the crash bug:** `repro/context_window/` on `pilot/c-bottleneck`; private until submission. It uses the real
  ADK compaction with a fake server, and shows the one-line fix (`max_output_tokens: 8192`).
- **Audit:** a reason for each of the 58 invalid tasks (`results/C00_audit.md`). Confirmed D's src-layout finding: in
  14/14 requests/httpx tasks the tests import the host's library, not the repo; 6 become valid if the repo's code is
  imported.
- **Also:** related-work list (`docs/RELATED_WORK.md`) and a reproduction guide (`REPRODUCE.md` on the pilot branch).

### 2026-11-02 — C06: the validation again, with the fix (2.71 h)
- **Asked:** do crashes disappear with `max_output_tokens: 8192`, and what is the hint worth without them? Also measured
  directly what compaction keeps (pre-registered in `docs/PLAN_C06_validation_fix.md`).
- **Came out:**
  - crashes fell from 14 to 0 (no hint) and from 9 to 2 (hint);
  - no-hint solves went from 6 to 9, hinted stayed at 13; the hint effect shrank to +4 net, not significant;
  - H6 failed again (AUC 0.27);
  - after compaction, the original task statement was in 0 of 1,472 requests; summaries keep ~0% of its 5-word phrases
    and about a third of its words;
  - failed edits rose from 6 to 33. They are the model quoting code that is not in the file, mostly after compaction
    (32/33 never matched; 31/33 after the first compaction);
  - the sample agent's `code_analyzer` sub-agent is never compacted and overflowed in both runs that used it.
- **Changed thinking:**
  - the crash fix works;
  - the location hint's real effect on solving is modest;
  - compaction erases the task and the code views, which shows up as edits against code that isn't there;
  - the probe measures something real about information, but its per-task numbers don't forecast solve flips.

### 2026-11-02 — C04: probe follow-up (1.41 h)
- **Asked:**
  - complete 12b;
  - add an unrelated-file graph as a control;
  - split each score into "call this tool now" vs "with these arguments".
- **Came out:**
  - H1 holds for all three sizes with 12b complete;
  - at the find step the right graph beats an unrelated one by 4.6–9.8 nats, about what naming the file in text gives;
  - at the use step the unrelated graph is as good or better, so the gain there is the extra tool turn, not the content;
  - words naming the function beat every graph at find by 7–29 nats;
  - the split shows a graph turn changes how ready the model is to call a tool now (up for e4b, down for 12b/31b because
    of their templates), while the file information sits in the arguments.
- **Changed thinking:** claim 3 became "find: the graph helps through the file it names; use: not through content"
  (`docs/CLAIMS.md`).

### 2026-11-02 — C03v: do the probe's sampled edits pass the tests? (Kaggle CPU, no GPU)
- **Asked:** apply each edit the probe sampled at the use step on its own and run the task's required tests. Use the
  result to finish the information threshold ("exact or passes" instead of "exact" only).
- **Came out:**
  - 435 of 1,746 sampled first actions were edits that applied and could be tested;
  - the lowest rung with a right edit is L4 (the change in words) for the median e4b task; for 12b and 31b it is above L5;
  - 12b and 31b score low because they rarely edit as their first action (2% at L2, 30–46% even with the exact diff),
    not because they edit wrongly: 69–80% of their edits with the diff pass. e4b edits almost every time but often
    wrongly;
  - pass rates are higher when the change is described in words than when the location is named: e4b 37% vs 28% (20%
    with neither), 31b 15% vs 2% (0%). Only a few of the 27 paired tasks change, so the tests are weak; only e4b's
    words vs nothing survives correction;
  - exact-match grading misses most correct edits: 54 of e4b's 65 passing edits below L5 are not exact copies of the gold
    fix.
- **Changed thinking:**
  - the threshold is real for e4b, but for the larger models it mostly measures willingness to edit right away;
  - grading by tests, not exact match, is necessary.

### 2026-11-02 — D1 and D2 built, frozen and dry-run (no GPU yet)
- Pilot D exported its held-out tasks (`notebooks/D0a_heldout_fetch__CPU.ipynb`, then `notebooks/D0b_heldout_export__CPU.ipynb`
  on `pilot/d-heldout`). Pilot C built the notebooks that re-check the claims on them, as variants of its own:
  - `notebooks/D1_heldout_probe__L4x4.ipynb` (C03/C04): claims 1 and 3 on 24 held-out tasks, 3 sizes, depth 1 and 2;
  - `notebooks/D2_heldout_rollouts_12b__L4x4.ipynb` (C06): claims 2 and 4 and the held-out solve rate, 12b, no hint;
  - `notebooks/D1v_test_verify__CPU.ipynb` (C03v): do D1's sampled edits pass the tests (CPU).
- Only tasks whose statement comes from an issue are used (a PR body often describes the fix); sympy is excluded.
- The replication criteria and the analysis code were frozen at 682a34f before any held-out data existed. Each notebook ends
  with a cell that writes the final tables and figures, tested on synthetic data.
- Estimates (L4x4 h, from C03/C04/C06's measured rates): main version D1 ≈ 1.55 + D2 ≈ 1.25 = **≈ 2.8 h** (range 2.4–3.6);
  fallback D1 depth 1 only **≈ 1.15 h** (range 1.0–1.5). Waiting for the coordinator's OK.

### Next — D runs
- Run D0b (pilot D), then D1 and D2 (after the coordinator's OK), then D1v on CPU.

**GPU used by pilot C:** 0.84 + 0.29 + 2.92 + 2.02 + 2.71 + 1.41 ≈ **10.2 L4x4 h** (C00 and C03v ran on CPU).
