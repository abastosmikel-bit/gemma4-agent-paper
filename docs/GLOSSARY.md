# Glossary (plain explanations of the terms used in pilot C's files)

## Measuring information

- **log p, log-likelihood.** How probable the model finds a given piece of text, here a whole action such as
  `read_file(...)`. It is the natural log of the probability, so it is negative; closer to 0 means more expected.
- **nat.** The unit of log p (natural log). A gain of +1 nat makes the action e (≈ 2.7) times more likely; +3 nats ≈ 20×;
  +10 nats ≈ 22,000×.
- **Δ (delta).** The difference in log p between two conditions for the same task, for example Δ(L2 − L0): how much the
  hint raised the correct action's probability. Tables report the median Δ over tasks.
- **Canonical (target) action.** The one correct next action we score:
  - at the find step, `read_file` on the gold function;
  - at the use step, the `edit_file` that makes the gold change.
- **Depth 1 / depth 2.**
  - Depth 1 scores the probability of the canonical action (no sampling).
  - Depth 2 lets the model actually choose its next action (1 sample at find, 2 at use) and classifies what it did.
- **Action / arguments split.** Splits an action's log p into the call header (`<|tool_call>call:read_file`, "call this
  tool now") and the arguments (file path, line numbers, edit text).
- **direct / spliced.** How the scored tokens are lined up with the chat template.
  - The 31b and 12b templates insert an empty "thinking" block after a user turn; "spliced" scoring accounts for it.
  - Every scored cell records which way was used.

## The two moments (states)

- **S-find (find).** The agent has the task and has not read code yet. The correct action is to read the gold function.
- **S-use (use).** The agent has just read the gold function. The correct action is the right edit.

## The ladder and the hints

| Code | What the agent is given (added to the problem statement) |
|---|---|
| L0 | nothing extra |
| L1 | the gold file |
| L2 | the gold file and function (name and line) |
| L3 | L2 + the reproduction test (the test code that checks the fix) |
| L4 | L3 + the change described in 1–3 sentences of plain words (written by 31b from the gold diff) |
| L5 | L4 + the exact diff |
| T | only the reproduction test |
| W | only the change in words |
| G-json, G-edges, G-adj | only a graph-tool output around the gold function, as JSON, as an edge list, or as an adjacency list |
| G-null | the same kind of graph, but for another task's code in an unrelated file (control, C04) |

L1–L5 are cumulative; T, W and the G-conditions are single hints.

**Wrong-hint controls (X-\*)**, each matched in length to its correct counterpart:
- X-file: a wrong file;
- X-func: the right file with a wrong function;
- X-graph: a graph focused on a wrong function in the right file;
- X-test: L2 + another task's test;
- X-words: L3 + another task's words.

**Hint conditions in full agent runs** (C01, C05, C06):
- O0: no hint;
- O-all: file + function + names of the required tests.

## Outcomes in sampled actions and runs

- **hit_file / hit_func.** At the find step: the sampled action reads the gold file / overlaps the gold function.
- **on_target / exact / applies.** At the use step:
  - on_target: the edit changes lines near the gold change;
  - exact: it equals the gold change;
  - applies: the harness can apply it.
- **followed_wrong.** The action went where a wrong hint (or the unrelated graph) pointed.
- **edit rate.** The share of sampled first actions that edit the gold file.
- **solves.** The sampled edit, applied alone, passes the required tests (checked in C03v).
- **resolved.** A full run's patch is non-empty and passes the required tests (the scorer's rule).
- **fail→pass flip.** A task unresolved without the hint and resolved with it.
- **discordant.** A task that resolves in exactly one of the two conditions.
- **Information threshold.** The lowest ladder rung at which a sampled edit is right (exact; after C03v, exact or
  solves).

## Hypotheses (fixed before the data; `docs/PLAN.md` §6)

- **H1.** Location hints help the find step much more than the use step. **Supported** (all three sizes).
- **H2.** The gain from words grows with model size, and the gain from the exact diff shrinks. **Not supported.**
- **H3.**
  - Graph encodings matter for small models but not for 31b;
  - every graph gives less than the text hint naming the function.
  - **Partly supported:** graphs < text everywhere; small encoding effect for e4b; for 31b the differences exceed the
    margin.
- **H4.** Wrong hints hurt, and hurt small models more. **Only X-file hurts;** no size trend.
- **H5.** e4b edits on target in ≥ 50% of tasks with the diff but ≤ 20% with only the location. **Not supported:** 63%
  already at L2.
- **H6.** The probe's per-task number predicts which tasks the hint rescues in full 12b runs, with AUC ≥ 0.65. **Not
  supported:** C05 0.43, C06 0.27.

## Statistics

- **Median and 95% bootstrap CI.** The middle value over tasks, and the range it falls in when the tasks are resampled
  10,000 times.
- **Wilcoxon signed-rank test.** Checks whether paired differences (same task, two conditions) are centred away from 0.
- **McNemar (exact) test.** For yes/no outcomes on the same tasks under two conditions; it only uses the tasks that
  changed.
- **Holm correction.** Adjusts p-values when several tests are run together.
- **Page's L test.** Checks whether a value rises (or falls) in a predicted order across the model sizes.
- **Cochran's Q.** Checks whether a yes/no outcome differs across several related conditions (L0–L5).
- **Fisher's exact test.** Compares two proportions in a small 2×2 table.
- **AUC.** The chance that a randomly chosen positive task (rescued by the hint) has a higher predictor value than a
  randomly chosen negative one. 0.5 = no better than chance; 1 = perfect.

## The agent and its context

- **Context window.** The most text (in tokens) the model can take in one request: 32,768 here (vLLM `max_model_len`).
- **max_output_tokens.** How many tokens the agent reserves for the reply. vLLM refuses a request if prompt + reserved
  output > 32,768.
  - With the starter's 16,384, prompts must stay under 16,384 (the **effective prompt limit**).
  - With 8,192, the limit is 24,576.
- **Crash (context-window crash).** A run that ends because a request was refused for length
  (`ContextWindowExceededError`).
- **Compaction.** ADK's way to shrink a long history. When the previous request's prompt was ≥ 14,336 tokens
  (`token_threshold`), it replaces everything except the last 5 events (`event_retention_size`) with an LLM-written
  summary.
- **Summary.** The text that replaces compacted events.
  - It keeps only text, not tool calls or outputs.
  - ADK shows it to the model as a user message, "For context: [model] said: …".
- **Statement retention.** How much of the task statement a summary keeps, as the share of its 5-word phrases or of its
  distinct words.
- **Sub-agent (`AgentTool`, `code_analyzer`).** A second agent the main agent can call as a tool. It runs in its own
  conversation, which is never compacted.
- **Failed edit.** An `edit_file` call the tool rejects, usually because the text to replace (`old_string`) is not in the
  file.

## Tasks and the benchmark

- **Gold patch.** The real fix from the repository's history.
- **No-patch baseline.** The same tests with no change at all.
- **Valid task.** The gold patch passes and no patch fails. 71 of 129 dev tasks on Kaggle.
- **src layout.** A repo that keeps its package under `src/`. In the sandbox the tests then import the copy installed on
  the host instead of the repo's code, so no patch can change the result.
- **Host site-packages.** Libraries installed on the machine running the harness. The sandbox can see them.

## Process

- **Pre-registered / frozen plan.** Hypotheses and analyses written and committed before the data
  (`docs/PLAN.md`, `docs/PLAN_C05_validation.md`, `docs/PLAN_C06_validation_fix.md`).
  - **Deviation:** a later change, logged with date and reason.
  - **Exploratory:** an analysis not in the plan.
- **L4x4 hour.** One hour on Kaggle's 4×L4 GPU machine; counts double against the weekly quota.
- **Dry run.** A run of a notebook on a CPU machine against a fake model server, to check the code before spending GPU time.
- **Watchdog.** A thread that kills a frozen model server so a run can't hang until the time limit.
