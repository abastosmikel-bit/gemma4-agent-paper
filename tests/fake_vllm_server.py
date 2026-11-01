"""LOCAL-ONLY stand-in for a vLLM OpenAI server process tree (used by tests/test_server_shutdown.py).

Like vLLM: an API-server process that serves /health and /v1/models, plus an "EngineCore" child and 4 "GPU worker"
grandchildren. Every process ignores SIGTERM, which reproduces the Kaggle failure where VllmServer.stop() killed only
the API server and the workers kept their GPU memory. Writes all PIDs to the file given as argv[2].
usage: python fake_vllm_server.py <port> <pidfile>
"""
import json
import multiprocessing as mp
import os
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


def stubborn_sleep():
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(1)


def engine(pid_q):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    ctx = mp.get_context("spawn")
    workers = [ctx.Process(target=stubborn_sleep, daemon=False) for _ in range(4)]
    for w in workers:
        w.start()
    pid_q.put([os.getpid()] + [w.pid for w in workers])
    stubborn_sleep()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"object": "list", "data": [{"id": "fake", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    port, pidfile = int(sys.argv[1]), sys.argv[2]
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    eng = ctx.Process(target=engine, args=(q,), daemon=False)
    eng.start()
    pids = [os.getpid()] + q.get(timeout=60)
    open(pidfile, "w").write(json.dumps(pids))
    print("fake vLLM API server ready", flush=True)
    HTTPServer(("127.0.0.1", port), H).serve_forever()
