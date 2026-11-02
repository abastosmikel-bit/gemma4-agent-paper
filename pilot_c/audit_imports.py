"""Audit check (CPU): does the task's test run import the REPO's copy of the package under test, or a copy installed in
the host environment? The harness runs tests as `cd /workspace && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s -m pytest`
with PYTHONPATH=/workspace, in a venv that also sees the host's site-packages (swegemma sandbox/subprocess.py). For a
src-layout repo (package under src/), /workspace is not where the package lives, so `import <pkg>` can resolve to the
host's installed copy (the harness itself depends on requests and httpx); then the patch cannot change the outcome.

Method: wrap the harness's own SubprocessSandbox.exec; right before it runs pytest, run in the identical environment
  python3 -s -c "import <pkg>; print(<pkg>.__file__, <pkg>.__version__)"
and record where the module came from. Verification itself runs exactly as notebooks/C00_gold_check__CPU.ipynb does
(gold patch). Numbers and paths relative to the workspace only.
Usage: python -m pilot_c.audit_imports <out.json> <task_id> [<task_id> ...]
"""
from __future__ import annotations

import json
import sys
import tarfile
import time
from pathlib import Path

from pilot_c import kaggle_runner as kr

PKG = {"psf/requests": "requests", "encode/httpx": "httpx", "fastapi/fastapi": "fastapi", "Textualize/rich": "rich"}
PROBE: dict[str, dict] = {}
_CUR = {"task": None, "pkg": None, "src_fix": False}
SRC_FIX = "PYTHONPATH=/workspace/src:/workspace "   # counterfactual: the repo's own src/ first on the import path


def _layout(snapshot: Path, pkg: str) -> str:
    names = set()
    with tarfile.open(snapshot, "r|gz") as tf:
        for m in tf:
            n = m.name[2:] if m.name.startswith("./") else m.name
            if n in (f"{pkg}/__init__.py", f"src/{pkg}/__init__.py"):
                names.add(n)
    return "src" if f"src/{pkg}/__init__.py" in names else "root" if f"{pkg}/__init__.py" in names else "not found"


def _install_hook() -> None:
    from swegemma.sandbox import subprocess as sb
    orig = sb.SubprocessManager.exec

    def exec_(self, sandbox_id, command, *, timeout=None):
        if "-m pytest" in command and _CUR["src_fix"]:
            command = command.replace("PYTHONSAFEPATH=1 ", "PYTHONSAFEPATH=1 " + SRC_FIX, 1)
        key = (_CUR["task"], _CUR["src_fix"])
        if "-m pytest" in command and _CUR["task"] and key not in PROBE:
            pkg = _CUR["pkg"]
            code = (f"import json, {pkg}; print('PROBE' + json.dumps({{'file': {pkg}.__file__, "
                    f"'version': getattr({pkg}, '__version__', None)}}))")
            probe = (f"cd /workspace && PYTHONSAFEPATH=1 {SRC_FIX if _CUR['src_fix'] else ''}PYTHONNOUSERSITE=1 "
                     f"python3 -s -c \"{code}\"")
            r = orig(self, sandbox_id, probe, timeout=120)
            out = (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
            ws = str(self._sandboxes[sandbox_id]["workspace"])
            rec = {"raw_error": None}
            line = next((l for l in out.splitlines() if l.startswith("PROBE")), None)
            if line:
                v = json.loads(line[5:])
                f = v["file"] or ""
                rec.update(version=v["version"],
                           imported_from=("workspace/src" if f.startswith(ws + "/src/") else "workspace" if f.startswith(ws + "/")
                                          else "venv/host site-packages"),
                           module_path=f.replace(ws, "<workspace>") if f.startswith(ws) else f.split("site-packages/")[-1])
            else:
                rec["raw_error"] = out[-300:]
            PROBE[key] = rec
        return orig(self, sandbox_id, command, timeout=timeout)
    sb.SubprocessManager.exec = exec_


def main(out_path: str, *task_ids: str) -> dict:
    from adk_submission.registry import ModelRegistry
    from swegemma.config import EvalConfig
    from swegemma.deduplication import resolve_task_snapshot_paths
    from swegemma.evaluate import Evaluator
    from swegemma.harness.verification import verify_task
    from swegemma.models import load_tasks as sg_load

    _install_hook()
    d = kr.data_dir()
    cfg = EvalConfig(tasks_path=d / "tasks.jsonl", snapshots_dir=d / "snapshots", results_dir=kr.PRIVATE / "audit_imports",
                     submission_dir=d / "sample_submission", models=ModelRegistry(), sandbox="subprocess",
                     timeout_seconds=300, verification_timeout_seconds=300, wheels_dir=d / "wheels",
                     graph_dir=str(d / "graphs"), embeddings_dir=str(d / "embeddings"), display_mode="quiet")
    ev = Evaluator(cfg)
    tasks = {t.instance_id: t for t in sg_load(d / "tasks.jsonl")}
    rows = []
    def verify(t, snap, base, patch, agent_patch):
        try:
            r = kr.run_sync(verify_task, ev.docker, cfg, t, snap, base_snapshot_path=base, patch_path=patch,
                            agent_patch=agent_patch, agent_error=None, trace=None, start_time=time.perf_counter())
            return bool(r.resolved) and (bool(agent_patch.strip()) or agent_patch == "")
        except Exception as e:  # noqa: BLE001
            return f"error: {type(e).__name__}"

    for iid in task_ids:
        t = tasks[iid]
        pkg = PKG[t.repo]
        snap, base, patch = resolve_task_snapshot_paths(d / "snapshots", iid, t.repo)
        t0 = time.perf_counter()
        row = {"instance_id": iid, "repo": t.repo, "package": pkg, "layout": _layout(Path(snap), pkg)}
        for fix in (False, True):
            _CUR.update(task=iid, pkg=pkg, src_fix=fix)
            tag = "src_first" if fix else "as_harness"
            row[f"{tag}_gold"] = verify(t, snap, base, patch, t.patch)
            row[f"{tag}_no_patch"] = verify(t, snap, base, patch, "")
            p = PROBE.get((iid, fix), {"raw_error": "no pytest run observed"})
            row[f"{tag}_imported_from"] = p.get("imported_from")
            row[f"{tag}_version"] = p.get("version")
            if p.get("raw_error"):
                row[f"{tag}_probe_error"] = p["raw_error"][-200:]
        row["verify_s"] = round(time.perf_counter() - t0, 1)
        rows.append(row)
        print(rows[-1])
        Path(out_path).write_text(json.dumps({"rows": rows, "env": kr.env_info()}, indent=1))
    return {"rows": rows}


if __name__ == "__main__":
    main(sys.argv[1], *sys.argv[2:])
