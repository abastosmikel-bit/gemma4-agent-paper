# common/: shared code for all pilots

No pilot-specific logic. Depends only on the standard library (the test also uses `adk_eval_core`).

| File | What |
|---|---|
| `tasks.py` | read `tasks.jsonl`, deterministic per-repo samples (`sample_ids(tasks, repo, n, seed)`) |
| `trace_parser.py` | swegemma ATIF trace file → ordered `ToolEvent`s (name, args, parsed response) |
| `metrics.py` | the shared per-task metrics, arm aggregates, paired statistics |

## Shared metrics (one row per task × seed)

| Metric | Definition |
|---|---|
| `resolved` | harness verdict: target tests pass in a fresh container after applying the patch |
| `wall_s` | `TaskResult.duration_seconds` (container setup + agent + verification) |
| `agent_s` | trace duration (agent loop only) |
| `tool_calls` | tool calls by the root agent visible in the trace (all tools, skill tools included) |
| `harness_tool_calls` | swegemma's budget counter (includes sub-agent calls, excludes free tools) |
| `repeat_share` | share of calls whose tool name and arguments exactly equal an *earlier* call in the same task |
| `malformed_share` | (calls with an unknown tool name or an argument/lookup error such as `TypeError`, `ValidationError`, `INVALID_ARGUMENTS`, `SKILL_NOT_FOUND` + raw `<\|tool_call>` text the parser could not turn into a call) ÷ (calls + those raw texts) |
| `failed_edits` | `edit_file`/`write_file` calls that returned an error |
| `skill_invocations` | calls to `list_skills` + `load_skill` + `load_skill_resource` + `run_skill_script` |
| `skill_load_rate` (arm) | share of tasks with ≥1 successful `load_skill` |

Arm-level shares (`repeat_share`, `malformed_share`, `failed_edit_share`) are pooled over all
calls, not averaged per task. Use `mcnemar_exact` (resolved, paired by task and seed),
`paired_bootstrap` (continuous metrics) and `seed_noise` (how often a task flips between seeds of
the same arm) to decide whether a difference exceeds run-to-run noise.

Test: `python tests/test_common.py` (builds a trace with swegemma's own `SessionTrace` writer).
