"""Scripted OpenAI-compatible chat server for CPU-only end-to-end tests of the harness.

Each request replays the next scripted step, chosen by how many tool results
the conversation already holds. The script deliberately produces one repeated
call, one hallucinated tool, one failed edit and one submit_patch, so every
common metric gets a known non-zero value. No model weights involved.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


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


class _Handler(BaseHTTPRequestHandler):
    script: list[dict] = []
    log: list[dict] = []

    def log_message(self, *a):  # silence
        pass

    def do_GET(self):  # /v1/models
        body = json.dumps({"object": "list", "data": [{"id": "mock", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        msgs = req.get("messages", [])
        step = sum(1 for m in msgs if m.get("role") == "tool")
        first_user = next((m.get("content") for m in msgs if m.get("role") == "user"), "")
        if isinstance(first_user, list):
            first_user = " ".join(str(x.get("text", "")) for x in first_user if isinstance(x, dict))
        _Handler.log.append({"step": step, "n_msgs": len(msgs), "stream": bool(req.get("stream")),
                             "has_hint": "## Location hints" in str(first_user),
                             "tools": sorted(t.get("function", {}).get("name", "") for t in req.get("tools", []) or []),
                             "max_tokens": req.get("max_tokens") or req.get("max_completion_tokens"),
                             "extra": {k: req[k] for k in ("chat_template_kwargs", "thinking_token_budget", "temperature", "top_p") if k in req}})
        item = self.script[step] if step < len(self.script) else None
        cid = "call_" + uuid.uuid4().hex[:8]
        if item is None:
            message = {"role": "assistant", "content": "Done."}
            finish = "stop"
        else:
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": cid, "type": "function", "function": {"name": item["name"], "arguments": json.dumps(item["arguments"])}}]}
            finish = "tool_calls"
        usage = {"prompt_tokens": 100 + 10 * len(msgs), "completion_tokens": 20, "total_tokens": 120 + 10 * len(msgs)}
        if req.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            delta = dict(message)
            if "tool_calls" in delta and delta["tool_calls"]:
                delta["tool_calls"] = [dict(delta["tool_calls"][0], index=0)]
            chunks = [{"choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                      {"choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": usage}]
            for c in chunks:
                c.update({"id": "chatcmpl-x", "object": "chat.completion.chunk", "created": int(time.time()), "model": "mock"})
                self.wfile.write(f"data: {json.dumps(c)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")
            return
        body = json.dumps({"id": "chatcmpl-x", "object": "chat.completion", "created": int(time.time()), "model": "mock",
                           "choices": [{"index": 0, "message": message, "finish_reason": finish}], "usage": usage}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(script: list[dict], port: int = 8001) -> ThreadingHTTPServer:
    _Handler.script = script
    _Handler.log = []
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
