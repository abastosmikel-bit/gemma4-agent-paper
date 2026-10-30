"""Generate notebooks/pilot_a_run.ipynb: one self-contained Kaggle notebook.

The repo code (common/ + pilot_a/) is embedded as a base64 tarball, so the user
only uploads one .ipynb. Re-run this after changing code or skills:

  python tools/build_notebook.py
"""
from __future__ import annotations

import base64
import io
import json
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = ["common", "pilot_a"]
EXCLUDE_PARTS = {"__pycache__"}
EXCLUDE_PREFIX = ("pilot_a/scripts/",)  # local-only tools (skill scripts/ ARE included)


def code_tarball() -> str:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for top in INCLUDE:
            for p in sorted((ROOT / top).rglob("*")):
                rel = p.relative_to(ROOT)
                if (p.is_file() and not (set(rel.parts) & EXCLUDE_PARTS) and p.suffix != ".pyc"
                        and not rel.as_posix().startswith(EXCLUDE_PREFIX)):
                    tar.add(p, arcname=str(rel))
    return base64.b64encode(buf.getvalue()).decode()


def md(s):
    return {"cell_type": "markdown", "metadata": {}, "source": s}


def code(s):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s}


INTRO = """# Pilot A: skills as weight-free post-training (Gemma 4 E4B)

**Before running:** attach (1) competition `gemma-4-developer-agent`, (2) dataset
`metric/gemma-4-developer-agent-wheelhouse`, (3) model `google/gemma-4` variant
`gemma-4-e4b-it-qat-w4a16-ct` (version 2). Accelerator: **GPU L4 x4** (or T4 x2 for `PHASE="probe"`).
Internet can stay off.

Set `PHASE` in the next cell, then *Run all*. Output to download/commit:
`/kaggle/working/pilot_a_<PHASE>.json` (aggregate numbers only).
Raw traces stay in `/kaggle/working/runs/` (do **not** commit them).
"""

PARAMS = """PHASE = "smoke"   # smoke | probe | phase2 | phase3 | phase4
MODEL = "gemma-4-e4b-it-qat-w4a16-ct"
CONCURRENCY = 4   # parallel tasks sharing one vLLM server
import time; NOTEBOOK_T0 = time.time()
"""

# Verbatim logic of the official starter's setup cell (wheel install).
SETUP = """import glob, importlib, logging, os, shutil, subprocess, sys
from pathlib import Path
for k, v in {'TRANSFORMERS_NO_TF': '1', 'TRANSFORMERS_NO_FLAX': '1', 'TRANSFORMERS_OFFLINE': '1',
             'VLLM_NO_USAGE_STATS': '1', 'VLLM_WORKER_MULTIPROC_METHOD': 'spawn',
             'VLLM_ENGINE_READY_TIMEOUT_S': '1200', 'VLLM_MEMORY_PROFILER_ESTIMATE_CUDAGRAPHS': '1',
             'NCCL_DEBUG': 'WARN', 'LITELLM_LOCAL_MODEL_COST_MAP': 'True', 'LITELLM_TELEMETRY': 'False',
             'LITELLM_LOG': 'WARNING', 'PYTORCH_CUDA_ALLOC_CONF': 'expandable_segments:True',
             'OTEL_SDK_DISABLED': 'true', 'OTEL_PYTHON_DISABLED': 'true'}.items():
    os.environ[k] = v
os.environ.setdefault('OPENAI_API_KEY', 'EMPTY'); os.environ.setdefault('LOCAL_API_KEY', 'EMPTY')
for name in ('LiteLLM', 'LiteLLM Router', 'LiteLLM Proxy', 'litellm', 'httpx', 'httpcore', 'openai',
             'urllib3', 'opentelemetry', 'opentelemetry.context'):
    lg = logging.getLogger(name); lg.setLevel(logging.WARNING)
    if 'litellm' in name.lower(): lg.propagate = False; lg.handlers.clear()

WHEELHOUSE_DIR = Path('/kaggle/input/datasets/metric/gemma-4-developer-agent-wheelhouse')
if not WHEELHOUSE_DIR.exists():
    WHEELHOUSE_DIR = next(Path('/kaggle/input').glob('**/gemma-4-developer-agent-wheelhouse'))
for pat in ('/usr/local/lib/python*/dist-packages/*cutlass*.pth', '/usr/local/lib/python*/site-packages/*cutlass*.pth'):
    for pth in glob.glob(pat):
        try: os.unlink(pth)
        except OSError: pass
tmp_whl = Path('/tmp/wheelhouse'); tmp_whl.mkdir(parents=True, exist_ok=True)
for w in WHEELHOUSE_DIR.glob('*.whl'):
    if 'cutlass' in w.name.lower(): continue
    t = tmp_whl / (w.name.replace('cu128', '+cu128') if ('cu128' in w.name and '+' not in w.name) else w.name)
    if not t.exists():
        try: os.symlink(w, t)
        except OSError: shutil.copyfile(w, t)
wheels = sorted(str(w) for w in tmp_whl.glob('*.whl'))
print(f'Installing {len(wheels)} wheels...')
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '--no-deps', '--force-reinstall', *wheels], check=True)
importlib.invalidate_caches()
print(f'setup done in {time.time() - NOTEBOOK_T0:.0f}s')
"""

UNPACK = """import base64, io, tarfile
CODE_TGZ = "{blob}"
PILOT_ROOT = Path('/kaggle/working/pilot_code')
shutil.rmtree(PILOT_ROOT, ignore_errors=True); PILOT_ROOT.mkdir(parents=True)
with tarfile.open(fileobj=io.BytesIO(base64.b64decode(CODE_TGZ)), mode='r:gz') as t:
    t.extractall(PILOT_ROOT, filter='data')
sys.path[:0] = [str(PILOT_ROOT), str(PILOT_ROOT / 'pilot_a')]
print(sorted(p.name for p in (PILOT_ROOT / 'pilot_a' / 'skills').iterdir()))
"""

RUN = """import kaggle_runner as kr
print(kr.gpu_info())
report = kr.run_phase(PHASE, MODEL, concurrency=CONCURRENCY)
print(f"notebook wall time so far: {(time.time() - NOTEBOOK_T0) / 3600:.2f} h")
"""

SUMMARY = """import pandas as pd
rows = [{'run': r['tag'], 'wall_s': r['wall_clock_s'], **{k: v for k, v in r['aggregate'].items() if k != 'skills_loaded'}}
        for r in report['runs']]
display(pd.DataFrame(rows))
for r in report['runs']:
    print(r['tag'], 'skills loaded:', r['aggregate'].get('skills_loaded'))
if report.get('distill'):
    print(report['distill']['stdout'])
"""

PACK = """# Keep raw traces as a private notebook output for skill building (never commit them).
import tarfile
with tarfile.open(f'/kaggle/working/raw_{PHASE}.tgz', 'w:gz') as t:
    t.add('/kaggle/working/runs', arcname='runs')
    if Path('/kaggle/working/skills_self_distilled').exists():
        t.add('/kaggle/working/skills_self_distilled', arcname='skills_self_distilled')
shutil.rmtree('/kaggle/working/subs', ignore_errors=True)
print(f'TOTAL notebook wall time: {(time.time() - NOTEBOOK_T0) / 3600:.2f} h  (L4x4 quota used = 2x this)')
"""


def main() -> None:
    nb = {
        "cells": [md(INTRO), code(PARAMS), code(SETUP), code(UNPACK.replace("{blob}", code_tarball())),
                  code(RUN), code(SUMMARY), code(PACK)],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                     "language_info": {"name": "python"}},
        "nbformat": 4, "nbformat_minor": 5,
    }
    out = ROOT / "notebooks" / "pilot_a_run.ipynb"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(nb, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
