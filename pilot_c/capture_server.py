"""Capture server: an OpenAI-compatible stand-in LLM that records the agent's exact requests.

Used by the probe (docs/PLAN.md §3) to obtain byte-identical agent contexts without a GPU:
the real swegemma agent loop runs against this server; for each task the server answers with a
scripted action sequence (read the gold span, then submit_patch, then stop) and stores the full
request bodies. Request 0 is the S-find context, request 1 the S-use context (it contains the real
harness read_file output). Summarizer (no-tools) requests get a short text reply.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _text(m: dict) -> str:
    c = m.get("content")
    if isinstance(c, list):
        return " ".join(str(x.get("text", "")) for x in c if isinstance(x, dict))
    return str(c or "")


class CaptureServer:
    def __init__(self, routes: dict[str, dict[str, Any]], port: int = 0):
        """routes: task_id -> {"needle": str found in the task prompt, "script": [ {name, arguments} | None ]}"""
        self.routes = routes
        self.captured: dict[str, list[dict]] = {k: [] for k in routes}
        self.unrouted = 0
        self.lock = threading.Lock()
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, obj: dict) -> None:
                b = json.dumps(obj).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                self._send({"object": "list", "data": [{"id": "capture", "object": "model"}]})

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                msgs = req.get("messages", [])
                now = int(time.time())
                if not req.get("tools"):
                    return self._send(_completion("Summary.", None, now))
                first_user = next((_text(m) for m in msgs if m.get("role") == "user"), "")
                tid = next((k for k, r in outer.routes.items() if r["needle"] and r["needle"] in first_user), None)
                if tid is None:
                    with outer.lock:
                        outer.unrouted += 1
                    return self._send(_completion("Done.", None, now))
                with outer.lock:
                    step = len(outer.captured[tid])
                    outer.captured[tid].append(req)
                script = outer.routes[tid]["script"]
                item = script[step] if step < len(script) else None
                if item is None:
                    return self._send(_completion("Done.", None, now))
                return self._send(_completion(None, item, now))

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), H)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def _completion(text: str | None, call: dict | None, now: int) -> dict:
    if call is None:
        msg, fin = {"role": "assistant", "content": text}, "stop"
    else:
        msg = {"role": "assistant", "content": None, "tool_calls": [{
            "id": "call_" + uuid.uuid4().hex[:10], "type": "function",
            "function": {"name": call["name"], "arguments": json.dumps(call["arguments"])}}]}
        fin = "tool_calls"
    return {"id": "chatcmpl-capture", "object": "chat.completion", "created": now, "model": "capture",
            "choices": [{"index": 0, "message": msg, "finish_reason": fin}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110}}


def needle_for(problem_statement: str) -> str:
    """A short, distinctive substring of the problem statement as the harness inserts it."""
    ps = problem_statement.strip()
    return ps[:120] if len(ps) >= 20 else hashlib.sha1(ps.encode()).hexdigest()
