# Pilot C — Information-ladder probe: study plan (pre-registered before any GPU run)

Status: frozen when committed; the commit hash is recorded in `DECISIONS.md` on `paper/main`.
Any later change goes into §11 "Deviations" with date and reason; nothing above it is edited.

## 1. Question

For each Gemma 4 size, how much does each piece of information raise the probability of the
correct next action? That is: where is the task, what must change, how does it change in code,
and does the same location help when it arrives as graph-tool output instead of text?

The probe separates **find** (choosing where to look) from **use** (writing the change once the
right code has been read). It works without full agent rollouts, so it does not floor at 0%
resolved.

## 2. Units and sizes

- **Tasks:**
  - Start from tasks that are **valid on Kaggle**: gold passes and no-patch fails, per notebook 00.
  - Keep those **eligible**: 1 existing non-test `.py` file changed, 1–2 enclosing functions or
    classes, ≤ 40 changed lines, ≥ 1 required test.
  - Keep those that have a constructible canonical edit (§4.3).
  - Order: notebook 00's pre-registered order per repo (`selection.eligible_valid_in_order`),
    taken round-robin across repos.
  - Cap: 30. With fewer than 20, the run goes ahead but is labelled low-power.
- **Sizes:** e2b, e4b, 12b, 31b (`gemma-4-*-it-qat-w4a16-ct`). Run order in the session: 31b first
  (it writes the "words" rung), then e4b, 12b, e2b. A time guard skips the tail.
- **Server:** the starter-identical vLLM server (`max_model_len=32768`, gemma4 tool and reasoning
  parsers, no LoRA).

## 3. States (where in a trajectory the probe is taken)

Both states are real agent contexts. They are captured by running the actual swegemma agent loop
(the official sample agent, 40 calls / 15 min config) against a capture server that scripts
exactly one action. So system prompt, tool schema, task prompt, workspace layout and tool-message
format are byte-identical to what the agent sends.

| State | Context | Correct action (target) |
|---|---|---|
| **S-find** | system + task prompt (+ rung) | `read_file(filepath=<gold file>, start_line=<gold fn start>, end_line=min(end, start+149))` |
| **S-use** | S-find + the agent's `read_file` call on that span + the real harness response | `edit_file(filepath, old_string, new_string)` = canonical gold edit (§4.3) |

## 4. Conditions

### 4.1 Text rungs (delivered by appending to the problem statement, as `pilot_c/hints.py` does)

| Id | Content (cumulative ladder) |
|---|---|
| L0 | none |
| L1 | + gold file path |
| L2 | + gold function (dotted name, def line) |
| L3 | + reproduction test: the required test functions' source from `test_patch` (≤ 60 lines) + whether the test file exists yet |
| L4 | + the change in words (1–3 sentences, no code; §4.4) |
| L5 | + the exact diff (gold patch restricted to the gold file) |
| T | reproduction test only (no location) |
| W | change in words only (no location) |

### 4.2 Graph rung: same location, delivered as graph-tool output

- **Content:** the induced subgraph on the gold symbol plus up to 10 non-test neighbours, taken
  from the harness's own `get_code_neighbors` and `get_code_subgraph` (tests removed so the rung
  carries location only).
- **Delivery:** a synthetic agent turn `get_code_subgraph(nodes=[gold symbol, neighbours…])`
  followed by its tool message, placed right after the task prompt. In S-use it sits before the
  read.
- **Encodings** (identical nodes and edges):

  | Id | Encoding |
  |---|---|
  | G-json | the harness's native JSON (`{"status","nodes","edges":[{"from","to","type"}],…}`) |
  | G-edges | one line per edge: `A -[calls]-> B` |
  | G-adj | one block per node: `A: calls B, C; called by D` |

- **Related work:**
  - Markowitz et al., *Tree-of-Traversals* (arXiv 2407.21358, 2024): LLMs acting over KG queries.
  - Markowitz et al., *KG-LLM-Bench* (arXiv 2504.07087, 2025): five textualizations × seven LLMs;
    the rendering changes reasoning accuracy.
  - New here: the graph comes from a code agent's own tool, it is compared against the same
    location given as text, and the comparison runs across sizes of one model family.
- **Caveat:** the graph gives the location as the "query focus", not as "the bug is here". That
  is a weaker cue than L2. The comparison with L2 is reported with that caveat.

### 4.3 Canonical correct action (one per task, identical across conditions)

- **Arguments:** in tool-schema order. `read_file`: `filepath, start_line, end_line`.
  `edit_file`: `filepath, old_string, new_string` (no `allow_multiple`).
- **Edit construction** (same as `docs/PROBE_INPUT.md` on `paper/main`):
  - `old_string` covers the base lines from the first to the last gold-changed line inside the gold
    function. A pure insertion gets its preceding line as an anchor.
  - Grow by one line at a time until `old_string` is unique in the file. `new_string` is the
    matching new text.
  - Gold changes outside the function (e.g. imports) are not part of the target; their count is
    reported.
- **Rendering:**
  - Tokenize as an assistant message with one `tool_calls` entry, using each size's own chat
    template through the server's `/tokenize` endpoint. The 4 sizes use 3 different templates.
  - Target tokens = tokens of [context + target] minus tokens of [context + generation prompt].
    The notebook asserts a prefix match per cell.
- **Depth 1** scores with thinking disabled (`enable_thinking=false`), so the target directly
  follows the generation prompt, as the template defines for non-thinking turns.

### 4.4 The "change in words" rung

- Written once per task by 31b, in-session, before any probing:
  - input: the gold diff;
  - instruction: 1–3 plain-English sentences, no code lines; names of functions and parameters
    allowed;
  - settings: thinking off, temperature 0, ≤ 300 tokens.
- **Leak check:** reject if any 20-character substring of a stripped `+` line of the diff appears
  in the description, or if it is longer than 600 characters. On rejection retry once with a
  stricter instruction; on a second failure the task has no W/L4/L5/X-words cells.
- Caveat: 31b describes the change used by every size, including itself.

### 4.5 Wrong-hint controls (matched length; each paired with its correct counterpart)

Wrong content is rendered with the same template as the correct rung. Its character length must
be within ±15% of the correct rung; the closest length wins, ties broken by sorted name.

| Id | Built from | Compared with |
|---|---|---|
| X-file | another non-test `.py` file of the same repo (from the code graph's modules) | L1 |
| X-func | correct file + another function or class in the **same file** | L2 |
| X-graph | G-json with the X-func symbol as focus | G-json |
| X-test | L2 + another valid task's (same repo) reproduction test | L3 |
| X-words | L3 + another task's description | L4 |

If no candidate meets ±15%, the closest one is used and its ratio is reported.

### 4.6 Which cells run

| | S-find | S-use |
|---|---|---|
| Depth 1 (target log-likelihood) | L0, L1, L2, T, W, G-json, G-edges, G-adj, X-file, X-func, X-graph (11) | all 16: L0–L5, T, W, G×3, X×5 |
| Depth 2 (one sampled next action) | L0, L1, L2, G-json, G-edges, X-func (n = 1) | L0, L2, L3, L4, L5, T, W, G-json, X-func, X-test (n = 2) |

L0 depth 1 runs twice per state to measure numerical noise.

## 5. Measures

- **Depth 1:**
  - `logp` = sum of target-token log-probabilities (vLLM `prompt_logprobs`); also per-token mean
    and target length.
  - Per task and size: Δ = logp(condition) − logp(reference). The reference is L0, or the matched
    correct rung for X-*. The unit is nats: the usable information of the rung.
- **Depth 2 (sampled with the agent's settings):** temperature 0.2, top_p 0.95, thinking on with
  budget 4,096, max 6,144 new tokens, seeds 1 and 2. Classification of the response:

  | Metric | S-find | S-use |
  |---|---|---|
  | `tool_call` | parsed call (else malformed) | parsed call (else malformed) |
  | location | `hit_file`: the call touches the gold file (`read_file` path or a shell command naming it); `hit_func`: `read_file` range overlaps the gold function | `edit_gold_file`; `applies` (old_string occurs exactly once, or once after whitespace-flexible matching) |
  | content | — | `on_target` (changed lines overlap the gold changed lines); `exact` (new text equals gold after whitespace normalization) |
  | X-* only | `followed_wrong` (touches the wrong file or function) | `followed_wrong` |

- **Tests pass:** each S-use edit is applied alone to the base snapshot. The required tests run in
  a separate CPU notebook (no GPU) with the scorer's verification (`solves`).
- **Information threshold per (task, size):** the lowest ladder rung L0…L5 at which at least 1 of
  2 S-use samples is `exact` or `solves`; otherwise ">L5".

## 6. Hypotheses (directional, fixed now)

- **H1 find vs use.** Location rungs raise the S-find target (Δ(L2−L0) > 0 for every size). At
  S-use, after the agent has read the gold code, they add much less:
  median Δ_use(L2−L0) < median Δ_find(L2−L0).
- **H2 what/how and size.** The S-use gain from words, Δ(L4−L3), increases with size. The gain
  from the exact diff, Δ(L5−L4), decreases with size.
- **H3 graph encoding.** For e2b and e4b, G-edges and G-adj beat G-json at S-find (higher Δ vs
  L0). For 31b the encodings differ by < 0.3 nats median. All graph encodings give less than the
  text rung L2.
- **H4 wrong hints.** Δ(X − L0) < 0 at S-find for X-file, X-func and X-graph (misleading, not
  just useless), and the harm is larger for smaller sizes (more over-trust).
- **H5 small models' failure.** e4b at S-use reaches `on_target` in ≥ 50% of tasks at L5 but in
  ≤ 20% at L2. If even L5 stays below 50%, the bottleneck is expression (pilot B's question), not
  information.
- **H6 validity.** Δ_use(L3−L0) from depth 1 predicts which tasks flip from fail to pass in the
  12b rollout validation (§8): AUC ≥ 0.65.

## 7. Statistics

- **Paired over tasks within a size:**
  - continuous Δ: Wilcoxon signed-rank;
  - binary depth-2 outcomes: exact McNemar.
  - Effects are reported as median Δ (nats) and rates, with 95% bootstrap CIs over tasks
    (10,000 resamples).
- **Trends over the four ordered sizes:** Page's L test on per-task Δ (H2, H4).
- **Multiple comparisons:** Holm correction within each hypothesis family (per size), α = 0.05.
- **Ladder cumulation** (depth 2): Cochran's Q across L0–L5.
- **H6:** ROC AUC of Δ for fail→pass flips, with a bootstrap CI.
- **Labelling:** every analysis not listed here is labelled exploratory. Every number goes into
  `RESULTS.md` with notebook version and commit.

## 8. 12b rollout validation (built runner, notebook 02 with a new PLAN)

- **Design:** O0 vs O-all on the probe tasks with the built hint renderer (O-all = file + function
  + test names). 1 seed each, 40 calls / 15 min, concurrency 5, scorer-consistent `resolved`
  (non-empty patch).
- **Expected outcome changes on 30 tasks:**
  - 12b no-hint base rate ≈ 15–30%. The forum reports 4/31 on random tasks; our tasks are
    smaller.
  - Run-to-run noise flips ≈ 15% of tasks (forum, 31b), so ≈ 2 noise flips each way.
  - Hint effect +3 to +6 tasks.
  - Expected discordant tasks: ≈ 7–11 (fail→pass 5–8, pass→fail 2–3).
- **Minimum that makes it worth it:** ≥ 6 discordant tasks with ≥ 4 fail→pass. Fewer cannot
  support H6 (an AUC on 3 positives is uninformative).
- **Sequential rule:** run both conditions on the first 15 tasks. If fewer than 2 are discordant,
  stop (saves ≈ 0.6 h).
- With 30 tasks a significant McNemar needs about 9 vs 1, so the validation is about prediction
  (H6), not about proving that hints help.

## 9. Exclusions (decided now, applied before any outcome is seen)

1. Not valid on Kaggle (notebook 00: gold fails or no-patch passes).
2. Not eligible (§2).
3. No constructible canonical edit, or gold-changed lines outside the 150-line read span.
4. Largest cell (S-use + L5) longer than 28,000 tokens.
5. Words leak check failed twice: that task's W/L4/L5/X-words cells are missing; analyses use
   complete cases per comparison.

Malformed or empty depth-2 responses are outcomes, not exclusions.

## 10. Cost (L4x4 hours, estimated; refined after notebook 01's timings)

| Item | Estimate |
|---|---|
| install + capture (CPU in session) | 0.15 h |
| 4 vLLM start-ups | 0.45 h |
| words (31b) | 0.05 h |
| depth 1: 27 cells × 30 tasks + 2 noise cells per size (~7k tokens each, no prefix cache with prompt logprobs) | 31b 0.4 h, 12b 0.15 h, e4b/e2b 0.1 h |
| depth 2: 26 generations × 30 tasks per size (~1.2k new tokens each) | 31b 0.5 h, 12b 0.25 h, e4b/e2b 0.2 h |
| **Probe total** | **≈ 2.2 h (range 1.6–3.0), hard stop 2.9 h** |
| Probe-lite (20 tasks; depth 2 only at S-use L0/L2/L5) | ≈ 1.2 h |
| 12b validation | ≈ 1.2 h (0.6 h if stopped at 15 tasks), hard stop 1.5 h |
| CPU verification of depth-2 edits | 0 GPU h |

## 11. Deviations

All found during CPU validation and papermill dry runs on 2026-10-31, before any GPU run, so no outcome
data had been seen.

1. **Reproduction-test rung source (§4.1 L3/T).** Shown as the test patch *as it reads after applying*:
   context + added lines, no removed lines, per hunk, ≤ 60 lines. The required-test functions' source
   alone was dropped. Reason: the scorer takes test names from hunk headers, which need not enclose the
   change. In `rich_3454` the named test is `test_wrong_type`, but the change is to the parametrize data of
   another test, so the function-source rule gave an empty rung.
2. **Pure deletions (§4.3).** If `new_string` would be empty, both strings include one neighbouring line
   as anchor. Without the anchor the edit leaves a stray blank line and does not equal the gold patch
   (`requests_7315`). After this, the canonical edit equals the gold patch on 9/10 local tasks; the
   remaining one differs only by its gold changes outside the function, by design.
3. **S-use context (§3).** The captured `read_file` assistant turn carries no reasoning text, because the
   capture server emits none. In a real run with `include_thoughts: true` that turn would also contain the
   model's thoughts.
4. **Rule 4 (§9).** Implemented as a per-cell check: a cell is skipped if context + target exceeds 28,000
   tokens; it is reported, not imputed.
5. **Session safety.** If the API self-check fails on the first size, the session stops instead of
   starting the other servers.
6. **Notebook names (2026-10-31, no design change).** References in this frozen plan map to full paths:
   "notebook 00" = `notebooks/C00_gold_check__CPU.ipynb` (output `C00_gold_check.json`);
   "notebook 01" = `notebooks/C01_smoke_timing__L4x4.ipynb`;
   the probe = `notebooks/C03_probe__L4x4.ipynb` (output `C03_probe.json`);
   its CPU test verification = `notebooks/C03v_test_verify__CPU.ipynb`.
   "notebook 02" in §8 means the 12b validation notebook, which is not built yet and will get its own C-number.
7. **Probe server memory settings (2026-10-31, after the failed Kaggle run of `notebooks/C03_probe__L4x4.ipynb`).**
   - What happened: the 31b self-check got HTTP 500 from the server on its first request, and the cause was not captured.
   - Leading, unverified hypothesis: out of memory in `prompt_logprobs`. vLLM computes a full-vocabulary (262k)
     log-softmax per prompt token in chunks of `max_num_batched_tokens` (default 2048 on L4), with only ~10% of GPU
     memory left at `gpu_memory_utilization=0.9`.
   - Change: probe servers now run with `gpu_memory_utilization=0.75` and `--max-num-batched-tokens 1024`. These are
     scheduling and memory settings only and do not change model outputs. Agent rollouts
     (`notebooks/C01_smoke_timing__L4x4.ipynb`) keep the starter settings.
   - HTTP error bodies and the server log are now kept, so the next failure shows its cause.
8. **Target tokens with the 31b and 12b templates (§4.3), found offline with the real chat templates before any result.**
   - With thinking off, these templates add an empty thought block to the generation prompt after a user turn, and
     the rendered assistant turn does not contain it.
   - So for S-find the target is defined as the tokens of the turn after its header, appended to the real
     generation prompt ("spliced"): exactly what the model conditions on, followed by the call.
   - Everywhere else (S-use, every e2b/e4b cell) the original definition holds ("direct"). Each scored cell records
     its `mode`.
   - Without this change all 31b and 12b S-find cells would have failed the prefix check.
9. **Operational (no design change).**
   - Each size runs isolated, with its own results file.
   - A failed size no longer ends the session. The session stops after two consecutive self-check failures, a
     second server freeze, or GPU memory not being released.
   - The size order stays 31b → e4b → 12b → e2b: one server start per size, and 31b first because it writes the
     words rung.

**Added 2026-11-01, after the C03 results were seen** (`results/C03_probe.json`, `results/C03_tables.md`). Items 10–13
describe `notebooks/C04_probe_followup__L4x4.ipynb`. Item 10 completes the frozen design; items 11–13 are exploratory
additions, labelled as such in every table, and do not change H1–H6.

10. **Completing the design in a second session.** C03's time guard skipped e2b, 12b depth 2, and 12b depth 1 for 3
    tasks. C04 runs exactly those cells, with the frozen definitions.
    - It reuses C03's records, captured contexts, and the change-in-words rung that 31b wrote in C03, read from C03's
      output. So every size sees byte-identical inputs, and 31b does not rewrite the words.
    - Server settings are as in deviation 7. Cells C03 completed are not rerun.
11. **X-graph at depth 2 (exploratory).** S-find, n = 1, all four sizes. It answers whether the graph's focus changes
    where the model reads (`hit_func`), next to G-json's existing depth-2 cells.
12. **G-null, an unrelated-file graph control (exploratory).**
    - Content: the same synthetic `get_code_subgraph` turn and JSON encoding as G-json, carrying another probe task's
      gold subgraph. The donor is from the same repo if possible. None of its nodes may lie in this task's gold module,
      and its gold file must differ. The donor's JSON length is closest to this task's G-json (ratio reported; ±15%
      target).
    - Cells: depth 1 at S-find and S-use, depth 2 at S-find (n = 1), all sizes.
    - Reading: G-json − G-null is the location content delivered as graph output, with the same context ending (a tool
      response). G-null − L0 is the ending effect plus whatever the unrelated graph suggests. At S-find, compare it with
      X-file − L0 (a wrong file in text). At S-use the file has already been read, so G-null − L0 is mostly the ending
      effect.
    - At depth 2, `followed_wrong` for G-null means the call went to the donor's file or symbol.
13. **Action / arguments split (exploratory).** Every newly scored cell records `logp_action` (target tokens up to the
    first token that depends on the arguments, found by also tokenizing the same call with empty arguments) and
    `logp_args` (the rest); they sum to `logp`. With the real templates the action part is `<|tool_call>call:<tool>`
    plus at most the opening brace (`tests/test_template_scoring.py`). To get the split where C03 already scored the
    cells, S-use L0, L2, L5 and W are re-scored for 31b, e4b and 12b (rows marked `purpose: rescore`). Their totals
    also measure run-to-run reproducibility against C03.
14. **Scope of `notebooks/C04_probe_followup__L4x4.ipynb` revised (coordinator, 2026-11-02, after the C03 and C05 results).**
    - e2b is not run, so the frozen design stays incomplete for e2b. H2 and H4 trends use 3 sizes.
    - The action/arguments split (item 13) is added at S-find: L0, L1, L2, G-json and X-graph are re-scored for 31b, e4b
      and 12b (exploratory). L2 is included so the function hint's gain can be placed in the call header or the
      arguments.
    - No empty-graph control.
    - Final tables and figures come from `pilot_c/analyze_c04.py` (the notebook's last cell). It recomputes the
      pre-registered tables with C04's design cells merged in (`C03C04_*`) and writes the exploratory additions
      (`C04_*`).
