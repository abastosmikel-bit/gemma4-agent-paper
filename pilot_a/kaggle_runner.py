"""Kaggle-side logic for pilot A (imported by notebooks/pilot_a_run.ipynb).

Mirrors the official starter notebook (vLLM + swegemma Evaluator, subprocess sandbox)
and adds: arm building, concurrency, shared metrics, and an aggregate-only results JSON.
Raw traces/patches stay in /kaggle/working/runs and are never part of the results JSON.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from common.metrics import aggregate, task_metrics  # noqa: E402
from common.trace_parser import parse_trace_file  # noqa: E402
from plan import DISTILL_AFTER, PHASES, run_tag, split_ids  # noqa: E402

DATA_DIR = Path("/kaggle/input/competitions/gemma-4-developer-agent")
WORK = Path("/kaggle/working")
ALLOWED = {"gemma-4-31b-it-qat-w4a16-ct", "gemma-4-12b-it-qat-w4a16-ct",
           "gemma-4-e4b-it-qat-w4a16-ct", "gemma-4-e2b-it-qat-w4a16-ct"}
EXTRA_ARGS = {"gemma-4-12b-it-qat-w4a16-ct": (
    "--hf-overrides", '{"architectures": ["Gemma4ForCausalLM"], "model_type": "gemma4"}')}
DECLARED_TOOLS = ["run_command", "read_file", "edit_file", "write_file", "get_status", "submit_patch",
                  "get_code_neighbors", "search_similar_code", "get_code_subgraph", "code_analyzer_agent"]


def run_sync(coro_fn):
    """Run an async function from inside Jupyter's running event loop (as in the starter)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(coro_fn())).result()
    return asyncio.run(coro_fn())


def gpu_info() -> dict:
    import torch
    n = torch.cuda.device_count() if torch.cuda.is_available() else 0
    names = [torch.cuda.get_device_name(i) for i in range(n)]
    return {"gpu_count": n, "gpus": names, "bf16": bool(n and torch.cuda.is_bf16_supported()),
            "cpu_count": os.cpu_count(), "python": platform.python_version()}


def start_vllm(model: str):
    """Start vLLM exactly like the starter; tensor parallel = number of GPUs (4 on L4x4)."""
    import litellm
    import torch
    from adk_submission import VllmConfig, VllmServer

    litellm.drop_params = True
    assert model in ALLOWED, model
    path = Path(f"/kaggle/input/models/google/gemma-4/other/{model}/2")
    assert path.exists(), f"attach the model input: {path}"
    n = torch.cuda.device_count()
    tp = 4 if n >= 4 else (2 if n >= 2 else 1)
    bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    cfg = VllmConfig(
        model=str(path), port=8000, host="127.0.0.1", tool_call_parser="gemma4",
        reasoning_parser="gemma4", max_model_len=32768,
        dtype="bfloat16" if bf16 else "auto",  # 'auto' -> fp16 on T4 (no bf16)
        gpu_memory_utilization=0.90, enable_auto_tool_choice=True, enable_lora=False,
        max_loras=1, max_lora_rank=128, scheduler_reserve_full_isl=False,
        tensor_parallel_size=tp, startup_timeout=60 * 20, extra_args=EXTRA_ARGS.get(model, ()),
    )
    t0 = time.time()
    server = VllmServer(cfg)
    server.start()
    models = server.create_model_registry(aliases=[model], model_prefix="openai/",
                                          api_key=os.environ.get("LOCAL_API_KEY", "EMPTY"))
    return server, models, {"vllm_start_s": round(time.time() - t0, 1), "tp": tp, "bf16": bf16}


def build_arm(arm: str, seed: int, model: str, out: Path) -> Path:
    cmd = [sys.executable, str(HERE / "build_submission.py"), "--sample", str(DATA_DIR / "sample_submission"),
           "--arm", arm, "--model", model, "--seed", str(seed), "--out", str(out)]
    subprocess.run(cmd, check=True)
    return out


def run_one(arm: str, seed: int, split: str, model: str, models, concurrency: int) -> dict:
    from google.adk.agents.context_cache_config import ContextCacheConfig
    from google.adk.apps._configs import EventsCompactionConfig
    from swegemma.config import EvalConfig, build_submission_limits
    from swegemma.evaluate import Evaluator
    import yaml

    tag = run_tag(arm, seed, split)
    sub = build_arm(arm, seed, model, WORK / "subs" / tag)
    ev = (yaml.safe_load((sub / "eval_config.yaml").read_text()) or {})["evaluation"]
    ids = split_ids(split)
    res_dir = WORK / "runs" / tag
    limits, gen = build_submission_limits()
    cfg = EvalConfig(
        tasks_path=DATA_DIR / "tasks.jsonl", snapshots_dir=DATA_DIR / "snapshots", results_dir=res_dir,
        submission_dir=sub, models=models, sandbox="subprocess",
        timeout_seconds=int(ev["timeout_seconds"]), verification_timeout_seconds=300,
        max_time_minutes=float(ev["max_time_minutes"]), max_tool_calls=int(ev["max_tool_calls"]),
        max_turns=int(ev["max_turns"]), limits=limits, generation_constraints=gen,
        context_cache_config=ContextCacheConfig(min_tokens=2048, ttl_seconds=1800, cache_intervals=10),
        events_compaction_config=EventsCompactionConfig(compaction_interval=15, overlap_size=2,
                                                        token_threshold=14336, event_retention_size=5),
        graph_dir=str(DATA_DIR / "graphs"), embeddings_dir=str(DATA_DIR / "embeddings"),
        wheels_dir=DATA_DIR / "wheels", task_ids=ids, concurrency=concurrency, display_mode="quiet",
        verbose=False,
    )
    t0 = time.time()
    result = run_sync(lambda: Evaluator(cfg).run())
    wall = time.time() - t0

    rows = []
    for tr in result.task_results:
        tp = res_dir / "traces" / f"trace_{tr.instance_id.replace('/', '__')}.json"
        if tp.exists():
            pt = parse_trace_file(tp)
        else:
            from common.trace_parser import ParsedTrace
            pt = ParsedTrace(instance_id=tr.instance_id)
        row = task_metrics(pt, {"resolved": tr.resolved, "duration_seconds": tr.duration_seconds,
                                "tool_calls": tr.tool_calls}, declared_tools=DECLARED_TOOLS)
        row["error"] = (tr.error or "")[:200] or None
        row["patch_empty"] = not (tr.agent_patch or "").strip()
        rows.append(row)
    return {"arm": arm, "seed": seed, "split": split, "tag": tag, "n_tasks": len(ids),
            "concurrency": concurrency, "wall_clock_s": round(wall, 1),
            "aggregate": aggregate(rows), "rows": rows}


def distill(tag: str) -> dict:
    out = WORK / "skills_self_distilled"
    cmd = [sys.executable, str(HERE / "distill_skills.py"), "--runs", str(WORK / "runs" / tag), "--out", str(out)]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    return {"from": tag, "returncode": p.returncode, "stdout": p.stdout[-3000:], "stderr": p.stderr[-2000:],
            "seconds": round(time.time() - t0, 1), "skills_dir": str(out)}


def run_phase(phase: str, model: str, concurrency: int = 4) -> dict:
    t_start = time.time()
    out_path = WORK / f"pilot_a_{phase}.json"
    report = {"pilot": "A-skills", "phase": phase, "model": model, "env": gpu_info(), "runs": []}
    server, models, vinfo = start_vllm(model)
    report["vllm"] = vinfo
    try:
        for arm, seed, split in PHASES[phase]:
            print(f"=== {run_tag(arm, seed, split)}", flush=True)
            r = run_one(arm, seed, split, model, models, concurrency)
            report["runs"].append(r)
            a = r["aggregate"]
            print(f"    resolved {a['resolved']}/{a['n']}  wall {r['wall_clock_s']:.0f}s  "
                  f"skill_load_rate {a['skill_load_rate']:.2f}", flush=True)
            if DISTILL_AFTER.get(phase) == (arm, seed, split):
                report["distill"] = distill(r["tag"])
                print(report["distill"]["stdout"][-800:], flush=True)
            report["total_s"] = round(time.time() - t_start, 1)
            out_path.write_text(json.dumps(report, indent=1, default=str))  # crash-safe
    finally:
        server.stop()
    report["total_s"] = round(time.time() - t_start, 1)
    report["gpu_hours_wall"] = round(report["total_s"] / 3600, 3)
    out_path.write_text(json.dumps(report, indent=1, default=str))
    print(f"wrote {out_path}; session GPU wall time {report['gpu_hours_wall']} h "
          f"(+ setup cells before this); L4x4 quota = 2x wall time")
    return report
