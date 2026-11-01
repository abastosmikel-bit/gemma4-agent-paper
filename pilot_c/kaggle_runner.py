"""Kaggle-side runner for Pilot C (imported by the notebooks; runs only on Kaggle).

Reproduces the official starter's evaluation path (swegemma Evaluator, subprocess
sandbox, vLLM with max_model_len=32768, tool/reasoning parser gemma4, the same
compaction and context-cache settings as the scorer per HARNESS_README §7.2) and
changes only: model alias, per-task budget (eval_config.yaml), task copies with
oracle hints, results dir, concurrency.

Outputs:
  /kaggle/working/private/...         raw runs (patches, traces) - NEVER commit
  /kaggle/working/C0x_<what>.json      numbers only - commit to results/ (names: notebooks/README.md)
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import datetime as _dt
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from common.metrics import aggregate, paired_flips, task_metrics  # noqa: E402
from common.tasks import diff_scopes, gold_locations, load_tasks  # noqa: E402
from common import runtime_probes as rp  # noqa: E402
from common.trace import load_trace  # noqa: E402
from pilot_c.hints import _HEADER as HINT_HEADER, rewrite_task  # noqa: E402

WORK = Path(os.environ.get("PILOT_WORK_DIR", "/kaggle/working"))
PRIVATE = WORK / "private"
ALLOWED = ("gemma-4-31b-it-qat-w4a16-ct", "gemma-4-12b-it-qat-w4a16-ct",
           "gemma-4-e4b-it-qat-w4a16-ct", "gemma-4-e2b-it-qat-w4a16-ct")
SHORT = {m: m.split("-")[2] for m in ALLOWED}  # 31b / 12b / e4b / e2b
MODEL_VLLM_EXTRA_ARGS = {
    "gemma-4-12b-it-qat-w4a16-ct": ("--hf-overrides", '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}'),
}
GPU_ONLY_WHEELS = ("vllm", "flashinfer", "bitsandbytes", "xgrammar", "nvidia_", "quack_kernels", "apache_tvm_ffi")


def _first_dir(*cands: str) -> Path:
    for c in cands:
        for p in sorted(glob.glob(c)):
            if Path(p).is_dir():
                return Path(p)
    raise FileNotFoundError(f"none of {cands} found")


def data_dir() -> Path:
    if os.environ.get("PILOT_DATA_DIR"):  # local testing only
        return Path(os.environ["PILOT_DATA_DIR"])
    return _first_dir("/kaggle/input/competitions/gemma-4-developer-agent", "/kaggle/input/gemma-4-developer-agent")


def wheelhouse_dir() -> Path:
    return _first_dir("/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse",
                      "/kaggle/input/gemma-4-developer-agent-wheelhouse")


def set_env() -> None:
    """Same environment variables as the official starter notebook."""
    env = {
        "TRANSFORMERS_NO_TF": "1", "TRANSFORMERS_NO_FLAX": "1", "TRANSFORMERS_OFFLINE": "1",
        "VLLM_NO_USAGE_STATS": "1", "VLLM_WORKER_MULTIPROC_METHOD": "spawn", "VLLM_ENGINE_READY_TIMEOUT_S": "1200",
        "VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS": "1", "NCCL_DEBUG": "WARN", "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "LITELLM_TELEMETRY": "False", "LITELLM_LOG": "WARNING", "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
        "OTEL_SDK_DISABLED": "true", "OTEL_PYTHON_DISABLED": "true",
    }
    os.environ.update(env)
    os.environ.setdefault("KAGGLE_SANDBOX_DIR", str(data_dir() / "sandbox"))
    os.environ.setdefault("OPENAI_API_KEY", "EMPTY")
    os.environ.setdefault("LOCAL_API_KEY", "EMPTY")


EXPECTED_PYTHON = (3, 12)  # the official starter's pinned Kaggle environment; the wheelhouse is built for cp312
# Wheelhouse wheels the CPU notebooks need (gold check, test verification). Found by running that code path and
# recording every imported distribution: of 90, only these 5 come from the wheelhouse; all are pure Python
# (py3-none-any). Everything else is provided by the Kaggle image. The other 36 wheels serve the model (vLLM stack).
CPU_WHEELS = ("swegemma", "adk_eval_core", "adk_submission", "google_adk", "google_genai")


def _dist_of(wheel_name: str) -> str:
    return re.sub(r"[-_.]+", "_", wheel_name.split("-")[0]).lower()


def _wheel_supported(wheel_name: str) -> bool:
    """True if the wheel's python tag fits this interpreter (pure-python, abi3 or the exact cpXY)."""
    parts = wheel_name[:-4].split("-")
    py, abi = parts[-3], parts[-2]
    here = f"cp{sys.version_info.major}{sys.version_info.minor}"
    if py.startswith("py") or "none" in abi and not py.startswith("cp"):
        return True
    if abi == "abi3":
        return any(int(t[3:] or 0) <= sys.version_info.minor for t in py.split(".") if t.startswith("cp3"))
    return here in py.split(".")


def install_wheelhouse(gpu: bool = True, only: tuple[str, ...] | None = None) -> None:
    """Starter-identical wheel install. gpu=False skips GPU-only wheels; `only` restricts to those distributions
    (the CPU notebooks pass CPU_WHEELS). Refuses, before calling pip, any wheel built for another Python."""
    import importlib
    for pat in ("/usr/local/lib/python*/dist-packages/*cutlass*.pth", "/usr/local/lib/python*/site-packages/*cutlass*.pth"):
        for pth in glob.glob(pat):
            try:
                os.unlink(pth)
            except OSError:
                pass
    tmp = Path("/tmp/wheelhouse")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    for w in wheelhouse_dir().glob("*.whl"):
        if "cutlass" in w.name.lower() or (not gpu and w.name.startswith(GPU_ONLY_WHEELS)):
            continue
        if only is not None and _dist_of(w.name) not in only:
            continue
        name = w.name.replace("cu128", "+cu128") if ("cu128" in w.name and "+" not in w.name) else w.name
        t = tmp / name
        if not t.exists():
            try:
                os.symlink(w, t)
            except OSError:
                shutil.copyfile(w, t)
    wheels = sorted(str(w) for w in tmp.glob("*.whl"))
    if only is not None:
        missing = sorted(set(only) - {_dist_of(Path(w).name) for w in wheels})
        if missing:
            raise RuntimeError(f"wheelhouse is missing {missing}; is the dataset metric/gemma-4-developer-agent-wheelhouse attached?")
    bad = [Path(w).name for w in wheels if not _wheel_supported(Path(w).name)]
    if bad:
        raise RuntimeError(f"Python {sys.version.split()[0]} cannot install {bad[:3]}... (wheelhouse is built for "
                           f"cp{EXPECTED_PYTHON[0]}{EXPECTED_PYTHON[1]}). Run this notebook in the official starter's "
                           "pinned environment: see the first cell of the notebook.")
    print(f"installing {len(wheels)} wheels: {', '.join(_dist_of(Path(w).name) for w in wheels)}")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "--force-reinstall", *wheels], check=True)
    importlib.invalidate_caches()


def quiet_logs() -> None:
    import logging
    for name in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "litellm", "httpx", "httpcore", "openai", "urllib3",
                 "opentelemetry", "opentelemetry.context"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        if "litellm" in name.lower():
            lg.propagate = False
            lg.handlers.clear()


def run_sync(fn, *args, **kwargs):
    """Run an async callable from a notebook (same helper as the starter)."""
    coro_fn = lambda: fn(*args, **kwargs)  # noqa: E731
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro_fn())).result()
    return asyncio.run(coro_fn())


def env_info() -> dict[str, Any]:
    info: dict[str, Any] = {"python": platform.python_version(), "nproc": os.cpu_count()}
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
        info["gpus"] = out
    except Exception:  # noqa: BLE001
        info["gpus"] = []
    try:
        import importlib.metadata as md
        info["versions"] = {p: md.version(p) for p in ("swegemma", "adk-eval-core", "adk-submission", "google-adk", "vllm")
                            if _has_dist(md, p)}
    except Exception:  # noqa: BLE001
        pass
    return info


def _has_dist(md, p: str) -> bool:
    try:
        md.version(p)
        return True
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- tasks & hints

def build_gold(task_ids: list[str]) -> dict[str, dict]:
    d = data_dir()
    tasks = {t["instance_id"]: t for t in load_tasks(d / "tasks.jsonl")}
    out = {}
    for iid in task_ids:
        out[iid] = gold_locations(tasks[iid], d / "snapshots" / f"{iid}.tgz").to_dict()
    return out


def write_task_copy(task_ids: list[str], gold: dict[str, dict], condition: str) -> Path:
    """Local hinted copy of tasks.jsonl for one condition (kept under PRIVATE)."""
    d = data_dir()
    tasks = {t["instance_id"]: t for t in load_tasks(d / "tasks.jsonl")}
    PRIVATE.mkdir(parents=True, exist_ok=True)
    path = PRIVATE / f"tasks_{condition}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for iid in task_ids:
            f.write(json.dumps(rewrite_task(tasks[iid], gold[iid], condition)) + "\n")
    return path


# --------------------------------------------------------------------------- agent & server

def prepare_agent_dir(model: str, budget: dict[str, Any]) -> Path:
    """Official sample_submission with the model alias swapped and the sample's dummy LoRA
    adapters removed for EVERY size (starter logic for non-31B; for 31B too, so all sizes run the
    plain base model), and eval_config.yaml replaced by the pilot budget."""
    assert model in ALLOWED, model
    src = data_dir() / "sample_submission"
    dst = WORK / f"agent_{SHORT[model]}"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    shutil.rmtree(dst / "adapters", ignore_errors=True)
    for y in [dst / "agent.yaml", *sorted((dst / "sub_agents").glob("*.yaml"))]:
        if y.is_file():
            txt = y.read_text(encoding="utf-8")
            txt = re.sub(r"^(\s*model:\s*).*$", rf"\g<1>{model}", txt, flags=re.M)
            txt = re.sub(r"^\s*adapter:\s*.*\n?", "", txt, flags=re.M)
            y.write_text(txt, encoding="utf-8")
    lines = ["evaluation:"] + [f"  {k}: {v}" for k, v in budget.items()]
    (dst / "eval_config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dst


def describe_agent(agent_dir: Path) -> dict[str, Any]:
    import yaml
    a = yaml.safe_load((agent_dir / "agent.yaml").read_text().replace("!include", "#include")) or {}
    samp = yaml.safe_load((agent_dir / "configs" / "sampling.yaml").read_text())
    tools = [t if isinstance(t, str) else "agent_tool:" + str(t.get("agent_tool", {}).get("config_path")) for t in a.get("tools", [])]
    return {"model": a.get("model"), "tools": tools, "sampling": samp,
            "eval_config": yaml.safe_load((agent_dir / "eval_config.yaml").read_text())}


class GpuMemoryNotReleased(RuntimeError):
    """GPU memory did not come back after a server was stopped; starting another server would fail."""


SERVER_LOG_DIR = PRIVATE / "server_logs"
LAST_SERVER_ERRORS: list[str] = []


def _own_process_group() -> None:
    """Make adk_submission start every inference server in its own session / process group.

    VllmServer.start() uses a plain Popen, so the server shares the notebook kernel's process group and
    VllmServer.stop() kills only the API-server PID: vLLM's EngineCore and its tensor-parallel worker
    processes survive and keep ~20 GiB on every GPU (Kaggle C03 run, 2026-10-31)."""
    import types
    import adk_submission.server as ads
    if getattr(ads.subprocess, "_pilot_own_group", False):
        return
    real = subprocess

    def popen(*args, **kwargs):
        kwargs.setdefault("start_new_session", True)
        return real.Popen(*args, **kwargs)

    shim = types.SimpleNamespace(**{n: getattr(real, n) for n in dir(real) if not n.startswith("__")})
    shim.Popen = popen
    shim._pilot_own_group = True
    ads.subprocess = shim


def gpu_memory() -> list[tuple[int, int]] | None:
    """(free MiB, total MiB) per GPU from nvidia-smi, or None when there is no GPU (dry runs)."""
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.free,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    return [tuple(int(float(x)) for x in line.split(",")[:2]) for line in out.stdout.strip().splitlines()]


def wait_gpu_free(need_frac: float, timeout_s: float = 300, poll_s: float = 5) -> dict[str, Any]:
    """Block until every GPU has at least need_frac of its memory free; raise GpuMemoryNotReleased on timeout."""
    t0 = time.time()
    while True:
        mem = gpu_memory()
        if mem is None:
            return {"checked": False}
        if all(free >= need_frac * total for free, total in mem):
            return {"checked": True, "waited_s": round(time.time() - t0, 1), "free_gib": [round(f / 1024, 2) for f, _ in mem]}
        if time.time() - t0 > timeout_s:
            raise GpuMemoryNotReleased(
                f"GPU memory not released {timeout_s:.0f}s after stopping the previous server: free "
                f"{[round(f / 1024, 2) for f, _ in mem]} GiB of {[round(t / 1024, 2) for _, t in mem]} GiB; the next "
                f"server needs {need_frac:.0%} free on every GPU. Stopping instead of starting another server.")
        time.sleep(poll_s)


def _save_server_log(server, tag: str) -> list[str]:
    """Keep the server log (VllmServer.stop() deletes it) under private/, return its error lines."""
    path = getattr(server, "log_path", None)
    if not path or not os.path.exists(path):
        return []
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    SERVER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    (SERVER_LOG_DIR / f"{tag}_{int(time.time())}.log").write_text("\n".join(lines[-2000:]), encoding="utf-8")
    errs = [l[:300] for l in lines if re.search(r"ERROR|Traceback|Error:|out of memory|OutOfMemory", l)]
    return errs[-20:]


def error_kinds(lines: list[str]) -> list[str]:
    """Exception class names only (safe to commit; the lines themselves stay private)."""
    return sorted({m for l in lines for m in re.findall(r"\b([A-Z][A-Za-z]+(?:Error|Exception))\b", l)})


def stop_server(server, tag: str = "server", timeout: float = 15.0) -> dict[str, Any]:
    """Stop an inference server and everything it spawned: SIGTERM, then SIGKILL, to its whole process group,
    plus any descendants recorded before the kill. Saves the server log first."""
    import signal
    global LAST_SERVER_ERRORS
    LAST_SERVER_ERRORS = _save_server_log(server, tag)
    info: dict[str, Any] = {"group_killed": False, "survivors": 0, "error_kinds": error_kinds(LAST_SERVER_ERRORS)}
    proc = getattr(server, "process", None)
    if proc is None:
        safe_stop(server)
        return info
    pid = proc.pid
    try:
        import psutil
        desc = psutil.Process(pid).children(recursive=True)
    except Exception:  # noqa: BLE001
        psutil, desc = None, []
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        pgid = None
    own = pgid is not None and pgid != os.getpgrp()
    try:
        if own:
            os.killpg(pgid, signal.SIGTERM)
        else:
            proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
        if own:
            try:
                os.killpg(pgid, signal.SIGKILL)
                info["group_killed"] = True
            except ProcessLookupError:
                pass
        elif proc.poll() is None:
            proc.kill()
        for d in desc:
            try:
                d.kill()
            except Exception:  # noqa: BLE001
                pass
        if psutil is not None and desc:
            _, alive = psutil.wait_procs(desc, timeout=15)
            info["survivors"] = len(alive)
        try:
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            pass
    finally:
        safe_stop(server)
    info["descendants"] = len(desc)
    return info


def start_server(agent_dir: Path, gpu_memory_utilization: float = 0.90, extra_args: tuple[str, ...] = ()):
    """Starter-identical vLLM launch (except optional memory settings for the probe), in its own process group.
    Waits until every GPU is free first. Returns (server, models, adapters, startup_seconds)."""
    if os.environ.get("PILOT_MOCK_LLM"):  # local papermill dry runs only (no GPU, scripted mock LLM)
        return _start_mock_server(agent_dir)
    import litellm
    import torch
    from adk_submission import VllmConfig, VllmServer, discover_adapters
    from adk_submission.discovery import discover_declared_models
    from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS

    _own_process_group()
    litellm.drop_params = True
    declared = discover_declared_models(agent_dir)
    assert len(declared) == 1, declared
    model = next(iter(declared))
    assert model in ALLOWED, model
    model_path = Path(f"/kaggle/input/models/google/gemma-4/other/{model}/2")
    if not model_path.exists():
        model_path = _first_dir(f"/kaggle/input/models/google/gemma-4/*/{model}/*", f"/kaggle/input/gemma-4/*/{model}/*")
    adapters = discover_adapters(str(agent_dir), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
    amap = getattr(adapters, "adapters", None) or {}
    ranks = [r for info in amap.values() if (r := getattr(info, "rank", None)) is not None and r > 0]
    n = torch.cuda.device_count() if torch.cuda.is_available() else 1
    tp = 4 if n >= 4 else (2 if n >= 2 else 1)
    waited = wait_gpu_free(gpu_memory_utilization + 0.02)
    cfg = VllmConfig(
        model=str(model_path), port=8000, host="127.0.0.1", tool_call_parser="gemma4", reasoning_parser="gemma4",
        max_model_len=32768, dtype="bfloat16" if (torch.cuda.is_available() and torch.cuda.is_bf16_supported()) else "auto",
        gpu_memory_utilization=gpu_memory_utilization, enable_auto_tool_choice=True, enable_lora=bool(amap),
        max_loras=max(1, len(amap)), max_lora_rank=max(ranks) if ranks else 128, scheduler_reserve_full_isl=False,
        tensor_parallel_size=tp, startup_timeout=60 * 20,
        extra_args=tuple(MODEL_VLLM_EXTRA_ARGS.get(model, ())) + tuple(extra_args),
    )
    t0 = time.perf_counter()
    server = VllmServer(cfg, adapter_manifest=adapters)
    try:
        server.start()
    except Exception:
        stop_server(server, tag=f"{SHORT[model]}_failed_start")  # also kills workers of a half-started server
        print("server log errors:", *LAST_SERVER_ERRORS[-8:], sep="\n  ")
        raise
    startup = time.perf_counter() - t0
    models = server.create_model_registry(aliases=[model], model_prefix="openai/", api_key=os.environ.get("LOCAL_API_KEY", "EMPTY"))
    print(f"vLLM up for {model} in {startup:.0f}s (tp={tp}, gpu_memory_utilization={gpu_memory_utilization}, "
          f"extra={list(extra_args)}, waited for GPU memory: {waited})")
    return server, models, adapters, startup


def _start_mock_server(agent_dir: Path):
    """Dry-run stand-in for vLLM: the scripted OpenAI-compatible mock from tests/ (PILOT_REPO)."""
    import litellm
    from adk_submission import discover_adapters
    from adk_submission.registry import ModelRegistry
    from adk_submission.resolvers.generation import install_litellm_reasoning_patch
    from google.adk.models.lite_llm import LiteLlm
    from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS
    sys.path.insert(0, os.environ["PILOT_REPO"])
    from tests.mock_openai_server import kill, make_script, serve

    litellm.drop_params = True
    install_litellm_reasoning_patch()
    model = describe_agent(agent_dir)["model"]
    if os.environ.get("PILOT_MOCK_FAIL_START") == SHORT.get(model):  # dry-run test of a size whose server fails
        raise RuntimeError("mock: inference server exited prematurely")
    srv = serve(make_script("README.md"), port=int(os.environ.get("PILOT_MOCK_PORT", "8001")))
    reg = ModelRegistry()
    reg.register(model, LiteLlm(model="openai/mock", api_base=f"http://127.0.0.1:{srv.server_address[1]}/v1", api_key="EMPTY"))
    ad = discover_adapters(str(agent_dir), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)

    class _S:
        base_url = f"http://127.0.0.1:{srv.server_address[1]}/v1"

        def stop(self):
            kill(srv)
    return _S(), reg, ad, 0.0


def server_root(server) -> str:
    """http://host:port of a started server (VllmServer.base_url or the dry-run mock's), without /v1."""
    base = str(getattr(server, "base_url", None) or "http://127.0.0.1:8000").rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


def safe_stop(server) -> None:
    """Stop a server that may already have been killed by the watchdog."""
    try:
        server.stop()
    except Exception as e:  # noqa: BLE001
        print(f"server.stop(): {type(e).__name__}: {e}")


# --------------------------------------------------------------------------- evaluation

def make_eval_config(agent_dir: Path, models, adapters, tasks_path: Path, task_ids: list[str], results_dir: Path,
                     concurrency: int, sandbox: str = "subprocess"):
    import yaml
    from google.adk.agents.context_cache_config import ContextCacheConfig
    from google.adk.apps._configs import EventsCompactionConfig
    from swegemma.config import EvalConfig, build_submission_limits

    raw = yaml.safe_load((agent_dir / "eval_config.yaml").read_text()) or {}
    ev = raw.get("evaluation", raw)
    turns = ev.get("max_turns", ev.get("max_llm_calls"))
    limits, gen = build_submission_limits()
    d = data_dir()
    return EvalConfig(
        tasks_path=tasks_path, snapshots_dir=d / "snapshots", results_dir=results_dir, submission_dir=agent_dir,
        models=models, sandbox=sandbox,
        timeout_seconds=int(ev.get("timeout_seconds", 300)),
        verification_timeout_seconds=int(ev.get("verification_timeout_seconds", 300)),
        max_time_minutes=float(ev.get("max_time_minutes", 60.0)), max_tool_calls=int(ev.get("max_tool_calls", 100)),
        max_turns=int(turns) if turns is not None else None,
        limits=limits, generation_constraints=gen, adapter_manifest=adapters,
        context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
        events_compaction_config=EventsCompactionConfig(compaction_interval=15, overlap_size=2, token_threshold=14336,
                                                        event_retention_size=5),
        graph_dir=str(d / "graphs"), embeddings_dir=str(d / "embeddings"), wheels_dir=d / "wheels",
        verbose=False, task_ids=list(task_ids), concurrency=concurrency, display_mode="quiet",
    )


def _result_dict(r) -> dict[str, Any]:
    try:
        d = r.model_dump(exclude={"trace"})
    except Exception:  # noqa: BLE001
        d = dict(r.__dict__)
        d.pop("trace", None)
    d.setdefault("instance_id", getattr(r, "instance_id", None) or d.get("task_id"))
    return d


def collect_rows(results, results_dir: Path, gold: dict[str, dict]) -> list[dict[str, Any]]:
    d = data_dir()
    rows = []
    for r in results:
        rd = _result_dict(r)
        iid = rd.get("instance_id") or rd.get("task_id")
        tpath = rd.get("trace_path") or str(results_dir / "traces" / f"trace_{iid}.json")
        events = load_trace(tpath) if tpath and Path(tpath).exists() else []
        patch = rd.get("agent_patch") or ""
        scopes = diff_scopes(patch, d / "snapshots" / f"{iid}.tgz") if patch.strip() else []
        row = task_metrics(rd, events, gold=gold.get(iid), agent_patch_scopes=scopes)
        row["trace_found"] = bool(events)
        row["trace_compaction_entries"] = sum(1 for e in events if e.type == "compaction")
        row.update({f"cmp_{k}": v for k, v in rp.task_compaction_stats(
            iid, [e.timestamp for e in events if e.type == "tool_call"]).items()})
        rows.append(row)
    return rows


def compaction_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Run-level answer to: how often/when does compaction fire, what does it drop, is it in the trace?"""
    fired = [r for r in rows if r.get("cmp_compactions")]
    firsts = sorted(r["cmp_first_compaction_at_call"] for r in fired if r.get("cmp_first_compaction_at_call") is not None)
    surv = [r["cmp_marker_survival"] for r in fired if r.get("cmp_marker_survival") is not None]
    return {
        "tasks": len(rows), "tasks_with_compaction": len(fired),
        "compactions_total": sum(r.get("cmp_compactions") or 0 for r in rows),
        "first_compaction_at_call_median": firsts[len(firsts) // 2] if firsts else None,
        "first_compaction_at_call_values": firsts,
        "function_calls_dropped": sum(r.get("cmp_function_calls_dropped") or 0 for r in rows),
        "function_responses_dropped": sum(r.get("cmp_function_responses_dropped") or 0 for r in rows),
        "skill_responses_dropped": sum(r.get("cmp_skill_responses_dropped") or 0 for r in rows),
        "task_prompt_compacted_tasks": sum(bool(r.get("cmp_task_prompt_compacted")) for r in fired),
        "requests_after_compaction_with_task_prompt": sum(r.get("cmp_after_with_task_prompt") or 0 for r in fired),
        "requests_after_compaction": sum(r.get("cmp_requests_after_first_compaction") or 0 for r in fired),
        "marker_survival_mean": round(sum(surv) / len(surv), 4) if surv else None,
        "trace_compaction_entries_total": sum(r.get("trace_compaction_entries") or 0 for r in rows),
        "markers": "per task: hint header, gold file path(s), gold function short names",
    }


def _markers_for(g: dict) -> list[str]:
    out = [HINT_HEADER] + list(g.get("src_files") or [])
    out += [f["qualname"].split(".")[-1] for f in g.get("functions") or []]
    return list(dict.fromkeys(out))


def run_condition(agent_dir: Path, models, adapters, task_ids: list[str], gold: dict[str, dict], condition: str,
                  replicate: int, concurrency: int) -> dict[str, Any]:
    from swegemma.evaluate import Evaluator
    model_short = agent_dir.name.replace("agent_", "")
    tasks_path = write_task_copy(task_ids, gold, condition)
    rdir = PRIVATE / "runs" / model_short / f"{condition}_r{replicate}"
    if rdir.exists():
        shutil.rmtree(rdir)
    rdir.mkdir(parents=True)
    cfg = make_eval_config(agent_dir, models, adapters, tasks_path, task_ids, rdir, concurrency)
    rp.install()
    rp.reset()
    for iid in task_ids:
        rp.MARKERS[iid] = _markers_for(gold.get(iid) or {})
    t0 = time.perf_counter()
    res = run_sync(Evaluator(cfg).run)
    batch = time.perf_counter() - t0
    rows = collect_rows(res.task_results, rdir, gold)
    agg = aggregate(rows)
    agg["compaction"] = compaction_summary(rows)
    print(f"[{model_short} {condition} r{replicate}] resolved {agg['resolved']}/{agg['n_tasks']} "
          f"batch {batch/60:.1f} min, mean wall {agg['wall_s_mean']}s, calls {agg['tool_calls_mean']}, "
          f"compactions {agg['compaction']['compactions_total']} (in trace: {agg['compaction']['trace_compaction_entries_total']})")
    return {"model": model_short, "condition": condition, "replicate": replicate, "concurrency": concurrency,
            "batch_wall_s": round(batch, 1), "aggregate": agg, "rows": rows}


def save_summary(path: Path, summary: dict[str, Any]) -> None:
    runs = summary.get("runs", [])
    comps = []
    base = {(r["model"]): r for r in runs if r["condition"] == "O0" and r["replicate"] == 1}
    for r in runs:
        b = base.get(r["model"])
        if b is not None and r is not b:
            comps.append({"model": r["model"], "a": "O0_r1", "b": f"{r['condition']}_r{r['replicate']}",
                          **paired_flips(b["rows"], r["rows"])})
    summary["paired_vs_O0_r1"] = comps
    summary["saved_utc"] = _dt.datetime.utcnow().isoformat(timespec="seconds")
    path.write_text(json.dumps(summary, indent=1))
    print(f"saved {path}")


# --------------------------------------------------------------------------- CPU gold check

def gold_check(task_ids: list[str], out_path: Path, timeout_s: int = 300, baseline: bool = True) -> dict[str, Any]:
    """CPU-only: apply each task's GOLD patch in the scorer's Phase-2 sandbox and record resolved; also run the
    same verification with NO patch (baseline). valid = gold passes AND no-patch fails. Numbers only."""
    from adk_submission.registry import ModelRegistry
    from swegemma.config import EvalConfig
    from swegemma.deduplication import resolve_task_snapshot_paths
    from swegemma.evaluate import Evaluator
    from swegemma.harness.verification import verify_task
    from swegemma.models import load_tasks as sg_load

    d = data_dir()
    PRIVATE.mkdir(parents=True, exist_ok=True)
    cfg = EvalConfig(tasks_path=d / "tasks.jsonl", snapshots_dir=d / "snapshots", results_dir=PRIVATE / "gold_check",
                     submission_dir=d / "sample_submission", models=ModelRegistry(), sandbox="subprocess",
                     timeout_seconds=timeout_s, verification_timeout_seconds=timeout_s, wheels_dir=d / "wheels",
                     graph_dir=str(d / "graphs"), embeddings_dir=str(d / "embeddings"), display_mode="quiet")
    ev = Evaluator(cfg)
    tasks = {t.instance_id: t for t in sg_load(d / "tasks.jsonl")}
    rows = []
    for i, iid in enumerate(task_ids, 1):
        t = tasks[iid]
        snap, base, patch = resolve_task_snapshot_paths(d / "snapshots", iid, t.repo)
        t0 = time.perf_counter()
        out_text = ""
        try:
            r = run_sync(verify_task, ev.docker, cfg, t, snap, base_snapshot_path=base, patch_path=patch,
                         agent_patch=t.patch, agent_error=None, trace=None, start_time=t0)
            ok, err = bool(r.resolved), (r.error or "")[:160] or None
            out_text = r.test_output or ""
        except Exception as e:  # noqa: BLE001
            ok, err = False, f"{type(e).__name__}: {e}"[:160]
        dt = time.perf_counter() - t0
        base_ok = None
        if baseline:  # the same tests with NO patch must fail, else any harmless edit "solves" the task
            try:
                rb = run_sync(verify_task, ev.docker, cfg, t, snap, base_snapshot_path=base, patch_path=patch,
                              agent_patch="", agent_error=None, trace=None, start_time=time.perf_counter())
                base_ok = bool(rb.resolved)
            except Exception:  # noqa: BLE001
                base_ok = None
        cls, mods = classify_gold_failure(ok, err, out_text)
        rows.append({"instance_id": iid, "repo": t.repo, "gold_resolved": ok, "baseline_resolved": base_ok,
                     "valid": bool(ok and base_ok is False), "verify_s": round(dt, 1), "error": err,
                     "failure_class": cls, "missing_modules": mods})  # for missing_fixture: fixture names
        print(f"[{i}/{len(task_ids)}] {iid} gold={ok} no_patch={base_ok} {cls} {mods or ''} {dt:.0f}s {err or ''}")
        out_path.write_text(json.dumps({"rows": rows, "summary": gold_check_summary(rows), "env": env_info()}, indent=1))
    return {"rows": rows, "summary": gold_check_summary(rows)}


_MISSING_MOD = re.compile(r"No module named '([A-Za-z0-9_\.]+)'")
_FIXTURE = re.compile(r"fixture '([A-Za-z0-9_]+)' not found|recursive dependency involving fixture '([A-Za-z0-9_]+)'")


def classify_gold_failure(ok: bool, err: str | None, test_output: str) -> tuple[str, list[str]]:
    """Why a gold patch failed (module names / fixture names only; test output is not stored)."""
    if ok:
        return "resolved", []
    mods = sorted({m.split(".")[0] for m in _MISSING_MOD.findall(test_output or "")})
    if mods:
        return "missing_module", mods
    fx = sorted({a or b for a, b in _FIXTURE.findall(test_output or "")})
    if fx:
        return "missing_fixture", fx
    e = err or ""
    if "Failed to apply" in e:
        return "patch_apply_failed", []
    if "TimeoutExceeded" in e or "timed out" in e.lower():
        return "timeout", []
    if e:
        return "harness_error", []
    return "test_failure", []


def gold_check_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from collections import Counter
    by_repo: dict[str, dict[str, int]] = {}
    for r in rows:
        d = by_repo.setdefault(r.get("repo", "?"), {"checked": 0, "gold_resolved": 0})
        d["checked"] += 1
        d["gold_resolved"] += int(r["gold_resolved"])
        d["valid"] = d.get("valid", 0) + int(bool(r.get("valid")))
    mods = Counter(m for r in rows if r["failure_class"] == "missing_module" for m in r.get("missing_modules") or [])
    fixtures = Counter(m for r in rows if r["failure_class"] == "missing_fixture" for m in r.get("missing_modules") or [])
    fastapi_inline_or_dirty = sum(1 for r in rows if r.get("repo") == "fastapi/fastapi" and r["failure_class"] == "missing_module"
                                  and {"inline_snapshot", "dirty_equals"} & set(r.get("missing_modules") or []))
    return {"checked": len(rows), "gold_resolved": sum(r["gold_resolved"] for r in rows),
            "baseline_resolved_without_patch": sum(1 for r in rows if r.get("baseline_resolved")),
            "valid": sum(1 for r in rows if r.get("valid")), "by_repo": by_repo,
            "failure_classes": dict(Counter(r["failure_class"] for r in rows)), "missing_modules": dict(mods),
            "missing_fixtures": dict(fixtures),
            "fastapi_failing_on_inline_snapshot_or_dirty_equals": fastapi_inline_or_dirty}


def select_from_gold_check(gold_all: dict[str, dict], check_rows: list[dict[str, Any]], seed: int = 20261031) -> dict[str, Any]:
    """Pre-registered order: per repo, eligible VALID tasks (gold passes and no-patch fails HERE), seeded shuffle.
    smoke3 = first of each repo. IDs only."""
    import random
    from pilot_c.select_tasks import QUOTA, eligible
    ok = {r["instance_id"] for r in check_rows if r.get("valid", r["gold_resolved"])}
    rng = random.Random(seed)
    order: dict[str, list[str]] = {}
    for repo in QUOTA:
        pool = sorted(i for i, g in gold_all.items() if g["repo"] == repo and eligible(g) and i in ok)
        rng.shuffle(pool)
        order[repo] = pool
    smoke = [v[0] for v in order.values() if v]
    # fill rule (pre-registered): if a repo has no valid task, take the next valid tasks round-robin
    # from the other repos' orders, so the timing set always has 3 tasks when 3 exist
    k = 1
    while len(smoke) < 3 and any(len(v) > k for v in order.values()):
        for v in order.values():
            if len(v) > k and len(smoke) < 3:
                smoke.append(v[k])
        k += 1
    return {"seed": seed, "eligible_valid_in_order": order, "smoke3": smoke, "valid_all": sorted(ok)}


def find_input_json(name: str) -> Path:
    """Locate an attached notebook output (e.g. C00_gold_check.json from notebooks/C00_gold_check__CPU.ipynb)
    anywhere under /kaggle/input, independent of the slug Kaggle gives the attached notebook."""
    root = os.environ.get("PILOT_INPUT_ROOT", "/kaggle/input")
    hits = sorted(glob.glob(f"{root}/**/{name}", recursive=True))
    if not hits:
        producer = {"C00_gold_check.json": "notebooks/C00_gold_check__CPU.ipynb",
                    "probe_records.jsonl": "notebooks/C03_probe__L4x4.ipynb"}.get(name, "the notebook that writes it")
        raise FileNotFoundError(f"{name} not found under {root}: attach the output of {producer} as an input first "
                                "(see notebooks/README.md)")
    return Path(hits[0])
