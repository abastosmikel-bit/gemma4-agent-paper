"""Freeze protection for a local OpenAI-compatible inference server (vLLM) during GPU notebooks.

Why: a main-track forum report says the gemma4 tool parser can loop forever on an array tool argument
(in the harness tool set the only one is `get_code_subgraph(nodes: list[str])`) and freeze the server
for the rest of the run. Without protection a freeze burns L4x4 time until the session limit: LiteLLM's
default request timeout is 6000 s, and adk-eval-core's ModelRetryPlugin retries timeouts up to 5 times.

Three layers, used by every GPU notebook:
  1. per-request timeouts (set by the callers: runtime_probes for agent requests, probe_runner for probes);
  2. `Watchdog`: a thread polling GET /health; after `max_fail` consecutive failures, or when requests
     are in flight but none has finished for `stall_s`, it trips: it sets TRIPPED and kills the server;
  3. `tracked()`: wraps every request; once TRIPPED is set, new and retried requests fail immediately with
     ServerFrozen (an adk-eval-core EvalCoreError when available, which its retry plugin does not retry).
The notebook loop then restarts the server for the next unit of work, and stops the session after a
second freeze.
"""
from __future__ import annotations

import contextlib
import os
import threading
import time
import urllib.request
from typing import Any, Callable

try:  # non-retryable for adk-eval-core's ModelRetryPlugin
    from adk_eval_core.errors import EvalCoreError as _Base
except Exception:  # noqa: BLE001
    _Base = RuntimeError


class ServerFrozen(_Base):
    """The inference server stopped responding and was killed by the watchdog."""


TRIPPED = threading.Event()
STATE: dict[str, Any] = {"reason": None, "t": None}
_LOCK = threading.Lock()
TRACK: dict[str, Any] = {"inflight": 0, "started": 0, "done": 0, "last_done": time.time()}
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def reset() -> None:
    TRIPPED.clear()
    STATE.update({"reason": None, "t": None})
    with _LOCK:
        TRACK.update({"inflight": 0, "started": 0, "done": 0, "last_done": time.time()})


@contextlib.contextmanager
def tracked():
    """Wrap one request to the inference server: counts it, and fails fast after a freeze."""
    if TRIPPED.is_set():
        raise ServerFrozen(f"inference server frozen ({STATE['reason']}); request not sent")
    with _LOCK:
        TRACK["inflight"] += 1
        TRACK["started"] += 1
    try:
        yield
    except Exception as e:  # noqa: BLE001
        if TRIPPED.is_set() and not isinstance(e, ServerFrozen):
            raise ServerFrozen(f"inference server frozen ({STATE['reason']}): {type(e).__name__}") from e
        raise
    finally:
        with _LOCK:
            TRACK["inflight"] -= 1
            TRACK["done"] += 1
            TRACK["last_done"] = time.time()


def _env(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


class Watchdog(threading.Thread):
    def __init__(self, root_url: str, kill: Callable[[], None], interval: float | None = None,
                 health_timeout: float | None = None, max_fail: int | None = None, stall_s: float | None = None,
                 log: Callable[[str], None] = print):
        super().__init__(daemon=True)
        self.root = root_url.rstrip("/")
        self.root = self.root[:-3] if self.root.endswith("/v1") else self.root
        self.kill = kill
        # defaults: a freeze is detected within ~90 s; overridable for dry runs
        self.interval = interval if interval is not None else _env("PILOT_WD_INTERVAL", 30)
        self.health_timeout = health_timeout if health_timeout is not None else _env("PILOT_WD_HEALTH_TIMEOUT", 10)
        self.max_fail = int(max_fail if max_fail is not None else _env("PILOT_WD_MAX_FAIL", 3))
        self.stall_s = stall_s if stall_s is not None else _env("PILOT_WD_STALL_S", 1200)
        self.log = log
        self._halt = threading.Event()  # not `_stop`: that name is a threading.Thread internal
        self.checks = 0

    def healthy(self) -> bool:
        try:
            with _OPENER.open(f"{self.root}/health", timeout=self.health_timeout) as r:
                return 200 <= r.status < 300
        except Exception:  # noqa: BLE001
            return False

    def run(self) -> None:
        fails = 0
        while not self._halt.wait(self.interval):
            self.checks += 1
            fails = 0 if self.healthy() else fails + 1
            with _LOCK:
                stalled = TRACK["inflight"] > 0 and time.time() - TRACK["last_done"] > self.stall_s
            if fails >= self.max_fail or stalled:
                self.trip("health check failed %d times" % fails if fails >= self.max_fail
                          else "no request finished for %.0f s" % self.stall_s)
                return

    def trip(self, reason: str) -> None:
        STATE.update({"reason": reason, "t": time.time()})
        TRIPPED.set()
        self.log(f"WATCHDOG: inference server considered frozen ({reason}); killing it")
        killer = threading.Thread(target=self._kill, daemon=True)
        killer.start()
        killer.join(60)

    def _kill(self) -> None:
        try:
            self.kill()
        except Exception as e:  # noqa: BLE001
            self.log(f"WATCHDOG: kill raised {type(e).__name__}: {e}")

    def stop(self) -> None:
        self._halt.set()


def state() -> dict[str, Any]:
    with _LOCK:
        return {"tripped": TRIPPED.is_set(), **STATE, **{k: v for k, v in TRACK.items() if k != "last_done"}}
