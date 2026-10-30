# Pilot B report: the code graph as an editing interface

Status: CPU work done (steps 1–4). **Step 5 (live GPU check) is prepared but not run: GPU hours used = 0.**
It needs your OK (estimate below). Every number here is *measured* unless marked otherwise, and
is a single deterministic run (no sampling is involved in steps 1–4).

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

Tests (base vs gold vs replay, same local venv, `results/replay_tests.json`): **TBD_TESTS**

Scoping (`results/scoping.json`): **TBD_SCOPING**

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

## Go / no-go
**No-go as the paper's headline method. Conditional go as a cheap component plus two measurement contributions.**
- Symbol-addressed editing exists (CodeStruct). Under your ambition rule, applying it to Gemma is a
  remix. What is new and solid here: (a) the exact graph-naming emulator, with two newly quantified
  graph defects (flattening collisions, the class-reset bug), which matter to anyone who addresses
  code by graph name; (b) the gold-patch expressibility analysis (45% / 57% / ~72%) and the
  payload-cost finding, which motivates scoped edits.
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
