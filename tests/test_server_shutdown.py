"""LOCAL-ONLY tests of inference-server shutdown with the real adk_submission.VllmServer (no GPU, no vLLM).

A fake vLLM process tree (tests/fake_vllm_server.py) ignores SIGTERM in every process, like the Kaggle C03 run where
VllmServer.stop() killed only the API server and the tensor-parallel workers kept ~20 GiB on each GPU.
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
psutil = pytest.importorskip("psutil")
ads = pytest.importorskip("adk_submission.server")


def _server(port: int, pidfile: str):
    from adk_submission import VllmConfig, VllmServer
    srv = VllmServer(VllmConfig(model="fake", port=port, host="127.0.0.1", startup_timeout=60))
    srv.build_cmd = lambda: [sys.executable, str(ROOT / "tests" / "fake_vllm_server.py"), str(port), pidfile]
    return srv


def _alive(pids):
    return [p for p in pids if psutil.pid_exists(p) and psutil.Process(p).status() != psutil.STATUS_ZOMBIE]


def _start(srv, pidfile):
    srv.start()
    for _ in range(100):
        if os.path.exists(pidfile) and os.path.getsize(pidfile):
            return json.loads(open(pidfile).read())
        time.sleep(0.1)
    raise AssertionError("fake server did not report its PIDs")


def test_old_stop_leaks_workers():
    import subprocess
    ads.subprocess = subprocess  # the library's own behaviour (no process group of its own)
    pidfile = tempfile.mktemp()
    srv = _server(8131, pidfile)
    pids = _start(srv, pidfile)
    assert len(pids) == 6  # API server + EngineCore + 4 workers
    srv.stop(timeout=2)
    time.sleep(1)
    leaked = _alive(pids)
    for p in leaked:  # clean up what the library left behind
        psutil.Process(p).kill()
    assert len(leaked) == 5, f"expected the 5 child processes to survive VllmServer.stop(), got {len(leaked)}"


def test_group_stop_kills_everything():
    from pilot_c import kaggle_runner as kr
    kr._own_process_group()
    pidfile = tempfile.mktemp()
    srv = _server(8132, pidfile)
    pids = _start(srv, pidfile)
    assert os.getpgid(pids[0]) != os.getpgrp()  # the server has its own process group
    t0 = time.time()
    info = kr.stop_server(srv, tag="fake", timeout=2)
    assert not _alive(pids), f"survivors: {_alive(pids)}"
    assert info["group_killed"] and info["survivors"] == 0 and time.time() - t0 < 30


def test_wait_gpu_free(monkeypatch):
    from pilot_c import kaggle_runner as kr
    readings = iter([[(1567, 23034)] * 4, [(9000, 23034)] * 4, [(22400, 23034)] * 4])
    monkeypatch.setattr(kr, "gpu_memory", lambda: next(readings))
    r = kr.wait_gpu_free(0.92, timeout_s=10, poll_s=0.01)
    assert r["checked"] and min(r["free_gib"]) > 21
    monkeypatch.setattr(kr, "gpu_memory", lambda: [(1567, 23034)] * 4)
    with pytest.raises(kr.GpuMemoryNotReleased, match="not released"):
        kr.wait_gpu_free(0.92, timeout_s=0.05, poll_s=0.01)
    monkeypatch.setattr(kr, "gpu_memory", lambda: None)  # no GPU (dry runs): no-op
    assert kr.wait_gpu_free(0.92) == {"checked": False}
