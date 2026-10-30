# How the swegemma harness exposes skills (pilot A, step 1)

Sources: `HARNESS_README.md` (competition data, 2026-10-13), the starter notebook
`ryanholbrook/getting-started-gemma-4-developer-agent`, and the source code of the wheels in
`metric/gemma-4-developer-agent-wheelhouse`: `swegemma 0.2.11`, `adk_submission 0.2.13`,
`adk_eval_core 0.1.0`, `google_adk 1.36.1`.
Status labels: **verified-run** = checked by running the real harness code locally (CPU, scripted
fake model; scripts in `pilot_a/scripts/`). **read** = from reading source/docs only.

## Short answer

Skills are usable, but only half-visible by default. By default the model is told that skills
*exist* and how to load them, but **not which skills exist**. The submission's own system prompt
can fix that, so this is not a show-stopper. It does mean "skill invocation rate" depends
heavily on how the prompt advertises the skills, and we have to report that choice.

## 1. How the model learns a skill exists

- In `agent.yaml`, an `LlmAgent` lists `skills: [skills/<dir>, ...]`. Each dir needs `SKILL.md` with
  YAML frontmatter `name` (kebab-case, ≤64 chars, **must equal the folder name** in practice) and
  `description` (≤1024 chars). The compiler `adk_submission` loads them with ADK's
  `load_skill_from_dir` and wraps them in ADK's `SkillToolset` (read).
- The SkillToolset adds **4 tools** to that agent: `list_skills`, `load_skill`,
  `load_skill_resource` and `run_skill_script` (verified-run).
- It also appends a generic paragraph to the system instruction: "You can use specialized
  'skills'... If a skill seems relevant... you MUST use `load_skill`..." (verified-run; full text in
  the captured prompt from `pilot_a/scripts/inspect_prompt.py`).
- **The `<available_skills>` block with names and descriptions is never added to the prompt.**
  `SkillToolset.process_llm_request` adds it only when the toolset has no `list_skills` tool, and
  `list_skills` is always present in ADK 1.36.1. Without our help, the model sees skill names only
  after it calls `list_skills` (verified-run: zero skill names in the prompt with `--no-index`).
- The harness's own task prompt (`build_agent_prompt`) never mentions skills (read).
- **Our fix (default in all pilot arms):** `build_submission.py` appends a `## Skills` section to
  `prompts/system.md` listing each skill's name and description. With it, all 3 names are in the
  prompt (verified-run). `--no-index` reproduces the plain ADK default.

## 2. What the skill tools do

| Tool | Does | Counts toward `max_tool_calls`? | Notes |
|---|---|---|---|
| `list_skills` | returns the `<available_skills>` XML (names + descriptions) | No | verified-run |
| `load_skill(skill_name)` | returns the SKILL.md body + frontmatter; marks the skill "activated" in session state | No | unknown name → `SKILL_NOT_FOUND` (verified-run) |
| `load_skill_resource(skill_name, file_path)` | returns a file under `references/`, `assets/` or `scripts/` | No | other prefixes → `INVALID_RESOURCE_PATH` (read) |
| `run_skill_script(skill_name, file_path, args?)` | runs a `.py` (or `.sh`) from `scripts/` **inside the agent sandbox** | **Yes** (goes through `check_budget`) | verified-run: 3 `run_command` + 1 script = 4 counted calls |

Every call still costs one LLM turn (`max_turns`) and context tokens, and wall-clock time counts
against `max_time_minutes`. So "free" applies only to the tool-call counter.

`activated` skills can unlock extra tools through the frontmatter key `metadata.adk_additional_tools`.
But adk_submission passes the agent's *already declared* tools as the candidates, so this cannot
hide tools until a skill is loaded (read).

## 3. Where scripts run, and what counts against the budget

- `swegemma` gives the compiler an `AdkSandboxCodeExecutor` bound to **Container A** (the agent's
  sandbox). ADK builds a self-extracting Python wrapper holding all the skill's files, writes it
  as `/workspace/.adk_exec_<id>.py`, runs `python3` on it, then deletes it. The wrapper copies the
  skill files into a temp dir and `chdir`s there before running the script (verified-run).
- Timeout per script = `min(timeout_seconds, remaining session time)` (read).
- **Pitfall 1: paths.** In the `subprocess` sandbox (what the Kaggle notebooks use), `/workspace`
  is rewritten to the real sandbox path only in shell *command strings*, not inside Python files.
  A skill script that hard-codes `/workspace` breaks on Kaggle. Our `check_patch.py` finds the repo
  from the launching shell's `PWD`/`PYTHONPATH` (verified-run).
- **Pitfall 2: patch pollution.** While a script runs, the harness's temp `.adk_exec_*.py` file sits
  in `/workspace`. A script that runs `git add -N .` could stage it into the patch. Our script is
  read-only (verified-run: the final patch contained only the intended file).
- Allowed submission file types: `.yaml .yml .md .txt .py .json .safetensors`. **`.sh` skill
  scripts are rejected by the validator**, so use `.py` (read; our arms pass `validate_directory`).
- Container setup and snapshot extraction are *excluded* from the agent time budget (read, README §7).

## 4. Other facts that matter for this pilot

- Calls made inside the starter's `code_analyzer_agent` (an AgentTool sub-agent) do **not** appear
  in the root trace, but they do count toward `tool_calls_used`. Our metrics therefore report both
  trace-visible calls (`tool_calls`) and the harness counter (`harness_tool_calls`) (read).
- ADK templates `{identifier}` in instructions from session state, so skill text pasted into a
  prompt must not contain `{name}`-style braces. `build_submission.py` and `distill_skills.py`
  guard against this (read).
- The e4b checkpoint is int4 (symmetric, group 32, compressed-tensors) with bf16 activations,
  `model.safetensors` = 11.5 GB (per-layer embeddings and the vision/audio towers are unquantized).
  T4 GPUs have no bf16, so vLLM would fall back to fp16. Whether Gemma 4 is numerically stable in
  fp16 is unknown, and the `probe` phase tests it (read; not run).

## 5. Context compaction removes loaded skills (added in the rethink)

- The scorer configures ADK `EventsCompactionConfig`: `token_threshold=14336`, `event_retention_size=5`,
  `compaction_interval=15`, `overlap_size=2`. This is set in `scripts/inference.py` and the starter
  notebook, not by the submission (read).
- ADK's `LlmEventSummarizer._format_events_for_prompt` only includes `part.text`. **Function calls and
  function responses are dropped from the summariser's input** (read: `google/adk/apps/llm_event_summarizer.py`).
- A skill body returned by `load_skill` is a function response, so after the next compaction it is
  gone, not even summarised. The system instruction (and with it an indexed catalog or inlined
  skills) is never compacted (read).
- The initial task prompt is a user text event, so it is summarised rather than kept verbatim (read).
- How soon compaction fires for e4b is unknown. Estimate: after ~5–10 calls, since `read_file`
  returns up to ~2.5k tokens. The traces record `compaction` events, and `common/trace_parser.py`
  counts them.
