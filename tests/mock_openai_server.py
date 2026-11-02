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

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except ConnectionAbortedError:
            self.close_connection = True

    # --- freeze simulation (MOCK_FREEZE_AFTER=N): after N POSTs the server hangs on every request,
    # including GET /health, like a vLLM API server whose event loop is stuck in the tool parser.
    frozen = threading.Event()
    stopped = threading.Event()
    posts = 0
    conns: set = set()

    def setup(self):
        super().setup()
        _Handler.conns.add(self.connection)

    def _maybe_freeze(self, is_post: bool) -> None:
        if is_post:
            with _Handler.lock:
                _Handler.posts += 1
                n = int(os.environ.get("MOCK_FREEZE_AFTER", "0") or 0)
                if n and _Handler.posts > n:
                    _Handler.frozen.set()
        if _Handler.frozen.is_set():
            _Handler.stopped.wait()  # hang until the server is killed ...
            self.close_connection = True
            raise ConnectionAbortedError("mock server killed")  # ... then drop the request unanswered, like a dead process

    def _send(self, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # /v1/models and /health
        self._maybe_freeze(False)
        if self.path.rstrip("/").endswith("/health"):
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send({"object": "list", "data": [{"id": "mock", "object": "model"}]})

    def _conv_id(self, msgs: list[dict]) -> str:
        for m in msgs:
            hit = _CONV.search(_text(m))
            if hit:
                return hit.group(1)
        first_user = next((_text(m) for m in msgs if m.get("role") == "user"), "")
        return hashlib.sha1(first_user.encode()).hexdigest()[:10]

    def _render(self, msgs: list[dict], gen: bool) -> str:
        """Fake chat template with the prefix property of real ones: gen prompt == start of an assistant turn."""
        out = ""
        for m in msgs:
            out += f"<{m.get('role')}>" + _text(m) + json.dumps(m.get("tool_calls") or "") + f"</{m.get('role')}>"
        if gen:
            out += "<assistant>"
        return out

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        self._maybe_freeze(True)
        if self.path.rstrip("/").endswith("/tokenize"):  # vLLM /tokenize (chat form)
            text = self._render(req.get("messages", []), bool(req.get("add_generation_prompt")))
            toks = [ord(c) for c in text]
            return self._send({"tokens": toks, "count": len(toks), "max_model_len": 32768})
        if self.path.rstrip("/").endswith("/v1/completions"):  # prompt_logprobs scoring
            prompt = req.get("prompt") or []
            pl = [None] + [{str(t): {"logprob": -0.1 - (t % 7) / 10, "rank": 1, "decoded_token": ""}} for t in prompt[1:]]
            return self._send({"id": "cmpl-x", "object": "text_completion", "model": "mock",
                               "choices": [{"index": 0, "text": "", "prompt_logprobs": pl, "finish_reason": "length"}],
                               "usage": {"prompt_tokens": len(prompt), "completion_tokens": 1}})
        msgs = req.get("messages", [])
        tools = req.get("tools") or []
        conv = self._conv_id(msgs)
        big_from = int(os.environ.get("MOCK_BIG_USAGE_FROM_STEP", "2"))
        first_user = next((_text(m) for m in msgs if m.get("role") == "user"), "")
        if not tools:  # ADK summarizer (compaction) request
            _Handler.log.append({"conv": conv, "summarizer": True, "n_msgs": len(msgs)})
            text = f"[conv={conv}] Summary: the agent read files and tried an edit."
            if os.environ.get("MOCK_SUMMARY_ECHO"):  # like a summarizer that re-states the task under its header
                hist = " ".join(_text(m) for m in msgs)
                k = hist.find("Problem Statement:")
                if k >= 0:
                    text += " " + hist[k:k + 300]
            return self._send({"id": "chatcmpl-x", "object": "chat.completion", "created": int(time.time()), "model": "mock",
                               "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                            "finish_reason": "stop"}],
                               "usage": {"prompt_tokens": 500, "completion_tokens": 20, "total_tokens": 520}})
        with _Handler.lock:
            step = _Handler.steps.get(conv, 0)
            _Handler.steps[conv] = step + 1
        cwe_at = int(os.environ.get("MOCK_CWE_AT_STEP", "0") or 0)
        if cwe_at and step >= cwe_at and int(conv, 16) % 3 == 0:  # vLLM's context-length rejection for 1 in 3 conversations
            body = json.dumps({"object": "error", "type": "BadRequestError", "code": 400, "param": "input_tokens",
                               "message": "This model's maximum context length is 32768 tokens. However, you requested "
                                          "8192 output tokens and your prompt contains 25000 input tokens, for a total of "
                                          "33192 tokens (25000 + 8192 = 33192 > 32768)."}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        _Handler.log.append({"conv": conv, "step": step, "n_msgs": len(msgs), "stream": bool(req.get("stream")),
                             "has_hint": "## Location hints" in first_user,
                             "n_tool_msgs": sum(1 for m in msgs if m.get("role") == "tool"),
                             "tools": sorted(t.get("function", {}).get("name", "") for t in tools),
                             "max_tokens": req.get("max_tokens") or req.get("max_completion_tokens"),
                             "extra": {k: req[k] for k in ("chat_template_kwargs", "thinking_token_budget", "temperature", "top_p") if k in req}})
        item = self.script[step] if step < len(self.script) else None
        if os.environ.get("MOCK_PROBE"):  # probe dry runs: S-use -> a real (trivial) edit of the file just read
            last = msgs[-1] if msgs else {}
            rd = None
            if last.get("role") == "tool":
                try:
                    v = json.loads(_text(last))
                    v = json.loads(v["result"]) if isinstance(v, dict) and isinstance(v.get("result"), str) else v
                    rd = v if isinstance(v, dict) and "content" in v and "filepath" in v else None
                except (ValueError, TypeError, KeyError):
                    rd = None
            if rd and rd["content"].strip():
                first = next(l for l in rd["content"].splitlines() if l.strip())
                item = {"name": "edit_file", "arguments": {"filepath": rd["filepath"], "old_string": first,
                                                           "new_string": first + "  # mock edit"}}
            else:
                item = {"name": "read_file", "arguments": {"filepath": "README.md"}}
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
        k = max(1, int(req.get("n") or 1))
        self._send({"id": "chatcmpl-x", "object": "chat.completion", "created": int(time.time()), "model": "mock",
                    "choices": [{"index": i, "message": message, "finish_reason": finish} for i in range(k)], "usage": usage})


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


def serve(script: list[dict], port: int = 8001) -> ThreadingHTTPServer:
    _Handler.script = script
    _Handler.log = []
    _Handler.steps = {}
    _Handler.posts = 0
    _Handler.frozen = threading.Event()
    _Handler.stopped = threading.Event()
    _Handler.conns = set()
    srv = _Server(("127.0.0.1", port), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def kill(srv: ThreadingHTTPServer) -> None:
    """Like killing the vLLM process: stop accepting, release hung handlers, drop every client connection."""
    import socket
    _Handler.stopped.set()
    srv.shutdown()
    for c in list(_Handler.conns):
        try:
            c.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
    srv.server_close()
