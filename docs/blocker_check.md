# Step 1: can a skill script edit the task repo, and does the edit reach the patch?

**Answer: yes, on both sandbox backends.** It is read from the harness source in the official
wheelhouse (`metric/gemma-4-developer-agent-wheelhouse`: swegemma 0.2.11, adk-submission 0.2.13,
adk-eval-core 0.1.0, google-adk 1.36.1). No live GPU run has confirmed it yet; the smoke run
does that.

## The call chain (file:function)
1. `swegemma/harness/agent_runner.py` (`run_agent_sandbox`, ~l.609) builds
   `AdkSandboxCodeExecutor(sandbox=context.sandbox, budget_check_fn=context.check_budget, ...)`
   and passes it to `compile_submission(..., code_executor=...)`. Skills declared in `agent.yaml`
   (`skills: [skills/<name>]`) become an ADK `SkillToolset` that uses this executor.
2. `google/adk/tools/skill_toolset.py` (`_SkillScriptCodeExecutor._build_wrapper_code`) turns
   `run_skill_script(skill_name, file_path, args)` into one self-contained Python program. The
   program writes all of the skill's `scripts/`, `references/` and `assets/` into a
   `tempfile.TemporaryDirectory()`, `chdir`s there, sets `sys.argv = [script, --k, v, ...]`, and
   runs the script with `runpy.run_path(..., run_name='__main__')`.
3. `adk_eval_core/sandbox/base.py` (`AdkSandboxCodeExecutor.execute_code`) writes that program to
   `/workspace/.adk_exec_<hex>.py`, runs `python3 /workspace/.adk_exec_<hex>.py` **inside the task
   sandbox** (Container A, or the subprocess sandbox on Kaggle), then deletes the temp file.
4. Patch extraction (`submit_patch`, or the automatic fallback) is
   `git add -N . && git diff --binary _swegemma_baseline || git diff --binary HEAD` in `/workspace`.
   Any file a script modified there is in the patch, minus the protected test and config files.

## Consequences for the skill design
| Fact | Consequence |
|---|---|
| The script's cwd is a temp dir, not the repo | It must locate the repo itself. Docker: `/workspace`. Subprocess sandbox: the harness sets `PYTHONPATH=<workspace_dir>`, and the literal `/workspace` inside a Python file is **not** rewritten there, unlike shell commands. `_symlib.find_root()` tries `GRAPH_EDIT_ROOT`, `/workspace`, `PYTHONPATH` entries, `PWD`, cwd, and takes the first that contains `.git`. |
| The code graph JSON lives on the host and is never copied into the sandbox | The skill cannot read the graph. It re-derives symbol spans with `ast` on every call, which is fresher anyway, and reproduces the graph's naming exactly (`common/graphnames.py`), so graph names resolve. |
| Each `run_skill_script` goes through `context.check_budget()` | Each script run costs **1 tool call**, the same as `edit_file`. `load_skill` and `load_skill_resource` do not pass the budget gate. |
| Script stdout/stderr come back as `{"stdout","stderr","status"}` | The scripts print one JSON line (`{"status": "ok"|"error", ...}`). `common/metrics.py` parses it to count failed skill edits. |
| Python in the sandbox: docker image `python:3.13-slim`; on Kaggle subprocess, the host Python | The skill uses the stdlib only. |
| ADK requires the `SKILL.md` `name` to be kebab-case and equal to the directory name | The skill is named `graph-edit`, in `skills/graph-edit/`. |
| Allowed submission extensions: .py .md .yaml .json .safetensors | `__pycache__/*.pyc` must not be shipped. The notebook deletes it. |

## Fallback, if a future harness version blocks writes
`edit_symbol` already computes the full new file text and a unified diff before writing. A
`--dry_run` flag that returns `{old_string, new_string}` for `edit_file` would keep every check
(symbol resolution, ast validation) and leave the write to the built-in tool. It is not needed today.
