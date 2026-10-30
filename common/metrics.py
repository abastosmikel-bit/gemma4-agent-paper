"""Shared per-task and per-arm metrics, identical across all pilots.

Definitions (see common/README.md for the plain-language version):
  resolved              harness verdict (Phase 2 pytest), bool
  wall_s                TaskResult.duration_seconds (setup + agent + verify)
  agent_s               trace duration (agent loop only)
  tool_calls            root-agent tool calls visible in the trace (all tools)
  harness_tool_calls    swegemma tool_calls_used (budget-counted, incl. sub-agents)
  repeat_share          calls whose (tool, args) equal an EARLIER call in the same task
  malformed_share       malformed calls / (calls + raw tool-call texts)
  failed_edits          edit_file / write_file calls that returned an error
  skill_*               list_skills / load_skill / load_skill_resource / run_skill_script
"""
from __future__ import annotations

import math
import random
import statistics
from collections import Counter
from typing import Any, Iterable

from .trace_parser import ParsedTrace

SKILL_TOOLS = ("list_skills", "load_skill", "load_skill_resource", "run_skill_script")
EDIT_TOOLS = ("edit_file", "write_file")

# Error types/codes that mean "the call itself was wrong" (bad name, bad args),
# as opposed to a well-formed call whose action failed (e.g. a test failing).
MALFORMED_ERROR_TYPES = {
    "TypeError", "ValidationError", "KeyError", "JSONDecodeError",
    "INVALID_ARGUMENTS", "SKILL_NOT_FOUND", "RESOURCE_NOT_FOUND",
    "SCRIPT_NOT_FOUND", "INVALID_RESOURCE_PATH", "UNSUPPORTED_SCRIPT_TYPE",
}


def _is_malformed(ev, declared_tools: set[str] | None) -> bool:
    if declared_tools is not None and ev.name not in declared_tools:
        return True
    et = ev.error_type
    if et in MALFORMED_ERROR_TYPES:
        return True
    if et == "ValueError":
        msg = str((ev.response or {}).get("error", "")).lower()
        return "not found" in msg or "argument" in msg
    return False


def task_metrics(
    pt: ParsedTrace,
    result: dict[str, Any] | None = None,
    declared_tools: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Compute the shared metrics for one task run.

    result: dict with optional keys resolved, duration_seconds, tool_calls (harness count).
    declared_tools: tool names the agent was given; None disables the unknown-tool check.
    """
    result = result or {}
    declared = set(declared_tools) | set(SKILL_TOOLS) if declared_tools is not None else None
    evs = pt.events
    n = len(evs)

    seen: set[str] = set()
    repeats = 0
    for ev in evs:
        if ev.key in seen:
            repeats += 1
        seen.add(ev.key)

    malformed = sum(_is_malformed(ev, declared) for ev in evs)
    raw_texts = pt.raw_tool_call_texts
    names = Counter(ev.name for ev in evs)
    loaded = Counter(
        str(ev.args.get("skill_name")) for ev in evs if ev.name == "load_skill" and ev.ok
    )

    return {
        "instance_id": pt.instance_id,
        "resolved": bool(result.get("resolved", False)),
        "wall_s": result.get("duration_seconds"),
        "agent_s": pt.duration_s,
        "tool_calls": n,
        "harness_tool_calls": result.get("tool_calls"),
        "repeat_calls": repeats,
        "repeat_share": repeats / n if n else 0.0,
        "malformed_calls": malformed + raw_texts,
        "raw_tool_call_texts": raw_texts,
        "malformed_share": (malformed + raw_texts) / (n + raw_texts) if (n + raw_texts) else 0.0,
        "edit_calls": sum(names[t] for t in EDIT_TOOLS),
        "failed_edits": sum(1 for ev in evs if ev.name in EDIT_TOOLS and not ev.ok),
        "skill_list_calls": names["list_skills"],
        "skill_load_calls": names["load_skill"],
        "skill_resource_calls": names["load_skill_resource"],
        "skill_script_calls": names["run_skill_script"],
        "skill_invocations": sum(names[t] for t in SKILL_TOOLS),
        "skills_loaded": dict(loaded),
        "submitted": names["submit_patch"] > 0,
        "prompt_tokens": pt.prompt_tokens,
        "completion_tokens": pt.completion_tokens,
        "compactions": pt.n_compactions,
        "tool_breakdown": dict(names),
    }


def _mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Arm-level summary over task rows (one row per task x seed)."""
    n = len(rows)
    if not n:
        return {"n": 0}
    tot_calls = sum(r["tool_calls"] for r in rows)
    loads = Counter()
    for r in rows:
        loads.update(r.get("skills_loaded") or {})
    return {
        "n": n,
        "resolved": sum(r["resolved"] for r in rows),
        "resolve_rate": sum(r["resolved"] for r in rows) / n,
        "wall_s_mean": _mean([r.get("wall_s") for r in rows]),
        "agent_s_mean": _mean([r.get("agent_s") for r in rows]),
        "tool_calls_mean": tot_calls / n,
        # pooled shares (calls-weighted) are less noisy than per-task means
        "repeat_share": sum(r["repeat_calls"] for r in rows) / tot_calls if tot_calls else 0.0,
        "malformed_share": sum(r["malformed_calls"] for r in rows)
        / max(1, tot_calls + sum(r["raw_tool_call_texts"] for r in rows)),
        "failed_edits_mean": _mean([r["failed_edits"] for r in rows]),
        "failed_edit_share": sum(r["failed_edits"] for r in rows)
        / max(1, sum(r["edit_calls"] for r in rows)),
        "skill_invocations_mean": _mean([r["skill_invocations"] for r in rows]),
        "tasks_with_skill_load": sum(r["skill_load_calls"] > 0 for r in rows),
        "skill_load_rate": sum(r["skill_load_calls"] > 0 for r in rows) / n,
        "skills_loaded": dict(loads),
        "submit_rate": sum(r["submitted"] for r in rows) / n,
    }


# ---------------------------------------------------------------- statistics

def mcnemar_exact(a: list[bool], b: list[bool]) -> dict[str, Any]:
    """Exact two-sided McNemar test on paired binary outcomes (same tasks, same seeds)."""
    assert len(a) == len(b)
    b_only = sum((not x) and y for x, y in zip(a, b))
    a_only = sum(x and (not y) for x, y in zip(a, b))
    k, m = min(a_only, b_only), a_only + b_only
    p = 1.0 if m == 0 else min(1.0, 2 * sum(math.comb(m, i) for i in range(k + 1)) / 2 ** m)
    return {"a_only": a_only, "b_only": b_only, "discordant": m, "p_two_sided": p}


def paired_bootstrap(a: list[float], b: list[float], iters: int = 10000, seed: int = 0) -> dict[str, Any]:
    """95% bootstrap CI of mean(b - a) over paired observations."""
    assert len(a) == len(b) and a
    d = [y - x for x, y in zip(a, b)]
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(d, k=len(d))) for _ in range(iters))
    return {
        "mean_diff": statistics.fmean(d),
        "ci95": (means[int(0.025 * iters)], means[int(0.975 * iters) - 1]),
    }


def seed_noise(rows_by_seed: dict[int, dict[str, bool]]) -> dict[str, Any]:
    """Run-to-run noise for one arm: how often the same task flips between seeds."""
    seeds = sorted(rows_by_seed)
    if len(seeds) < 2:
        return {"seeds": seeds, "flip_rate": None}
    common = set.intersection(*(set(rows_by_seed[s]) for s in seeds))
    flips = sum(len({rows_by_seed[s][t] for s in seeds}) > 1 for t in common)
    rates = [sum(rows_by_seed[s][t] for t in common) / len(common) for s in seeds] if common else []
    return {
        "seeds": seeds,
        "n_tasks": len(common),
        "flip_rate": flips / len(common) if common else None,
        "resolve_rate_by_seed": rates,
    }
