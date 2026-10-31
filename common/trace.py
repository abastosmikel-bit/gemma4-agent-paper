"""Parse swegemma/adk-eval-core session traces into a flat event list.

Supports the ATIF v1.7 JSON written by `SessionTrace.save()` (the harness
default, `results_dir/traces/trace_<id>.json`) and the legacy
`{"entries": [...]}` format. Mirrors `SessionTrace.from_dict` in
adk-eval-core 0.1.0 without importing it, so this works on any machine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Event:
    type: str  # tool_call | tool_response | thinking | text | final | continuation_nudge | compaction | ...
    author: str = ""
    elapsed: float = 0.0
    tool: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    result: str = ""
    content: str = ""
    timestamp: float = 0.0  # absolute wall clock (s since epoch) when the harness recorded it
    meta: dict[str, Any] | None = None  # e.g. compaction start/end timestamps


@dataclass
class ToolCall:
    index: int  # order among tool calls in the task (0-based)
    tool: str
    args: dict[str, Any]
    author: str
    elapsed: float
    result: str | None = None  # raw response text (JSON string) if matched
    timestamp: float = 0.0

    def result_json(self) -> dict[str, Any] | None:
        if self.result is None:
            return None
        try:
            v = json.loads(self.result)
        except (ValueError, TypeError):
            return None
        # ADK sometimes wraps tool output as {"result": "<json string>"}
        if isinstance(v, dict) and set(v) == {"result"} and isinstance(v["result"], str):
            try:
                inner = json.loads(v["result"])
                if isinstance(inner, dict):
                    return inner
            except ValueError:
                pass
        return v if isinstance(v, dict) else None


def _atif_events(data: dict[str, Any]) -> list[Event]:
    evs: list[Event] = []
    for step in data.get("steps", []):
        source = step.get("source", "agent")
        msg = step.get("message")
        extra = step.get("extra") or {}
        author = extra.get("author", source)
        etype = extra.get("event_type")
        el = float(extra.get("elapsed_s", 0.0) or 0.0)
        ts = float(extra.get("timestamp", 0.0) or 0.0)
        if msg is not None or (etype is not None and not step.get("tool_calls") and not step.get("observation") and etype != "usage"):
            if not etype:
                etype = {"system": "system_instruction", "user": "task_prompt"}.get(source, "text")
            evs.append(Event(etype, author, el, content=str(msg) if msg is not None else "", timestamp=ts,
                             meta=extra.get("metadata")))
        for tc in step.get("tool_calls", []) or []:
            tx = tc.get("extra") or {}
            evs.append(Event("tool_call", tx.get("author", author), float(tx.get("elapsed_s", el) or 0.0),
                             tool=tc.get("function_name", ""), args=tc.get("arguments") or {},
                             timestamp=float(tx.get("timestamp", ts) or 0.0)))
        obs = step.get("observation")
        if obs:
            ox = obs.get("extra") or {}
            content = obs.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, default=str)
            evs.append(Event("tool_response", ox.get("author") or "system", float(ox.get("elapsed_s", el) or 0.0),
                             tool=ox.get("tool_name", ""), result=content, timestamp=float(ox.get("timestamp", ts) or 0.0)))
    return evs


def _legacy_events(data: dict[str, Any]) -> list[Event]:
    return [
        Event(e.get("type") or "custom", e.get("author") or "", float(e.get("elapsed_s") or 0.0),
              tool=e.get("tool") or "", args=e.get("args") or {}, result=e.get("result") or "", content=e.get("content") or "",
              timestamp=float(e.get("timestamp") or 0.0), meta=e.get("metadata"))
        for e in data.get("entries", [])
    ]


def parse_trace(data: dict[str, Any]) -> list[Event]:
    if str(data.get("schema_version", "")).startswith("ATIF"):
        return _atif_events(data)
    return _legacy_events(data)


def load_trace(path: str | Path) -> list[Event]:
    with open(path, encoding="utf-8") as f:
        return parse_trace(json.load(f))


def pair_tool_calls(events: list[Event]) -> list[ToolCall]:
    """Match each tool_response to the earliest unanswered tool_call with the same tool name."""
    calls: list[ToolCall] = []
    pending: dict[str, list[ToolCall]] = {}
    for ev in events:
        if ev.type == "tool_call":
            c = ToolCall(len(calls), ev.tool, ev.args or {}, ev.author, ev.elapsed, timestamp=ev.timestamp)
            calls.append(c)
            pending.setdefault(ev.tool, []).append(c)
        elif ev.type == "tool_response":
            q = pending.get(ev.tool)
            if q:
                q.pop(0).result = ev.result
    return calls
