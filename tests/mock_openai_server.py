"""Scripted OpenAI-compatible chat server for CPU-only end-to-end tests of the harness.

Each conversation replays the scripted steps in order. The step counter lives server-side, keyed by
a conversation id, so it survives ADK compaction (which removes old tool messages). The script
deliberately produces one repeated call, one hallucinated tool, one failed edit and one
submit_patch, so every common metric gets a known non-zero value.

Compaction: from step MOCK_BIG_USAGE_FROM_STEP on (default 2) the mock reports prompt_tokens=15000
(> the scorer's 14,336 threshold), so ADK's real token-threshold compaction fires. Requests without
tools are summarizer calls; they get a text summary carrying the conversation id.
No model weights involved.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_CONV = re.compile(r"\[conv=([0-9a-f]{10})\]")


def make_script(gold_file: str, good_edit: tuple[str, str] | None = None) -> list[dict]:
    extra = [{"name": "edit_file", "arguments": {"filepath": gold_file, "old_string": good_edit[0], "new_string": good_edit[1]}}] \
        if good_edit else []
    return extra + [
        {"name": "read_file", "arguments": {"filepath": gold_file, "start_line": 1, "end_line": 20}},
        {"name": "read_file", "arguments": {"filepath": gold_file, "start_line": 1, "end_line": 20}},  # repeat
        {"name": "open_file_now", "arguments": {"path": gold_file}},  # hallucinated tool
        {"name": "edit_file", "arguments": {"filepath": gold_file, "old_string": "NO SUCH TEXT 123", "new_string": "x"}},
        {"name": "run_command", "arguments": {"command": f"head -3 {gold_file}"}},
        {"name": "submit_patch", "arguments": {}},
        None,  # final text
    ]


def _text(m: dict) -> str:
    c = m.get("content")
    if isinstance(c, list):
        return " ".join(str(x.get("text", "")) for x in c if isinstance(x, dict))
    return str(c or "")


class _Handler(BaseHTTPRequestHandler):
    script: list[dict] = []
    log: list[dict] = []
    steps: dict[str, int] = {}
    lock = threading.Lock()

    def log_message(self, *a):  # silence
        pass

    def _send(self, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # /v1/models
        self._send({"object": "list", "data": [{"id": "mock", "object": "model"}]})

    def _conv_id(self, msgs: list[dict]) -> str:
        for m in msgs:
            hit = _CONV.search(_text(m))
            if hit:
                return hit.group(1)
        first_user = next((_text(m) for m in msgs if m.get("role") == "user"), "")
        return hashlib.sha1(first_user.encode()).hexdigest()[:10]

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        msgs = req.get("messages", [])
        tools = req.get("tools") or []
        conv = self._conv_id(msgs)
        big_from = int(os.environ.get("MOCK_BIG_USAGE_FROM_STEP", "2"))
        first_user = next((_text(m) for m in msgs if m.get("role") == "user"), "")
        if not tools:  # ADK summarizer (compaction) request
            _Handler.log.append({"conv": conv, "summarizer": True, "n_msgs": len(msgs)})
            return self._send({"id": "chatcmpl-x", "object": "chat.completion", "created": int(time.time()), "model": "mock",
                               "choices": [{"index": 0, "message": {"role": "assistant", "content": f"[conv={conv}] Summary: the agent read files and tried an edit."},
                                            "finish_reason": "stop"}],
                               "usage": {"prompt_tokens": 500, "completion_tokens": 20, "total_tokens": 520}})
        with _Handler.lock:
            step = _Handler.steps.get(conv, 0)
            _Handler.steps[conv] = step + 1
        _Handler.log.append({"conv": conv, "step": step, "n_msgs": len(msgs), "stream": bool(req.get("stream")),
                             "has_hint": "## Location hints" in first_user,
                             "n_tool_msgs": sum(1 for m in msgs if m.get("role") == "tool"),
                             "tools": sorted(t.get("function", {}).get("name", "") for t in tools),
                             "max_tokens": req.get("max_tokens") or req.get("max_completion_tokens"),
                             "extra": {k: req[k] for k in ("chat_template_kwargs", "thinking_token_budget", "temperature", "top_p") if k in req}})
        item = self.script[step] if step < len(self.script) else None
        if item is None:
            message, finish = {"role": "assistant", "content": "Done."}, "stop"
        else:
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_" + uuid.uuid4().hex[:8], "type": "function",
                 "function": {"name": item["name"], "arguments": json.dumps(item["arguments"])}}]}
            finish = "tool_calls"
        pt = 15000 if step >= big_from else 100 + 10 * len(msgs)
        usage = {"prompt_tokens": pt, "completion_tokens": 20, "total_tokens": pt + 20}
        if req.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            delta = dict(message)
            if delta.get("tool_calls"):
                delta["tool_calls"] = [dict(delta["tool_calls"][0], index=0)]
            for c in ({"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                      {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": usage}):
                c.update({"id": "chatcmpl-x", "object": "chat.completion.chunk", "created": int(time.time()), "model": "mock"})
                self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return
        self._send({"id": "chatcmpl-x", "object": "chat.completion", "created": int(time.time()), "model": "mock",
                    "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage})


def serve(script: list[dict], port: int = 8001) -> ThreadingHTTPServer:
    _Handler.script = script
    _Handler.log = []
    _Handler.steps = {}
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
