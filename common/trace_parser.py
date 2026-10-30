"""Parse swegemma ATIF v1.7 trace files into a flat list of tool events.

swegemma writes results_dir/traces/trace_<instance_id>.json via
SessionTrace.save(format="atif"). In that format a step can hold several
tool_calls but only one observation; extra responses become separate
"system" steps. So we flatten all calls and all responses in order and pair
the k-th call of tool X with the k-th response of tool X.

Calls made inside an AgentTool sub-agent run in a separate ADK runner and do
NOT appear in the root trace (they still count in swegemma's tool_calls_used).
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# A model emitting the raw Gemma tool-call token in text means the vLLM
# parser could not turn it into a call (typically truncated or malformed).
RAW_TOOL_CALL_MARKERS = ("<|tool_call>", "<|tool_call|>", "<tool_call>")


@dataclass
class ToolEvent:
    index: int
    name: str
    args: dict[str, Any]
    response: dict[str, Any] | None
    elapsed_s: float | None
    author: str | None = None

    @property
    def key(self) -> str:
        """Identity used for the repeated-call metric (same tool + same args)."""
        return self.name + "|" + json.dumps(self.args, sort_keys=True, default=str)

    @property
    def ok(self) -> bool:
        return not is_error(self.response)

    @property
    def error_type(self) -> str | None:
        r = self.response or {}
        return r.get("error_type") or r.get("error_code") if is_error(r) else None


@dataclass
class ParsedTrace:
    instance_id: str | None
    events: list[ToolEvent] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    n_thinking: int = 0
    n_compactions: int = 0
    duration_s: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def raw_tool_call_texts(self) -> int:
        return sum(any(m in t for m in RAW_TOOL_CALL_MARKERS) for t in self.texts)


def _parse_json_maybe(x: Any) -> Any:
    if isinstance(x, str):
        try:
            return json.loads(x)
        except (json.JSONDecodeError, TypeError):
            return {"raw": x}
    return x


def _normalise_response(content: Any) -> dict[str, Any] | None:
    r = _parse_json_maybe(content)
    if isinstance(r, list):  # ATIF allows list-of-parts content
        r = {"parts": r}
    if not isinstance(r, dict):
        return {"raw": r}
    # Some tools return a JSON string nested one level deeper.
    if set(r) == {"result"} or set(r) == {"raw"}:
        inner = _parse_json_maybe(next(iter(r.values())))
        if isinstance(inner, dict):
            r = inner
    return r


def is_error(resp: dict[str, Any] | None) -> bool:
    if not resp:
        return False
    if resp.get("status") == "error":
        return True
    # ADK skill tools return {"error": ..., "error_code": ...} without status.
    if "error_code" in resp or ("error" in resp and "status" not in resp):
        return True
    return False


def parse_trace_dict(data: dict[str, Any], instance_id: str | None = None) -> ParsedTrace:
    pt = ParsedTrace(instance_id=instance_id)
    calls: list[tuple[str, dict, float | None, str | None]] = []
    responses: dict[str, list[dict | None]] = defaultdict(list)
    last_elapsed = 0.0

    for step in data.get("steps", []):
        extra = step.get("extra") or {}
        ev = extra.get("event_type")
        if isinstance(extra.get("elapsed_s"), (int, float)):
            last_elapsed = max(last_elapsed, float(extra["elapsed_s"]))
        metrics = step.get("metrics") or {}
        pt.prompt_tokens += int(metrics.get("prompt_tokens", 0) or 0)
        pt.completion_tokens += int(metrics.get("completion_tokens", 0) or 0)

        for tc in step.get("tool_calls") or []:
            tce = tc.get("extra") or {}
            calls.append((
                tc.get("function_name", ""),
                tc.get("arguments") or {},
                tce.get("elapsed_s"),
                tce.get("author"),
            ))
        obs = step.get("observation")
        if obs is not None:
            name = (obs.get("extra") or {}).get("tool_name", "")
            responses[name].append(_normalise_response(obs.get("content")))

        if ev == "thinking":
            pt.n_thinking += 1
        elif ev == "compaction":
            pt.n_compactions += 1
        elif ev in ("text", "final") and step.get("source") == "agent":
            msg = step.get("message")
            pt.texts.append(msg if isinstance(msg, str) else json.dumps(msg, default=str))

    used: dict[str, int] = defaultdict(int)
    for i, (name, args, el, author) in enumerate(calls):
        k = used[name]
        resp = responses[name][k] if k < len(responses[name]) else None
        used[name] += 1
        pt.events.append(ToolEvent(i, name, args, resp, el, author))

    fm = data.get("final_metrics") or {}
    pt.duration_s = fm.get("duration_s") or fm.get("total_duration_s") or (last_elapsed or None)
    return pt


def parse_trace_file(path: str | Path) -> ParsedTrace:
    p = Path(path)
    iid = p.stem[len("trace_"):] if p.stem.startswith("trace_") else p.stem
    with open(p, encoding="utf-8") as f:
        return parse_trace_dict(json.load(f), instance_id=iid.replace("__", "/"))
