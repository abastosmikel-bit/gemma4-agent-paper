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
  SUMMARIES    per task, the text of every compaction summary (visible parts only) with how much of the
               task statement it keeps. TEXT: competition-derived, write it only under private/
               (dump_summaries); everything else here is counts.
Per request it also records where the task-prompt marker sits (a compaction summary = a message containing a
recorded summary, which ADK shows as a user message "For context: [model] said: ..."; the original prompt = another user
message holding the task statement; other),
the requested output tokens, the prompt tokens the server reports, and the exception type if it failed.
Task attribution: a ContextVar set around Evaluator.evaluate_task.

Usage: install(); set MARKERS[task_id] = [strings to track]; run; read REQUESTS / COMPACTIONS.
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import time
from collections import Counter
from typing import Any

CURRENT_TASK: contextvars.ContextVar[str | None] = contextvars.ContextVar("pilot_current_task", default=None)
REQUESTS: list[dict[str, Any]] = []
COMPACTIONS: list[dict[str, Any]] = []
MARKERS: dict[str, list[str]] = {}
SUMMARIES: dict[str, list[dict[str, Any]]] = {}
PROBLEM: dict[str, str] = {}          # task statement as given to the agent (set from the task in evaluate_task)
TASK_PROMPT_MARKER = "Problem Statement:"
_FP_CHARS = 160
AGENT_REQUEST_TIMEOUT_S = 900
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


def _norm(text: str) -> str:
    return " ".join(str(text).split())


_WORD = re.compile(r"[a-z0-9_]+")


def statement_retention(statement: str, summary: str) -> dict[str, Any]:
    """How much of `statement` a summary keeps: share of the statement's word 5-grams that occur in the summary,
    and share of its distinct words of >= 4 characters that occur in it. Numbers only."""
    sw, uw = _WORD.findall(statement.lower()), _WORD.findall(summary.lower())

    def grams(w: list[str], n: int) -> set[tuple[str, ...]]:
        return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}
    s5, u5 = grams(sw, 5), grams(uw, 5)
    sv, uv = {w for w in sw if len(w) >= 4}, set(uw)
    return {"ngram5_recall": round(len(s5 & u5) / len(s5), 4) if s5 else None,
            "word_recall": round(len(sv & uv) / len(sv), 4) if sv else None,
            "statement_words": len(sw), "summary_words": len(uw)}


def marker_sources(tid: str | None, messages: list[Any]) -> tuple[list[str], bool, bool]:
    """(where the task-prompt marker occurs: 'prompt' / 'summary' / 'other'; original statement present in a user
    message that is not a summary; a recorded summary present in any message)."""
    stmt = _norm(PROBLEM.get(tid or "", ""))[:_FP_CHARS]
    fps = [s["fp"] for s in SUMMARIES.get(tid or "", []) if s.get("fp")]
    src: set[str] = set()
    prompt_present = summary_present = False
    for m in messages:
        role, text = str(_get(m, "role")), _msg_text(m)
        nt = _norm(text)
        # ADK (contents.py, _present_other_agent_message) shows a compaction summary to the model as a USER message
        # "For context: [model] said: <summary>", so a summary is recognised by its text, whatever the role.
        is_summary = any(fp in nt for fp in fps)
        is_prompt = role == "user" and bool(stmt) and stmt in nt and not is_summary
        prompt_present |= is_prompt
        summary_present |= is_summary
        if TASK_PROMPT_MARKER in text:
            src.add("prompt" if is_prompt else "summary" if is_summary else "other")
    return sorted(src), prompt_present, summary_present


def request_shape(messages: list[Any], tools: Any, kwargs: dict[str, Any] | None = None) -> dict[str, Any]:
    tid = CURRENT_TASK.get()
    texts = [_msg_text(m) for m in messages]
    roles = Counter(str(_get(m, "role")) for m in messages)
    marks = MARKERS.get(tid or "", [])
    src, prompt_present, summary_present = marker_sources(tid, messages)
    kw = kwargs or {}
    return {
        "task": tid, "t": time.time(), "n_messages": len(messages), "roles": dict(roles),
        "n_tool_messages": roles.get("tool", 0),
        "n_assistant_tool_calls": sum(len(_get(m, "tool_calls") or []) for m in messages),
        "has_tools": bool(tools), "chars": sum(len(x) for x in texts),
        "has_task_prompt": any(TASK_PROMPT_MARKER in x for x in texts),
        "marker_sources": src, "original_prompt_present": prompt_present, "summary_present": summary_present,
        "requested_output_tokens": kw.get("max_completion_tokens") or kw.get("max_tokens"),
        "markers_present": [i for i, s in enumerate(marks) if any(s in x for x in texts)],
    }


def dump_summaries(path: Any) -> int:
    """Write every recorded summary (TEXT, competition-derived) as JSONL. Call it with a path under private/."""
    from pathlib import Path
    n = 0
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for tid, items in SUMMARIES.items():
            for i, s in enumerate(items):
                f.write(json.dumps({"task": tid, "index": i, **{k: v for k, v in s.items() if k != "fp"}}) + "\n")
                n += 1
    return n


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
        if getattr(p, "text", None) and not getattr(p, "thought", False):   # what later requests see
            summary += p.text
    raw = "\n".join(raw_blobs)
    before = [i for i, s in enumerate(marks) if s in raw]
    ret = statement_retention(PROBLEM.get(tid or "", ""), summary) if summary else {}
    if result is not None and summary:
        SUMMARIES.setdefault(tid or "", []).append({"t": time.time(), "text": summary, "fp": _norm(summary)[:_FP_CHARS],
                                                    "has_marker": TASK_PROMPT_MARKER in summary, **ret})
    return {
        "summary_ngram5_recall": ret.get("ngram5_recall"), "summary_word_recall": ret.get("word_recall"),
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

    import litellm
    from common.server_watchdog import tracked

    # per-request timeout for agent requests (LiteLLM's default is 6000 s). 900 s = the per-task time budget:
    # a single request longer than the whole task budget is useless anyway.
    timeout_s = float(os.environ.get("PILOT_AGENT_REQUEST_TIMEOUT", AGENT_REQUEST_TIMEOUT_S))
    litellm.request_timeout = timeout_s
    orig_ac = lite_llm.LiteLLMClient.acompletion

    async def acompletion(self, model, messages, tools, **kwargs):
        rec = None
        try:
            rec = request_shape(messages, tools, kwargs)
            REQUESTS.append(rec)
        except Exception:  # noqa: BLE001 - instrumentation must never break a run
            pass
        kwargs.setdefault("timeout", timeout_s)
        with tracked():  # counts in-flight requests for the watchdog; fails fast after a freeze
            try:
                resp = await orig_ac(self, model, messages, tools, **kwargs)
            except Exception as e:
                if rec is not None:
                    rec["error"] = type(e).__name__
                raise
        if rec is not None:
            try:
                u = resp.get("usage") if isinstance(resp, dict) else getattr(resp, "usage", None)
                rec["prompt_tokens"] = u.get("prompt_tokens") if isinstance(u, dict) else getattr(u, "prompt_tokens", None)
            except Exception:  # noqa: BLE001
                pass
        return resp

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
        from common.server_watchdog import ServerFrozen, STATE, TRIPPED
        if TRIPPED.is_set():  # server frozen: do not even set up the task's sandbox
            raise ServerFrozen(f"inference server frozen ({STATE['reason']}); task skipped")
        task = kwargs.get("task", args[0] if args else None)
        tid = getattr(task, "instance_id", None)
        if tid is not None:
            PROBLEM[tid] = str(getattr(task, "problem_statement", "") or "")
        tok = CURRENT_TASK.set(tid)
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
    SUMMARIES.clear()


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
        # where the marker sits after compaction (requests may have several sources)
        "after_marker_in_prompt": sum("prompt" in r.get("marker_sources", []) for r in after),
        "after_marker_in_summary_only": sum("summary" in r.get("marker_sources", []) and "prompt" not in r.get("marker_sources", [])
                                            for r in after),
        "after_marker_other_only": sum(bool(r.get("marker_sources")) and not {"prompt", "summary"} & set(r["marker_sources"])
                                       for r in after),
        "after_with_original_prompt": sum(bool(r.get("original_prompt_present")) for r in after),
        "summaries": len(SUMMARIES.get(task_id, [])),
        "summaries_with_marker": sum(bool(x.get("has_marker")) for x in SUMMARIES.get(task_id, [])),
        "summary_ngram5_recall_mean": _mean([x.get("ngram5_recall") for x in SUMMARIES.get(task_id, [])]),
        "summary_ngram5_recall_max": max([x["ngram5_recall"] for x in SUMMARIES.get(task_id, []) if x.get("ngram5_recall") is not None], default=None),
        "summary_word_recall_mean": _mean([x.get("word_recall") for x in SUMMARIES.get(task_id, [])]),
        "requested_output_tokens": sorted({r["requested_output_tokens"] for r in reqs if r.get("requested_output_tokens")}),
        "max_prompt_tokens": max([r["prompt_tokens"] for r in reqs if r.get("prompt_tokens")], default=None),
        "context_errors": sum("ContextWindow" in str(r.get("error") or "") for r in reqs),
        "prompt_tokens_before_first_context_error": _before_error(reqs),
        "max_tool_messages_before": max((r["n_tool_messages"] for r in reqs if first_t is None or r["t"] <= first_t), default=0),
        "max_tool_messages_after": max((r["n_tool_messages"] for r in after), default=None),
    }


def _mean(xs: list[Any]) -> float | None:
    v = [x for x in xs if x is not None]
    return round(sum(v) / len(v), 4) if v else None


def _before_error(reqs: list[dict[str, Any]]) -> int | None:
    """Prompt tokens of the last successful request before the first context-window error (None if no error)."""
    last = None
    for r in sorted(reqs, key=lambda r: r["t"]):
        if "ContextWindow" in str(r.get("error") or ""):
            return last
        if r.get("prompt_tokens"):
            last = r["prompt_tokens"]
    return None
