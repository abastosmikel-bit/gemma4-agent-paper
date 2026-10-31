"""Per-task and aggregate metrics shared by all pilots.

Common metric set (identical definitions in every pilot):
  resolved          scorer verdict (Phase 2 pytest + JUnit validation)
  wall_s            TaskResult.duration_seconds (setup + agent + verification)
  agent_s           last event timestamp in the trace (time inside the agent loop)
  tool_calls        tool_call events in the ROOT trace. Calls made inside an AgentTool sub-agent
                    (e.g. code_analyzer_agent) run in a separate ADK Runner and are NOT in the
                    trace; only the AgentTool call itself is (verified in google-adk 1.36.1
                    tools/agent_tool.py; pilot A found this first). Localization metrics are
                    therefore lower bounds when the agent delegates reading to the sub-agent.
  budget_tool_calls harness-counted calls (TaskResult.tool_calls; budget-gated tools only)
  repeat_share      share of tool calls identical (same tool + canonical JSON args) to an
                    earlier call in the same task
  malformed_share   malformed / (tool_calls + unparsed_tool_calls); malformed = unknown tool,
                    missing/unexpected arguments, or argument validation errors; unparsed =
                    turns cut off inside an unclosed <|tool_call> (harness nudge type 1)
  failed_edits      edit_file / write_file calls that returned status=error
  skill_calls       calls to ADK skill tools (list/search/load_skill, load_skill_resource,
                    run_skill_script)
Optional localization metrics (need gold locations, see common.tasks.gold_locations):
  viewed_gold_file, first_gold_view_call, edited_gold_file, edited_gold_function
"""
from __future__ import annotations

import json
import re
import statistics
from typing import Any, Iterable

from .diffs import parse_unified_diff
from .trace import Event, ToolCall, pair_tool_calls

SKILL_TOOLS = {"list_skills", "search_skills", "load_skill", "load_skill_resource", "run_skill_script"}
EDIT_TOOLS = {"edit_file", "write_file"}
_MALFORMED_TYPES = {"TypeError", "ValidationError", "KeyError", "JSONDecodeError", "ArgumentError"}
_MALFORMED_PATTERNS = (
    re.compile(r"Tool '.*' not found", re.S),
    re.compile(r"mandatory input parameters are not present"),
    re.compile(r"unexpected keyword argument"),
    re.compile(r"missing \d+ required (positional|keyword)"),
    re.compile(r"cannot be greater than end_line"),
)
_UNPARSED_NUDGE = "tool call finished closing"


def canonical_call(c: ToolCall) -> str:
    return c.tool + "\x00" + json.dumps(c.args, sort_keys=True, default=str)


def _error_info(c: ToolCall) -> tuple[bool, str, str]:
    r = c.result_json()
    if r is None:
        return False, "", ""
    if r.get("status") == "error":
        return True, str(r.get("error_type", "")), str(r.get("error_message") or r.get("error") or "")
    return False, "", ""


def is_malformed(c: ToolCall) -> bool:
    is_err, etype, msg = _error_info(c)
    if not is_err:
        return False
    if etype in _MALFORMED_TYPES:
        return True
    return any(p.search(msg) for p in _MALFORMED_PATTERNS)


def call_touches_path(c: ToolCall, path: str) -> bool:
    """True if a tool call reads/views `path` (read_file, or a shell command naming it)."""
    if c.tool == "read_file":
        fp = str(c.args.get("filepath", "")).lstrip("/")
        fp = fp[len("workspace/"):] if fp.startswith("workspace/") else fp
        return fp == path or fp.endswith("/" + path)
    if c.tool == "run_command":
        return path in str(c.args.get("command", ""))
    return False


def task_metrics(
    result: dict[str, Any],
    events: list[Event],
    gold: dict[str, Any] | None = None,
    agent_patch_scopes: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Compute the common metric row for one task (root-agent calls only, see module doc).

    result: a TaskResult row (task_results.jsonl line or TaskResult.model_dump()).
    events: parsed trace (common.trace.load_trace / parse_trace).
    gold:   optional GoldLocations.to_dict() for localization metrics.
    agent_patch_scopes: optional dotted names of scopes the agent's patch changed.
    The returned row holds numbers/flags only (no patch, no trace text).
    """
    calls = pair_tool_calls(events)
    n = len(calls)
    seen: set[str] = set()
    repeats = 0
    for c in calls:
        k = canonical_call(c)
        if k in seen:
            repeats += 1
        seen.add(k)
    unparsed = sum(1 for e in events if e.type == "continuation_nudge" and _UNPARSED_NUDGE in e.content)
    nudges = sum(1 for e in events if e.type == "continuation_nudge")
    malformed = sum(1 for c in calls if is_malformed(c))
    edit_calls = [c for c in calls if c.tool in EDIT_TOOLS]
    failed_edits = sum(1 for c in edit_calls if _error_info(c)[0])
    by_tool: dict[str, int] = {}
    for c in calls:
        by_tool[c.tool] = by_tool.get(c.tool, 0) + 1
    agent_s = max((e.elapsed for e in events), default=0.0)
    patch = result.get("agent_patch") or ""
    patch_files = [fd.path for fd in parse_unified_diff(patch)] if patch else []

    row: dict[str, Any] = {
        "instance_id": result.get("task_id") or result.get("instance_id"),
        "resolved": bool(result.get("resolved")),
        "error": (result.get("error_message") or "")[:120] or None,
        "wall_s": round(float(result.get("duration_seconds") or 0.0), 1),
        "agent_s": round(agent_s, 1),
        "tool_calls": n,
        "budget_tool_calls": int(result.get("tool_calls") or 0),
        "llm_calls": int(result.get("total_llm_calls") or 0),
        "total_tokens": int(result.get("total_tokens") or 0),
        "repeat_calls": repeats,
        "repeat_share": round(repeats / n, 4) if n else 0.0,
        "malformed_calls": malformed,
        "unparsed_tool_calls": unparsed,
        "malformed_share": round((malformed + unparsed) / (n + unparsed), 4) if (n + unparsed) else 0.0,
        "edit_calls": len(edit_calls),
        "failed_edits": failed_edits,
        "skill_calls": sum(1 for c in calls if c.tool in SKILL_TOOLS),
        "nudges": nudges,
        "submitted": any(c.tool == "submit_patch" for c in calls),
        "patch_nonempty": bool(patch.strip()),
        "patch_files": len(patch_files),
        "calls_by_tool": by_tool,
    }
    if gold is not None:
        gfiles = list(gold.get("src_files") or [])
        first = next((c.index for c in calls if any(call_touches_path(c, g) for g in gfiles)), None)
        row["viewed_gold_file"] = first is not None
        row["first_gold_view_call"] = first
        row["edited_gold_file"] = bool(set(patch_files) & set(gfiles))
        row["edited_only_gold_files"] = bool(patch_files) and set(patch_files) <= set(gfiles)
        if agent_patch_scopes is not None:
            gfun = {f["dotted"] for f in gold.get("functions") or []}
            row["edited_gold_function"] = bool(gfun & set(agent_patch_scopes)) if gfun else None
    return row


def _mean(xs: list[float]) -> float | None:
    return round(statistics.fmean(xs), 3) if xs else None


def _median(xs: list[float]) -> float | None:
    return round(statistics.median(xs), 3) if xs else None


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate common metrics over a list of task rows (one condition/run)."""
    n = len(rows)
    tot_calls = sum(r["tool_calls"] for r in rows)
    tot_unparsed = sum(r["unparsed_tool_calls"] for r in rows)
    out: dict[str, Any] = {
        "n_tasks": n,
        "resolved": sum(r["resolved"] for r in rows),
        "resolve_rate": round(sum(r["resolved"] for r in rows) / n, 4) if n else None,
        "wall_s_mean": _mean([r["wall_s"] for r in rows]),
        "wall_s_median": _median([r["wall_s"] for r in rows]),
        "agent_s_mean": _mean([r["agent_s"] for r in rows]),
        "tool_calls_mean": _mean([r["tool_calls"] for r in rows]),
        # pooled shares (calls across all tasks) and per-task means
        "repeat_share_pooled": round(sum(r["repeat_calls"] for r in rows) / tot_calls, 4) if tot_calls else 0.0,
        "malformed_share_pooled": round((sum(r["malformed_calls"] for r in rows) + tot_unparsed) / (tot_calls + tot_unparsed), 4)
        if (tot_calls + tot_unparsed) else 0.0,
        "repeat_share_task_mean": _mean([r["repeat_share"] for r in rows]),
        "malformed_share_task_mean": _mean([r["malformed_share"] for r in rows]),
        "failed_edits_total": sum(r["failed_edits"] for r in rows),
        "edit_calls_total": sum(r["edit_calls"] for r in rows),
        "skill_calls_total": sum(r["skill_calls"] for r in rows),
        "submitted_share": round(sum(r["submitted"] for r in rows) / n, 4) if n else None,
        "patch_nonempty_share": round(sum(r["patch_nonempty"] for r in rows) / n, 4) if n else None,
        "errors": sum(1 for r in rows if r.get("error")),
    }
    for k in ("viewed_gold_file", "edited_gold_file", "edited_only_gold_files", "edited_gold_function"):
        vals = [r[k] for r in rows if r.get(k) is not None]
        if vals:
            out[f"{k}_share"] = round(sum(vals) / len(vals), 4)
    fg = [r["first_gold_view_call"] for r in rows if r.get("first_gold_view_call") is not None]
    if fg:
        out["first_gold_view_call_median"] = _median(fg)
    return out


def paired_flips(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> dict[str, Any]:
    """Paired comparison of two runs over the same tasks (b vs a).

    Returns discordant counts and an exact two-sided McNemar (binomial) p-value.
    """
    ra = {r["instance_id"]: r["resolved"] for r in a}
    rb = {r["instance_id"]: r["resolved"] for r in b}
    common = sorted(set(ra) & set(rb))
    gain = sum(1 for t in common if rb[t] and not ra[t])
    loss = sum(1 for t in common if ra[t] and not rb[t])
    m = gain + loss
    if m == 0:
        p = 1.0
    else:
        from math import comb
        k = min(gain, loss)
        p = min(1.0, 2 * sum(comb(m, i) for i in range(k + 1)) / 2 ** m)
    return {"n_common": len(common), "b_only": gain, "a_only": loss, "both": sum(1 for t in common if ra[t] and rb[t]),
            "delta": (sum(rb[t] for t in common) - sum(ra[t] for t in common)), "mcnemar_exact_p": round(p, 4)}
