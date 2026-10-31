"""Runtime instrumentation for swegemma / google-adk runs (generic; counts only, no content saved).

Why: in google-adk 1.36.1 token-threshold compaction runs as a request processor before a model
call (flows/llm_flows/compaction.py) and appends its event to the session WITHOUT yielding it, so
the harness SessionTrace (fed by yielded events) is expected to miss it. The summarizer
(apps/llm_event_summarizer.py) formats only `part.text` of the compacted events, so function
calls/responses (incl. load_skill outputs) are dropped, and the initial task prompt is compacted
like any other event (all but the last `event_retention_size` events).

This module measures that directly:
  REQUESTS     one record per LLM request: messages by role, tool messages, whether the task
               prompt ("Problem Statement:") and each tracked marker string are still present
  COMPACTIONS  one record per summarizer call: events compacted, function calls / responses
               dropped, text vs non-text chars, whether the task prompt was compacted, which
               tracked markers were present before and survive in the summary
Task attribution: a ContextVar set around Evaluator.evaluate_task.

Usage: install(); set MARKERS[task_id] = [strings to track]; run; read REQUESTS / COMPACTIONS.
"""
from __future__ import annotations

import contextvars
import json
import time
from collections import Counter
from typing import Any

CURRENT_TASK: contextvars.ContextVar[str | None] = contextvars.ContextVar("pilot_current_task", default=None)
REQUESTS: list[dict[str, Any]] = []
COMPACTIONS: list[dict[str, Any]] = []
MARKERS: dict[str, list[str]] = {}
TASK_PROMPT_MARKER = "Problem Statement:"
SKILL_RESPONSE_TOOLS = {"load_skill", "load_skill_resource"}
_installed = False


def _msg_text(m: Any) -> str:
    c = m.get("content") if isinstance(m, dict) else getattr(m, "content", None)
    if c is None:
        return ""
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in c)
    return str(c)


def _get(m: Any, k: str) -> Any:
    return m.get(k) if isinstance(m, dict) else getattr(m, k, None)


def request_shape(messages: list[Any], tools: Any) -> dict[str, Any]:
    tid = CURRENT_TASK.get()
    texts = [_msg_text(m) for m in messages]
    roles = Counter(str(_get(m, "role")) for m in messages)
    marks = MARKERS.get(tid or "", [])
    return {
        "task": tid, "t": time.time(), "n_messages": len(messages), "roles": dict(roles),
        "n_tool_messages": roles.get("tool", 0),
        "n_assistant_tool_calls": sum(len(_get(m, "tool_calls") or []) for m in messages),
        "has_tools": bool(tools), "chars": sum(len(x) for x in texts),
        "has_task_prompt": any(TASK_PROMPT_MARKER in x for x in texts),
        "markers_present": [i for i, s in enumerate(marks) if any(s in x for x in texts)],
    }


def compaction_record(events: list[Any], result: Any) -> dict[str, Any]:
    tid = CURRENT_TASK.get()
    marks = MARKERS.get(tid or "", [])
    n_fc = n_fr = n_skill = 0
    text_chars = nontext_chars = 0
    task_prompt = False
    raw_blobs: list[str] = []
    for e in events:
        parts = getattr(getattr(e, "content", None), "parts", None) or []
        for p in parts:
            if getattr(p, "text", None):
                text_chars += len(p.text)
                raw_blobs.append(p.text)
                if getattr(e, "author", "") == "user" and TASK_PROMPT_MARKER in p.text:
                    task_prompt = True
            fc = getattr(p, "function_call", None)
            if fc is not None:
                n_fc += 1
                blob = json.dumps(dict(fc.args or {}), default=str)
                nontext_chars += len(blob)
                raw_blobs.append(blob)
            fr = getattr(p, "function_response", None)
            if fr is not None:
                n_fr += 1
                if getattr(fr, "name", "") in SKILL_RESPONSE_TOOLS:
                    n_skill += 1
                blob = json.dumps(getattr(fr, "response", None), default=str)
                nontext_chars += len(blob)
                raw_blobs.append(blob)
    summary = ""
    comp = getattr(getattr(result, "actions", None), "compaction", None)
    cc = getattr(comp, "compacted_content", None)
    for p in getattr(cc, "parts", None) or []:
        if getattr(p, "text", None):
            summary += p.text
    raw = "\n".join(raw_blobs)
    before = [i for i, s in enumerate(marks) if s in raw]
    return {
        "task": tid, "t": time.time(), "n_events": len(events), "function_calls_dropped": n_fc,
        "function_responses_dropped": n_fr, "skill_responses_dropped": n_skill,
        "text_chars": text_chars, "nontext_chars": nontext_chars, "task_prompt_compacted": task_prompt,
        "summary_chars": len(summary), "summary_has_task_prompt_marker": TASK_PROMPT_MARKER in summary,
        "markers_before": before, "markers_in_summary": [i for i in before if marks[i] in summary],
        "produced": result is not None,
    }


def install() -> None:
    """Patch (idempotently) the ADK LLM client, the ADK summarizer and swegemma's evaluate_task."""
    global _installed
    if _installed:
        return
    from google.adk.apps import llm_event_summarizer as les
    from google.adk.models import lite_llm
    from swegemma import evaluate as sg_eval

    orig_ac = lite_llm.LiteLLMClient.acompletion

    async def acompletion(self, model, messages, tools, **kwargs):
        try:
            REQUESTS.append(request_shape(messages, tools))
        except Exception:  # noqa: BLE001 - instrumentation must never break a run
            pass
        return await orig_ac(self, model, messages, tools, **kwargs)

    orig_sum = les.LlmEventSummarizer.maybe_summarize_events

    async def maybe_summarize_events(self, *, events):
        res = await orig_sum(self, events=events)
        try:
            COMPACTIONS.append(compaction_record(events, res))
        except Exception:  # noqa: BLE001
            pass
        return res

    orig_eval = sg_eval.Evaluator.evaluate_task

    async def evaluate_task(self, *args, **kwargs):
        task = kwargs.get("task", args[0] if args else None)
        tok = CURRENT_TASK.set(getattr(task, "instance_id", None))
        try:
            return await orig_eval(self, *args, **kwargs)
        finally:
            CURRENT_TASK.reset(tok)

    lite_llm.LiteLLMClient.acompletion = acompletion
    les.LlmEventSummarizer.maybe_summarize_events = maybe_summarize_events
    sg_eval.Evaluator.evaluate_task = evaluate_task
    _installed = True


def reset() -> None:
    REQUESTS.clear()
    COMPACTIONS.clear()


def task_compaction_stats(task_id: str, tool_call_timestamps: list[float]) -> dict[str, Any]:
    """Per-task summary: how often and when compaction fired, what it dropped, what survived."""
    comps = [c for c in COMPACTIONS if c["task"] == task_id and c["produced"]]
    reqs = [r for r in REQUESTS if r["task"] == task_id and r["has_tools"]]
    first_t = comps[0]["t"] if comps else None
    after = [r for r in reqs if first_t is not None and r["t"] > first_t]
    marks_before = sum(len(c["markers_before"]) for c in comps)
    return {
        "compactions": len(comps),
        "first_compaction_at_call": sum(1 for ts in tool_call_timestamps if first_t is not None and ts < first_t) if comps else None,
        "function_calls_dropped": sum(c["function_calls_dropped"] for c in comps),
        "function_responses_dropped": sum(c["function_responses_dropped"] for c in comps),
        "skill_responses_dropped": sum(c["skill_responses_dropped"] for c in comps),
        "nontext_share_dropped": round(sum(c["nontext_chars"] for c in comps) / max(1, sum(c["nontext_chars"] + c["text_chars"] for c in comps)), 4) if comps else None,
        "task_prompt_compacted": any(c["task_prompt_compacted"] for c in comps),
        "marker_survival": round(sum(len(c["markers_in_summary"]) for c in comps) / marks_before, 4) if marks_before else None,
        "requests": len(reqs),
        "requests_after_first_compaction": len(after),
        "after_with_task_prompt": sum(r["has_task_prompt"] for r in after),
        "max_tool_messages_before": max((r["n_tool_messages"] for r in reqs if first_t is None or r["t"] <= first_t), default=0),
        "max_tool_messages_after": max((r["n_tool_messages"] for r in after), default=None),
    }
