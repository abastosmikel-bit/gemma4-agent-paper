# Pilot B report: the code graph as an editing interface

Status: CPU work done (steps 1–4). **GPU hours used = 0.** The step-5 notebook is built but, after
the **[Rethink](#rethink-what-question-do-these-numbers-belong-to)** below, I no longer recommend running it as designed.
Every number here is *measured* unless marked otherwise, and is a single deterministic run (no
sampling is involved in steps 1–4).

## What I did, in plain terms
An LLM agent edits code with `edit_file(old_string, new_string)`: it must reproduce a piece of the
file exactly, and the tool swaps it. Small models often get that text slightly wrong, so the edit
fails ("no match") or hits the wrong place ("multiple matches"). The idea tested here is to
address the edit by *name* instead, as in "replace `fastapi.routing.APIRoute.__init__`", using the
dotted names the competition's code graph already prints.

1. **Blocker check.** Can a skill script change files, and do the changes reach the patch?
2. **Graph to source.** Can every graph node be pinned to an exact place in the file?
3. **Expressibility.** How many real fixes (the 129 gold patches) could be written as symbol edits?
4. **Built the skill** `graph-edit` (show / edit / insert by symbol), replayed every expressible
   gold patch through it, and ran the tests.
5. **Live check notebook** for Gemma E4B with vs without the skill (ready, not run).

## 1. Blocker check: passed (from harness source; details in `docs/blocker_check.md`)
- `run_skill_script` runs **inside the task sandbox**, as `python3 /workspace/.adk_exec_*.py`
  (`AdkSandboxCodeExecutor`). Files it writes in `/workspace` land in `git diff`, so they reach the
  submitted patch. Each call costs one tool call, the same as `edit_file`.
- Two gotchas, both handled. (a) The script runs from a temp dir, and on Kaggle's subprocess
  sandbox the literal path `/workspace` does not exist, so the skill finds the repo via
  `PYTHONPATH`. (b) **The graph file is not available inside the sandbox**, so the skill
  recomputes symbol locations with Python's `ast` module on every call (always fresh after earlier
  edits) and reproduces the graph's naming so graph names resolve.
- Verified offline through the **real** harness code (`pilot_b/tests/adk_integration.py`):
  `validate_directory` and `compile_submission` accept the submission (a `SkillToolset` is
  attached), and the real ADK script wrapper plus `AdkSandboxCodeExecutor` ran `show_symbol` and
  `edit_symbol` on a fastapi checkout; the edit appeared in `git diff`. *Not yet verified on
  Kaggle's own subprocess sandbox: the smoke run does that.*

## 2. Graph node → source span (127 graphs, every node; `results/graph_spans.json`)
**Surprise #1: the graph's naming rule is fully reproducible.** The generator is a plain AST
visitor with one "current class" variable. I re-implemented it (`common/graphnames.py`) and it
reproduces **100% of node names** on all four repos. That is what makes graph-name addressing possible.

| Library code (fastapi/, rich/, requests/, httpx/), summed over 127 graphs | Value |
|---|---|
| Function nodes whose text equals exactly one AST definition, character for character | **61,665 / 61,665 (100%)** |
| ... whose text a plain string search finds exactly once in the file | 98.1% (1.9% are ambiguous duplicates) |
| Class nodes: text is a generated skeleton (bodies → `...`, attributes dropped), not source | 93.6% not verbatim; located via AST instead |
| Nodes that could not be located at all | 0 in library code; 998 (0.27%) in `docs_src/`, where several tutorial files share a bare module name |

What the graph leaves out, as a share of all library `def`/`class` definitions (82,937):

| Gap (known ones quantified, plus two not previously reported) | Library | Tests/docs |
|---|---|---|
| `async def` has no node (known "async gap") | 3.4% | 18.5% |
| Nested function renamed as if module-level, which can collide with a real method (*new*) | 4.0% | 4.3% |
| Same-named definitions collapsed into one node (property setters, overloads, flattened names) | 3.6% | 2.8% |
| **Generator bug** (*new*): after a class nested in a class or method ends, the outer class's remaining methods are named as module functions | 0.15% | 1.6% |
| Edge types other than `calls` (known "calls-only") | 0 of 452,588 edges | |
| Module-level code (imports, constants) and class attributes | Not nodes by design: 78k import lines and 123k class-body statement lines in library code | |

Concrete collision: in fastapi, `FastAPI.openapi` (the method) and an `openapi` function nested
inside `FastAPI.setup` share the graph name `fastapi.applications.FastAPI.openapi`. A tool that
trusted graph names blindly would edit the wrong one. My resolver prefers the true nested name,
then the graph name, and accepts `name@<line>` to pick between same-named definitions.

## 3. Expressibility of the 129 gold patches (`results/expressibility.json`)
Each changed region of each gold patch was attributed to the innermost definition containing it on
both sides of the diff, or to module level.

| Tool capability (cumulative) | Tasks fully expressible |
|---|---|
| L0: replace existing graph **function** nodes only | **58 / 129 (45%)** |
| L1: + any def by AST name (async, nested) | 62 (48%) |
| L2: + replace whole classes (attributes, new methods) | 69 (53%) |
| L3: + insert new functions/classes | **74 (57%)** |
| L3 + an "add import" operation (estimate from the breakdown below, not built) | 93 (72%) |

By repo at L3: requests 10/13, rich 32/48, fastapi 31/67. fastapi is lowest because it often adds
new files and module-level code. The 55 inexpressible tasks need: imports only (19),
module-level statements (12), imports and statements (13), new source files (11).
No gold patch touches non-Python files.

**Surprise #2: the cost of whole-symbol replacement.** Re-emitting the entire function to change
one line sends a **median 6.7× (p90 32×, max 199×)** more lines than the gold diff changes. For a
small model with output-token limits, that risks exactly the truncated-call failures the harness
nudges about. I therefore added a **symbol-scoped find/replace** mode: `edit_symbol(symbol,
old_string, new_string)` matches only inside the named definition, tolerates indentation drift,
and re-checks syntax.

## 4. The skill and the offline replay
`pilot_b/skill/graph-edit/` (stdlib only):
- `show_symbol` returns the source of `pkg.mod.Class.method`, `file.py:Class.method` or a unique
  short name, or a symbol outline for a file. When a name is wrong it suggests close matches.
- `edit_symbol` replaces a whole definition, keeping its decorators if omitted, or does a scoped
  find/replace. It **refuses to write** if the result does not compile, if the snippet is not
  exactly one def/class, or if the name or kind changes without `allow_rename`. It returns a short diff.
- `insert_symbol` adds a new definition `after`, `before` or `into` a symbol or file.

Replay of every expressible gold patch through the skill code (114 files):
**112 byte-identical to gold, 1 AST-identical, 1 same definitions in a different top-level order,
0 failures** (after fixing 4 bugs this replay found: fences stripped inside docstrings, insertion
anchors, same-name ranking, graph-name collisions).

Tests (`results/replay_tests.json`). For all 74 expressible tasks I ran pytest on the test files of
`test_patch` in three trees, base, gold and replay, in one local PyPI venv per repo:
| | Tasks |
|---|---|
| Replay pass/fail/error counts identical to gold | **74 / 74** |
| Informative (base fails, gold passes) | 33 (rich 22, requests 6, fastapi 5) |
| ... of which replay passes | **33 / 33** |
| Gold changes test counts vs base (wider definition) | 45 |
| Local env cannot collect the tests (old fastapi commits vs new starlette/pydantic) | 18 fastapi; counts match but carry no information |
| Timed out (180 s) identically in all three trees | 2 (rich) |
"Replay" here means **the skill code reproduces the gold patch**, which is an upper bound. It says
nothing yet about whether a *model* will use the skill well. That is step 5.

**Scoping (`results/scoping.json`): the strongest offline result.** For each of 683 gold hunks
inside a definition, I took the *minimal* `old_string` a model would write: the changed lines, or
for a pure insertion the line before it. 71% of these are single lines.
| Where the match is searched | Ambiguous (more than one match, so `edit_file` would refuse) |
|---|---|
| Whole file (today's `edit_file`) | **28.1%** (192 / 683) |
| Only inside the named symbol (`edit_symbol` scoped mode) | **9.1%** (62 / 683) |
So naming the symbol resolves 130 of the 192 ambiguous edits (68%) at no extra output tokens.
This is a mechanism-level prediction for the live check: fewer "multiple matches" failures.
Caveat: a model may add context lines on its own. The live run measures what actually happens.

## 5. Live check: ready, not run (needs your OK)
`notebooks/pilot_b_live.ipynb` (generated by `pilot_b/build_notebook.py`, skill embedded):
- E4B, both conditions start from the official `sample_submission` with identical budgets
  (50 tool calls, 10 min, seed 1234); the only difference is the skill plus 8 prompt lines.
- 15 fixed tasks, stratified: 10 expressible, 5 not; fastapi 7, rich 6, requests 2. Smoke = 3 tasks.
- Writes one JSON with the shared metrics (resolved, wall time, tool calls, duplicate calls,
  malformed share, failed edits, skill usage) and per-task error types for `edit_file` vs skill edits.
- Estimate (*estimated, not measured*): smoke ≈ 0.4–0.6 L4x4 h. Full 15×2 ≈ 1.0–1.4 L4x4 h. A
  hard stop at 1.9 h of notebook wall time protects the 2 h cap. That is 2–4 quota hours if L4x4
  counts double.
- Caveat: 15 tasks cannot show a difference in *resolved* rate (E4B will resolve few). The
  readable signals are failed-edit share, malformed share and skill uptake.

## Closest prior work
| Work | What it does | Gap left for us |
|---|---|---|
| **CodeStruct** (Kim et al., ACL 2026, arXiv 2604.05407) | `readCode`/`editCode` on named AST entities, syntax-validated edits, SWE-bench Verified with 6 LLMs (smallest Qwen3-8B). +1.2–5.0 Pass@1; GPT-5-nano empty patches 46.6%→7.2% | **Same core idea, so symbol-addressed editing is NOT novel.** Not graph-named, no Gemma, no expressibility analysis of gold patches. Their small-model error counts barely drop (per the subagent's reading of the HTML version; I verified only the abstract) |
| Serena (oraios, GitHub) | LSP-backed `replace_symbol_body`, `insert_after_symbol`, ... | No paper, no small-model measurement |
| SWE-agent ACI (Yang et al. 2024) | Line-range `edit` plus a linter guard that reverts bad edits; no-lint ablation −3.0 pts | Line addressing. Precedent for our reject-before-write |
| Aider edit formats; Diff-XYZ (2025); "To Diff or Not to Diff" (2026) | Edit-format comparisons; search/replace is weaker for small models | Not symbol-addressed, not agentic |
| AutoCodeRover, Moatless, Agentless | AST search / span context; edits stay string-based | Retrieval, not edit addressing |
| Competition: host's pinned "Note on Code Graphs for Async Functions"; paper-track threads incl. "27 fastapi tasks cannot pass (missing inline_snapshot/dirty_equals)" and a pre-registration on "anchor distance and small-agent failure" | Async gap acknowledged by the host | No public work found on graph-addressed *editing*. Kaggle pages did not render for my tools (titles from search snippets only); check the pre-registration thread yourself, as it may overlap |

## Go / no-go (first pass; superseded by the Rethink below)
**No-go as the paper's headline method. Conditional go as a cheap component plus two measurement contributions.**
- Symbol-addressed editing exists (CodeStruct). Under your ambition rule, applying it to Gemma is a
  remix. What is new and solid here: (a) the exact graph-naming emulator, with two newly quantified
  graph defects (flattening collisions, the class-reset bug), which matter to anyone who addresses
  code by graph name; (b) the gold-patch expressibility analysis (45% / 57% / ~72%), the
  payload-cost finding, and the scoping result (minimal edit anchors ambiguous 28% file-wide vs 9%
  inside the symbol). Together these argue that the right interface for small models is
  *symbol-scoped find/replace*, not whole-symbol rewriting. CodeStruct, per its abstract, edits whole AST entities.
- A bolder mechanism the full version could test, which CodeStruct cannot do because it has no
  graph (*hypothesis*): **graph-checked edits**. After `edit_symbol` changes a signature, use the
  call graph to find every caller and statically check arity and keywords, returning the call
  sites that would break *before* the agent runs tests. This is a verification signal tied to the graph.
- Decision rule for after the 15-task check: go on only if baseline E4B shows a failed-plus-malformed
  edit share of at least about 20% **and** the skill visibly lowers it with uptake of at least 50% of
  tasks. Otherwise fold (a) and (b) into another pilot's paper as a resource section.

**Full version cost (estimate):** 4–6 working days. Live runs: E4B and 12B × 2 conditions × ~60
tasks × 2 seeds ≈ 8–12 L4x4 hours (16–24 quota hours if doubled), i.e. most of one week's budget,
plus ~1 day of CPU work for the graph-checked-edit verifier.

## Rethink: what question do these numbers belong to?

### The higher-level question
Every edit has two parts: a **reference** (where to change) and a **payload** (what to put
there). The model writes both; a deterministic tool must turn the reference back into a location.
`edit_file`'s anchor text, SWE-agent's line ranges, CodeStruct's AST paths, our graph names: these
are all **addressing schemes**. They are different ways for a lossy sender (a small model) to
describe a place in code to an exact receiver (the tool).

So the underlying question is not "graph or no graph". It is:

> **How should a small model refer to the code it changes, and what should the tool do when the
> reference is imperfect?** What share of small-model edit failures are *reference* failures (no
> match, several matches, wrong place, outdated location) rather than *content* failures (bad
> code)? Which scheme gives the fewest reference failures per output token?

A good reference has four properties, and they pull against each other:
1. **Unique**: it denotes one place.
2. **Stable**: it stays valid while earlier edits change the file.
3. **Cheap**: few tokens to produce, little exact copying.
4. **Total**: it can point at every place a fix touches.

The tool's side is a *resolver*. When a reference is imperfect, it can fail, guess, or ask back.
That choice is part of the interface too.

**On your framing.** "The graph as an editing interface" makes the graph the subject, and my
results say it should not be:
- The graph is not available inside the sandbox, where edits happen.
- It is a snapshot of the code before the fix, so it goes stale after the first edit.
- Its names fail at 15% of real edit sites (below).

The graph's legitimate role is narrower. It is a *namespace the model already learned while
navigating*, and the defects measure exactly where that continuity breaks. The right lens is
**edit addressing as reference resolution between model and tool**. The graph is one namespace
among four. Your original metric, "malformed or lost edits", also needs splitting into: malformed
call, unresolved reference, ambiguous reference, wrong-site application, stale reference, and bad
content. They have different causes and different fixes.

### What the CPU results already say
Gold patches only, so this describes the *edits a fix needs*, not what a model writes. Numbers are
hunk-weighted (1,000 hunks in 129 tasks; `results/addressing.json`, `scoping.json`, `expressibility.json`).

| Scheme | Unique | Stable | Cheap | Total |
|---|---|---|---|---|
| Line numbers (SWE-agent) | yes | **no: 67.6% of hunks follow an earlier hunk in the same file that changed its length (76/128 tasks)**, so line numbers computed up front go stale | yes | yes |
| Minimal text anchor (`edit_file`) | **no: 27.7% ambiguous**; ~2 extra lines of context fix most; 2.4% stay ambiguous even with 10 | yes | copy-heavy | yes |
| Symbol name + whole rewrite (CodeStruct-like) | mostly | yes | **no: median 6.7× the needed lines** | **no: 27.8% of hunks are outside any def/class**; 43% of tasks need such an edit |
| Graph name | **no at 14.8% of in-symbol edit sites**: 14.0% are `async def` (no node), 0.8% share a name | **no** after the first edit (snapshot) | yes | same as symbol |
| Symbol + scoped anchor (this pilot) | 90.9% at minimal anchor | yes | yes | same as symbol |

Four conclusions:
1. **No single scheme dominates.** Each fails one property badly. The best interface is a
   *composite*: name a coarse scope, then anchor finely inside it, with module-level fallback.
2. **The async gap is concentrated where fixes happen.** `async def` is 3.4% of library
   definitions but 14.0% of edited ones. That is a new, decision-relevant fact beyond the existing
   graph audits, which count nodes rather than edit sites.
3. **The receiver side is solved.** The replay passes 74/74 with test counts identical to gold.
   The unknown is entirely on the sender side: how often a *model* produces bad references, and
   which kind.
4. None of this has touched a model yet. If small-model failures turn out to be mostly *content*,
   every addressing interface, CodeStruct's included, is optimising the wrong thing. That would be
   a useful negative result in its own right.

### Reframed directions
**A. Edit-reference probe: a benchmark that separates reference failures from content failures.**
- *How:* from the 1,000 gold hunks, build single-turn prompts. Show the current code region and
  the exact intended change, then ask the model to express it in scheme S: anchor, line range,
  symbol rewrite, symbol + anchor, or a resolver with feedback. Reasoning is removed, so every
  failure is an interface failure, scored automatically per type and per output token. This is a
  controlled experiment, not an agent run.
- *Claim it could support:* "For Gemma E4B/12B, X% of edit-call failures are reference failures,
  and scheme S cuts them by Y% at Z tokens." Or the negative: "reference failures are rare, so
  edit-interface work does not pay off at this scale."
- *New vs CodeStruct:* CodeStruct reports end-to-end Pass@1 for one structured scheme. This
  decomposes failures by cause across the whole scheme space, with gold ground truth per edit.
- *New vs graph audits and Diff-XYZ:* real-repo ambiguity and staleness, agent tool formats, edit
  sites rather than node counts.
- *Prize fit:* Best New Resource; it generalises to any agent and model.
- *Weakness:* on its own it is a measurement. The ambition rule wants a method, so pair it with B.
- *Cost (estimated):* ~1 day CPU to build. 4,000–8,000 short single-turn generations ≈
  **0.3–0.6 L4x4 h** for E4B, plus ~0.4 h for 12B.

**B. Reference-tolerant edits: a resolver that uses the agent's own focus and asks back cheaply (the method candidate).**
- *How:* the edit tool stops treating an imperfect reference as an error. It resolves in steps:
  1. Restrict to the agent's **focus scope**: symbols it recently viewed or edited, tracked by the
     skill in a sandbox state file, so the model never has to name anything.
  2. Allow indentation-tolerant matching.
  3. If still ambiguous, return numbered candidates labelled by enclosing symbol, so the model
     answers with an index (a few tokens) instead of re-emitting a longer anchor.
  4. Never apply silently outside the focus scope.
- *Claim it could support:* "Implicit, trajectory-derived scoping removes most reference failures
  for small models at near-zero extra output tokens, without wrong-site edits."
- *CPU evidence so far:* explicit symbol scope resolves 68% of ambiguous minimal anchors. That is
  the upper bound for focus scoping when focus equals the true symbol.
- *New vs CodeStruct:* no explicit naming, a stateful resolver, a disambiguation dialogue, and it
  works with ordinary text anchors. That gives totality, including module-level code.
- *New vs SWE-agent:* its guard reverts; this one repairs or asks.
- *Main risk:* wrong focus leads to wrong-site edits. Precision must be measured, and A's probe can measure it.
- *Cost:* ~1–2 days CPU (most pieces exist: scoped matching, AST index, skill plumbing). Live
  pilot 15–30 tasks × 2 conditions ≈ **1.5–2.5 L4x4 h**; full ≈ 8–12 L4x4 h.

**C. Live index over precomputed graph: addresses and consequences from the same edit-time index.**
- *How:* the precomputed graph is a pre-edit snapshot that never enters the sandbox, so anything
  done at edit time should use a live AST index (which the skill already builds). Use it for two
  jobs: (i) addresses that are always valid, and (ii) **consequence checks** after an edit. Which
  references to the changed symbol are now inconsistent: callers with the wrong arity or keywords,
  overrides, imports, `__all__`? This is my earlier call-graph impact idea, recast. It does not
  need the competition graph at all.
- *Claim it could support:* "Many incomplete fixes are multi-site; an edit-time consequence check
  catches them before tests."
- *Status:* unmeasured. The first CPU step is to count how many gold patches change a signature
  and also touch its call sites (half a day).
- *New vs CodeStruct and the audits:* neither checks consequences. The audits describe the graph;
  this replaces it at edit time.
- *Cost:* ~2 days CPU; live pilot ≈ 1.5–2 L4x4 h. Only worth it if the multi-site count is high (say >15% of tasks).

### Recommendation
- **A + B as one study.** A is the measurement that decides whether the problem is real for small
  Gemma models; B is the method that addresses it. Together they answer the higher-level question
  rather than one point in it, and they fit the paper track's generality criterion: the claim is
  about addressing for any small agent, not about Gemma or this graph.
- C is a sub-feature, pending a half-day CPU count.
- Keep everything built so far: the skill becomes B's resolver, the replay harness becomes A's
  ground truth, and the graph emulator and defects become a short "where graph names mislead" result.
- **Check first** the paper-track pre-registration thread "anchor distance and small-agent
  failure". Its title suggests overlap with A. I could not read it (Kaggle did not render).
- **The 3-task smoke as designed (with vs without skill, agentic) no longer makes sense.** It tests
  the old framing, and 3 agentic tasks cannot measure failure rates. Two things still need GPU
  confirmation, and they should share one cheap Kaggle session (≈0.5–0.7 L4x4 h *estimated*):
  1. Run A's probe on E4B. This is the decisive cheap experiment.
  2. Run a **baseline-only** agentic run on ~5 tasks, plus 1 task with the skill. The baseline
     run records the *natural* rate and type of E4B's `edit_file` failures; the extra task confirms
     the skill works in Kaggle's subprocess sandbox.
- Both need ~1 day of CPU work first (probe builder, scorer, notebook update). I have not started
  it, per your instruction to stop here.

## Surprises, collected
1. The graph naming is an exact, simple, buggy visitor, fully reproducible.
2. 100% of library function nodes map to exact spans, but graph names are not unique addresses.
3. Whole-symbol replacement is expensive (median 6.7× the gold diff), so scoped edits are the practical form.
4. All 129 gold patches lack a trailing newline (`git apply` reports "corrupt patch" unless one is added).
5. The 129 base commits are public upstream, so the CPU analyses need no 200 MB snapshots.
6. Local test environments drift from the official sandbox (starlette 1.x deprecates `httpx`;
   fastapi's `filterwarnings=error` turns that into collection errors). Comparisons are paired for that reason.

## Environment and logistics
- Python 3.13, docker present (unused), kaggle CLI (credentials injected by the proxy; no
  `KAGGLE_API_TOKEN`), 31 GB free disk, 4 CPUs, no GPU.
- Branch: **`pilot/b-graph-edit`** (orphan). The environment's assigned branch was
  `claude/youthful-turing-n71akn`; a force-push replacing it with an orphan was blocked as
  destructive, so I pushed the orphan to the name you asked for and left the assigned branch untouched.
- Downloaded: `tasks.jsonl`, `HARNESS_README.md`, sample submission, docker files, 127 graphs,
  2 snapshots (for the upstream equality check), harness wheels. Nothing from them is in git.
