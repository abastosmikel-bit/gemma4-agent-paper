"""Validate tasks with the competition harness's own Phase-2 code (swegemma.verify_task).

A task is VALID iff, in the chosen sandbox backend:
  baseline: verify_task(agent_patch="")          -> resolved == False   (tests fail without the fix)
  gold:     verify_task(agent_patch=task.patch)  -> resolved == True    (exit 0 + JUnit checks pass)
This is the host's own criterion (swegemma.harness.sample_verification: base_exit != 0 and
patch_exit == 0), but run through verify_task so protected-file stripping, test-file reset,
pytest.ini/conftest rewriting and JUnit validation are exactly what the scorer does.

Run with the interpreter that has swegemma installed. In subprocess mode that interpreter's
site-packages ARE the sandbox's environment (SubprocessManager uses system_site_packages=True),
so it should mirror the Kaggle notebook host as closely as possible.

Usage:
  python common/validate.py --tasks T.jsonl --snapshots DIR --backend subprocess \
      --out results.jsonl [--wheels DIR] [--ids a b c] [--logs DIR]
Output: one JSON line per task with verdict fields only (no patches, no test output).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import tempfile
import time
from pathlib import Path


def _config(args, results_dir: Path):
    from adk_submission import ModelRegistry
    from swegemma.config import EvalConfig

    return EvalConfig(
        tasks_path=Path(args.tasks),
        snapshots_dir=Path(args.snapshots),
        results_dir=results_dir,
        submission_dir=results_dir,
        models=ModelRegistry(),
        sandbox=args.backend,
        image=args.image,
        wheels_dir=Path(args.wheels) if args.wheels else None,
        timeout_seconds=args.timeout,
        verification_timeout_seconds=args.timeout,
    )


def _sandbox(config):
    if config.sandbox == "docker":
        from swegemma.sandbox import ContainerConfig, ContainerManager

        return ContainerManager(ContainerConfig(image=config.image, timeout_seconds=config.verification_timeout_seconds))
    from swegemma.sandbox.subprocess import SubprocessManager

    return SubprocessManager(timeout_seconds=config.verification_timeout_seconds)


def _first_error_line(text: str) -> str:
    """A short, data-free failure category (exception class / pytest summary keyword)."""
    import re

    for pat in (r"(ModuleNotFoundError|ImportError|AttributeError|TypeError|NameError|SyntaxError|"
                r"AssertionError|FileNotFoundError|fixture '[^']+' not found|ERROR collecting)",
                r"(\d+ failed|\d+ error)"):
        m = re.search(pat, text or "")
        if m:
            return m.group(1)[:80]
    return ""


async def _one(task, args, logs: Path | None):
    from swegemma.harness.verification import verify_task

    snap = Path(args.snapshots) / f"{task.instance_id}.tgz"
    if not snap.exists():
        snap = Path(args.snapshots) / f"{task.instance_id}.tar.gz"
    rec = {"instance_id": task.instance_id, "repo": task.repo, "backend": args.backend}
    with tempfile.TemporaryDirectory() as td:
        config = _config(args, Path(td))
        sb = _sandbox(config)
        for kind, patch in (("base", ""), ("gold", task.patch)):
            t0 = time.perf_counter()
            try:
                r = await verify_task(sb, config, task, snap, agent_patch=patch, start_time=t0)
                rec[f"{kind}_resolved"] = bool(r.resolved)
                rec[f"{kind}_exit"] = r.test_exit_code
                rec[f"{kind}_error"] = (r.error or "")[:160]
                rec[f"{kind}_symptom"] = _first_error_line(r.test_output)
                if logs:
                    (logs / f"{task.instance_id}.{args.backend}.{kind}.log").write_text(
                        f"error: {r.error}\n\n{r.test_output}")
            except Exception as e:  # harness/setup failure, not a test verdict
                rec[f"{kind}_resolved"] = None
                rec[f"{kind}_error"] = f"{type(e).__name__}: {e}"[:160]
            rec[f"{kind}_seconds"] = round(time.perf_counter() - t0, 1)
    rec["valid"] = rec.get("base_resolved") is False and rec.get("gold_resolved") is True
    return rec


async def main_async(args):
    from swegemma.models import load_tasks

    tasks = load_tasks(Path(args.tasks))
    if args.ids:
        tasks = [t for t in tasks if t.instance_id in set(args.ids)]
    logs = Path(args.logs) if args.logs else None
    if logs:
        logs.mkdir(parents=True, exist_ok=True)
    out = open(args.out, "a")
    sem = asyncio.Semaphore(args.concurrency)

    async def run(t):
        async with sem:
            rec = await _one(t, args, logs)
            out.write(json.dumps(rec) + "\n")
            out.flush()
            print(json.dumps({k: rec.get(k) for k in ("instance_id", "valid", "base_resolved", "gold_resolved",
                                                      "gold_symptom", "gold_error", "gold_seconds")}), flush=True)

    await asyncio.gather(*(run(t) for t in tasks))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", required=True)
    p.add_argument("--snapshots", required=True)
    p.add_argument("--backend", choices=["subprocess", "docker"], default="subprocess")
    p.add_argument("--image", default="swebench-sandbox:latest")
    p.add_argument("--wheels")
    p.add_argument("--ids", nargs="*")
    p.add_argument("--out", required=True)
    p.add_argument("--logs")
    p.add_argument("--timeout", type=int, default=300)
    p.add_argument("--concurrency", type=int, default=2)
    a = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main_async(a))
