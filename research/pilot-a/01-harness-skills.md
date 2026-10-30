# Pilot A, step 1: how the harness exposes skills

Source: competition data (`HARNESS_README.md`, `sample_submission/`), starter notebook
`ryanholbrook/getting-started-gemma-4-developer-agent`, and the wheels in dataset
`metric/gemma-4-developer-agent-wheelhouse` (`adk_submission-0.2.13`, `swegemma-0.2.11`,
`adk_eval_core-0.1.0`, `google_adk-1.36.1`). All findings below are **read from source**, not yet
observed in a run. File references are to the unpacked wheels (kept out of git under `vendor/`).

## Verdict
Skills are **reachable but hidden by default**. With an unmodified ADK `SkillToolset`, the model
never sees the names or descriptions of our skills in its prompt. It only sees a generic paragraph
saying skills exist, plus four tool declarations. To find out which skills exist it must first call
`list_skills`. A small model may simply never do that.

The fix is cheap and legitimate: the agent's own `instruction` (which we write) can carry a short
skill index (name + when to use it). With that, skills are visible enough to test. So the pilot
continues, with one change to the design: **visibility becomes an explicit factor** (see the
"Consequences" section).

## 1. How the model learns a skill exists
Path: `agent.yaml` → `skills: [skills/<name>]` → `adk_submission/resolvers/tools.py::resolve_skills`
→ `load_skill_from_dir` → one `google.adk.tools.skill_toolset.SkillToolset` per agent, appended
to that agent's tools (`adk_submission/builders/llm.py:67`).

On every LLM call ADK runs `SkillToolset.process_llm_request` (`base_llm_flow.py:451`). It
appends to the system instruction:
- always: `_DEFAULT_SKILL_SYSTEM_INSTRUCTION`, a ~250-word generic text ("You can use specialized
  'skills'... If a skill seems relevant... you MUST use `load_skill`...");
- the `<available_skills>` XML with names and descriptions, **only if the toolset has no
  `list_skills` tool**. In ADK 1.36.1 `ListSkillsTool` is always added (`skill_toolset.py`,
  `SkillToolset.__init__`), so **the XML index is never injected**.

`adk_submission` passes no custom toolset class (`compiler.py:150`, `skill_toolset_cls=SkillToolset`)
and the swegemma prompt builder (`build_agent_prompt`) never mentions skills.

What the model actually sees: the generic paragraph, and tool declarations for `list_skills`,
`load_skill(skill_name)`, `load_skill_resource(skill_name, file_path)` and
`run_skill_script(skill_name, file_path, args?, short_options?, positional_args?)`.
Skill names are visible only after a `list_skills` call or if our own instruction names them.

## 2. What each tool does
| Tool | Returns | Counts toward `tool_calls` budget? |
|---|---|---|
| `list_skills()` | XML list of every skill's name + description | No |
| `load_skill(skill_name)` | The SKILL.md body + frontmatter. Also records the skill as "activated" in session state (`_adk_activated_skill_<agent>`) | No |
| `load_skill_resource(skill_name, file_path)` | Text of `references/*`, `assets/*` or `scripts/*` inside the skill directory | No |
| `run_skill_script(skill_name, file_path, ...)` | stdout/stderr of a skill script | **Yes**: the executor calls `context.check_budget()`, which increments `tool_calls_used` (`adk_eval_core/sandbox/base.py:176`, `swegemma/context.py:468`) |

Notes:
- Activation also unlocks any tools named in the skill's frontmatter
  `metadata.adk_additional_tools`, chosen from the agent's own declared tools
  (`_resolve_additional_tools_from_state`). This is a real **gating** mechanism: a tool can stay
  hidden until a skill is loaded. Not documented in the README.
- swegemma coerces `["name"]` → `"name"` for `skill_name`/`file_path` (`agent_runner.py:97`), a fix
  for a malformed-argument pattern Gemma apparently produces.
- Skill tool calls are not budget-gated, but each still costs an LLM turn, wall-clock time and
  context tokens. A loaded SKILL.md stays in the history until ADK's compaction removes it
  (compaction runs at 14,336 tokens and keeps the last 5 events).

## 3. Where scripts run, and what counts against the time budget
- Executor: `AdkSandboxCodeExecutor` (`swegemma/harness/agent_runner.py:609`), bound to the
  task's **Container A** sandbox (Docker in the README; `sandbox='subprocess'` in the Kaggle starter
  notebook).
- Mechanism: ADK builds a self-extracting Python wrapper holding all of the skill's
  references/assets/scripts. The wrapper is written to `/workspace/.adk_exec_<id>.py`, run with
  `python3`, then deleted in a `finally`. The script runs inside a `tempfile.TemporaryDirectory()`.
  Its cwd is **not** `/workspace`, so it must use absolute paths to reach the repo. It has the
  same offline environment and repo packages as `run_command`.
- Allowed types: ADK accepts `.py/.sh/.bash`, but the submission validator only allows `.py`.
  **Skill scripts must be Python.**
- Timeout: `min(command_timeout_seconds [300 s], remaining session time)`.
- Budget: the session clock (`agent_start_time`, started after container setup) runs during every
  skill call. `run_skill_script` also uses one of the `tool_calls` slots. If the budget is
  exhausted, the script returns the budget error in its stderr.
- Risk: if a script crashes the sandbox before the `finally` runs, the `.adk_exec_*.py` file could
  end up in `git diff`. Unlikely, but our scripts should avoid writing into `/workspace` unless that
  is their purpose.

## 4. Submission constraints that matter for skills
- Skill directory name must equal the frontmatter `name` (kebab-case or snake_case, lowercase).
- Allowed files: `.md`, `.txt`, `.py`, `.yaml`, `.json`. ≤ 50 MiB per skill, ≤ 1,000 skills.
- Each SKILL.md counts toward the instruction-length limits (1M chars per agent). Not binding.
- `skills:` is per agent. Sub-agents need their own list.

## 5. Consequences for Pilot A design
1. **Invocation rate is the first-order metric.** A skill the model never opens cannot help. We
   log `list_skills` / `load_skill` / `load_skill_resource` / `run_skill_script` calls per task from
   the ATIF traces.
2. **Visibility factor.** Two exposure modes:
   - *V0 (default ADK)*: skills declared, no mention in our instruction. This is the harness as shipped.
   - *V1 (index)*: plus a ≤ 80-word "Skills index" in our instruction (name + trigger condition).
   The main comparison uses V1. V0 on one arm measures how much invocation depends on the index.
3. **Prompt-length confound.** Any skill gain could just be "longer prompt with good advice". The
   control is an **inline arm**: the same skill bodies pasted into the system instruction, with no
   tools. "Skills > inline" means on-demand loading itself matters. "Skills ≈ inline > baseline"
   means the content matters and the skill mechanism is only packaging. The pilot does not have the
   budget for this arm. The main experiment must include it, or the paper cannot claim anything
   about skills as a mechanism.
4. **Novel lever (to evaluate later):** `adk_additional_tools` gating lets a skill *unlock tools*.
   Example: `edit_file` stays hidden until the agent loads a "reproduce first" skill, so procedure
   is enforced rather than suggested. That is closer to "changing behaviour like a LoRA" than advice
   text is. Logged in `ideas.md` (as a candidate idea, not a result).

## Open items (not yet verified)
- Whether e4b calls `list_skills` at all under V0 (needs a run).
- Whether `sandbox.run_command` truncates script stdout to 5,000 chars as it does for `run_command`.
- Exact token cost of the generic skill paragraph + 4 declarations for e4b (measure from traces).
