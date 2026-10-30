"""Parse swegemma ATIF v1.7 trace files (results/<run>/traces/trace_<id>.json) into flat tool events.

ATIF observations carry no tool_call_id, so each response is paired with the earliest
unanswered call of the same tool name (FIFO), which matches the harness's emission order.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolEvent:
    idx: int
    name: str
    args: dict[str, Any]
    result: Any = None          # parsed JSON dict when possible, else raw string/list
    author: str | None = None


@dataclass
class ParsedTrace:
    events: list[ToolEvent] = field(default_factory=list)
    user_messages: list[str] = field(default_factory=list)
    final_metrics: dict[str, Any] | None = None


def _parse_json(x: Any) -> Any:
    if isinstance(x, str):
        s = x.strip()
        if s.startswith("{"):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                return x
    if isinstance(x, list) and len(x) == 1 and isinstance(x[0], dict) and "text" in x[0]:
        return _parse_json(x[0]["text"])
    return x


def _iter_steps(traj: dict):
    for st in traj.get("steps", []):
        yield st
    for sub in traj.get("subagent_trajectories", []) or []:
        yield from _iter_steps(sub)


def parse_trace(path_or_dict: str | dict) -> ParsedTrace:
    traj = path_or_dict
    if isinstance(path_or_dict, str):
        with open(path_or_dict, encoding="utf-8") as f:
            traj = json.load(f)
    out = ParsedTrace(final_metrics=traj.get("final_metrics"))
    pending: dict[str, list[ToolEvent]] = {}
    for st in _iter_steps(traj):
        if st.get("source") == "user" and isinstance(st.get("message"), str):
            out.user_messages.append(st["message"])
        for tc in st.get("tool_calls", []) or []:
            ev = ToolEvent(len(out.events), tc.get("function_name", ""), tc.get("arguments") or {},
                           author=(tc.get("extra") or {}).get("author"))
            out.events.append(ev)
            pending.setdefault(ev.name, []).append(ev)
        obs = st.get("observation")
        if obs is not None:
            name = (obs.get("extra") or {}).get("tool_name")
            q = pending.get(name) or []
            if q:
                q.pop(0).result = _parse_json(obs.get("content"))
    return out
