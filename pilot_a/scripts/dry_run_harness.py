"""CPU-only end-to-end check of the skill path in the REAL swegemma harness.

Runs swegemma's Evaluator (subprocess sandbox, as on Kaggle) on one task with a
scripted fake model that: lists skills, loads one, edits a file, runs the skill's
script, repeats a call, and submits. Then parses the saved trace with common/.

  python dry_run_harness.py --submission <dir> --tasks tasks.jsonl --snapshots <dir> \
      --task-id httpx_3672 --results <out_dir>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from common.metrics import task_metrics  # noqa: E402
from common.trace_parser import parse_trace_file  # noqa: E402

SCRIPT = [
    ("list_skills", {}),
    ("load_skill", {"skill_name": "verify-before-submit"}),
    ("run_command", {"command": "echo '# dry-run edit' >> README.md && git status --short"}),
    ("run_skill_script", {"skill_name": "verify-before-submit", "file_path": "scripts/check_patch.py"}),
    ("run_command", {"command": "ls"}),
    ("run_command", {"command": "ls"}),
    ("load_skill", {"skill_name": "no-such-skill"}),
    ("submit_patch", {}),
]
SEEN: list[dict] = []


class ScriptedLlm(BaseLlm):
    model: str = "scripted"

    async def generate_content_async(self, llm_request, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        n_resp = 0
        for c in llm_request.contents or []:
            for p in c.parts or []:
                if p.function_response is not None:
                    n_resp += 1
                    SEEN.append({"tool": p.function_response.name,
                                 "response": json.dumps(p.function_response.response, default=str)[:1500]})
        if n_resp < len(SCRIPT):
            name, args = SCRIPT[n_resp]
            part = types.Part(function_call=types.FunctionCall(name=name, args=args))
        else:
            part = types.Part(text="Done.")
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submission", required=True)
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--snapshots", required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--results", required=True)
    a = ap.parse_args()

    from adk_submission.registry import ModelRegistry
    from swegemma.config import EvalConfig, build_submission_limits
    from swegemma.evaluate import Evaluator

    sub = Path(a.submission)
    model = next(l.split(":", 1)[1].strip() for l in (sub / "agent.yaml").read_text().splitlines()
                 if l.strip().startswith("model:"))
    models = ModelRegistry()
    models.register(model, ScriptedLlm())
    limits, gen = build_submission_limits()
    cfg = EvalConfig(
        tasks_path=Path(a.tasks), snapshots_dir=Path(a.snapshots), results_dir=Path(a.results),
        submission_dir=sub, models=models, sandbox="subprocess", timeout_seconds=60,
        verification_timeout_seconds=60, max_time_minutes=5, max_tool_calls=20, max_turns=30,
        limits=limits, generation_constraints=gen, task_ids=[a.task_id], display_mode="quiet",
    )
    res = asyncio.run(Evaluator(cfg).run())
    tr = res.task_results[0]
    print("RESULT", json.dumps({"resolved": tr.resolved, "tool_calls": tr.tool_calls, "error": tr.error,
                                 "patch_chars": len(tr.agent_patch or "")}))
    print("PATCH FILES", [l for l in (tr.agent_patch or "").splitlines() if l.startswith("diff --git")])
    for s in SEEN[-len(SCRIPT):]:
        print("--", s["tool"], s["response"][:700])
    pt = parse_trace_file(Path(a.results) / "traces" / f"trace_{a.task_id}.json")
    m = task_metrics(pt, {"resolved": tr.resolved, "duration_seconds": tr.duration_seconds,
                          "tool_calls": tr.tool_calls},
                     declared_tools=["run_command", "read_file", "edit_file", "write_file", "get_status",
                                     "submit_patch", "get_code_neighbors", "search_similar_code",
                                     "get_code_subgraph", "code_analyzer_agent"])
    print("METRICS", json.dumps({k: v for k, v in m.items() if k != "tool_breakdown"}, default=str))


if __name__ == "__main__":
    main()
