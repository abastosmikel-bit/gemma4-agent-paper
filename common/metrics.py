"""Shared per-task metrics, identical across pilots.

resolved, wall_s, tool_calls, dup_call_share (same tool + same args as an earlier call),
malformed_share, failed_edits, edit_attempts, skill_invocations.

Definitions:
  malformed call: the harness/ADK rejected the call itself, not its effect: unknown tool,
    argument validation/type errors, or a skill-tool argument error. Truncated tool calls never
    reach the trace as calls, so they are counted separately from "cut off" nudges.
  edit attempt: edit_file, write_file, or a skill script whose name contains "edit"/"insert".
  failed edit: an edit attempt whose result has status "error" (or, for skills, an error JSON
    in stdout).
"""
from __future__ import annotations

import json
from typing import Any

from .traces import ParsedTrace, ToolEvent

MALFORMED_ERROR_TYPES = {"ValueError", "TypeError", "ValidationError", "KeyError", "ToolNotFoundError",
                         "InvalidArgument", "JSONDecodeError", "pydantic_core._pydantic_core.ValidationError"}
EDIT_TOOLS = {"edit_file", "write_file"}
SKILL_TOOLS = {"load_skill", "load_skill_resource", "run_skill_script", "list_skills"}
CUTOFF_MARK = "was cut off"


def _canon(args: dict) -> str:
    return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)


def skill_stdout_json(ev: ToolEvent) -> dict | None:
    r = ev.result
    if isinstance(r, dict) and isinstance(r.get("stdout"), str):
        s = r["stdout"].strip()
        if s.startswith("{"):
            try:
                return json.loads(s.splitlines()[0] if s.count("\n") and not s.endswith("}") else s)
            except json.JSONDecodeError:
                return None
    return None


def is_error(ev: ToolEvent) -> bool:
    r = ev.result
    if isinstance(r, dict):
        if r.get("status") == "error" or "error_code" in r:
            return True
        j = skill_stdout_json(ev)
        return bool(j and j.get("status") == "error")
    return False


def is_malformed(ev: ToolEvent) -> bool:
    r = ev.result
    if not isinstance(r, dict):
        return False
    et = str(r.get("error_type", ""))
    if et in MALFORMED_ERROR_TYPES:
        return True
    if r.get("error_code") in ("INVALID_ARGUMENTS", "MISSING_SKILL_NAME", "SKILL_NOT_FOUND", "MISSING_FILE_PATH"):
        return True
    msg = str(r.get("error", "")) + str(r.get("error_message", ""))
    return "not found in tools_dict" in msg or "missing" in msg.lower() and "argument" in msg.lower()


def is_edit(ev: ToolEvent) -> bool:
    if ev.name in EDIT_TOOLS:
        return True
    if ev.name == "run_skill_script":
        fp = str(ev.args.get("file_path", ""))
        a = ev.args.get("args")
        sub = (a[0] if isinstance(a, list) and a else "") if not isinstance(a, dict) else a.get("op", "")
        return any(k in (fp + " " + str(sub)) for k in ("edit", "insert"))
    return False


def task_metrics(trace: ParsedTrace, result_row: dict | None = None) -> dict[str, Any]:
    evs = trace.events
    seen, dups = set(), 0
    for ev in evs:
        k = (ev.name, _canon(ev.args))
        dups += k in seen
        seen.add(k)
    edits = [e for e in evs if is_edit(e)]
    n = len(evs)
    row = result_row or {}
    return {
        "instance_id": row.get("instance_id"),
        "resolved": row.get("resolved"),
        "wall_s": row.get("duration_seconds"),
        "tool_calls": n,
        "harness_tool_calls": row.get("tool_calls"),
        "dup_call_share": dups / n if n else 0.0,
        "malformed_calls": sum(is_malformed(e) for e in evs),
        "malformed_share": sum(is_malformed(e) for e in evs) / n if n else 0.0,
        "cutoff_nudges": sum(CUTOFF_MARK in m for m in trace.user_messages),
        "edit_attempts": len(edits),
        "failed_edits": sum(is_error(e) for e in edits),
        "failed_edit_share": (sum(is_error(e) for e in edits) / len(edits)) if edits else None,
        "skill_invocations": sum(e.name in SKILL_TOOLS for e in evs),
        "skill_script_runs": sum(e.name == "run_skill_script" for e in evs),
        "submitted": any(e.name == "submit_patch" for e in evs),
        "patch_size": row.get("agent_patch_size"),
    }


def aggregate(rows: list[dict]) -> dict[str, Any]:
    n = len(rows)
    if not n:
        return {}
    s = lambda k: sum((r.get(k) or 0) for r in rows)  # noqa: E731
    edits = s("edit_attempts")
    calls = s("tool_calls")
    return {
        "tasks": n,
        "resolved": s("resolved"),
        "resolved_rate": s("resolved") / n,
        "mean_wall_s": s("wall_s") / n,
        "mean_tool_calls": calls / n,
        "dup_call_share": sum(r["dup_call_share"] * r["tool_calls"] for r in rows) / calls if calls else 0.0,
        "malformed_share": s("malformed_calls") / calls if calls else 0.0,
        "cutoff_nudges": s("cutoff_nudges"),
        "edit_attempts": edits,
        "failed_edits": s("failed_edits"),
        "failed_edit_share": s("failed_edits") / edits if edits else None,
        "skill_invocations": s("skill_invocations"),
        "tasks_using_skill": sum(1 for r in rows if r.get("skill_script_runs")),
        "empty_patches": sum(1 for r in rows if not r.get("patch_size")),
    }
