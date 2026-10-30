"""Show exactly what the model sees for a submission: system instruction + tool list.

Compiles the submission with the real adk_submission compiler and runs one ADK turn
against a recording fake LLM (no GPU, no server). Tools are signature stubs.

  python inspect_prompt.py <submission_dir> [--out report.md]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from adk_submission import compile_submission
from adk_submission.registry import ModelRegistry

CAPTURED: list = []


class RecordingLlm(BaseLlm):
    model: str = "recording"

    async def generate_content_async(self, llm_request, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        CAPTURED.append(llm_request)
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="done")]))


# Signature stubs matching HARNESS_README section 6 (bodies never run here).
def run_command(command: str) -> str: return ""
def submit_patch() -> str: return ""
def get_status() -> str: return ""
def read_file(filepath: str, start_line: int | None = None, end_line: int | None = None) -> str: return ""
def edit_file(filepath: str, old_string: str, new_string: str, allow_multiple: bool = False) -> str: return ""
def write_file(filepath: str, content: str) -> str: return ""
def get_code_neighbors(node: str, edge_type: str | None = None, max_neighbors: int = 50) -> str: return ""
def search_similar_code(query: str, k: int = 10) -> str: return ""
def get_code_subgraph(nodes: list[str]) -> str: return ""

TOOLS = {f.__name__: f for f in (run_command, submit_patch, get_status, read_file, edit_file,
                                 write_file, get_code_neighbors, search_similar_code, get_code_subgraph)}


async def capture(sub: Path) -> tuple[str, list[str]]:
    models = ModelRegistry()
    for line in (sub / "agent.yaml").read_text().splitlines():
        if line.strip().startswith("model:"):
            models.register(line.split(":", 1)[1].strip(), RecordingLlm())
            break
    agent = compile_submission(submission_dir=sub, tool_registry=TOOLS, model_registry=models)
    svc = InMemorySessionService()
    runner = Runner(app_name="inspect", agent=agent, session_service=svc)
    s = await svc.create_session(app_name="inspect", user_id="u", state={"problem_description": "PROBLEM"})
    msg = types.Content(role="user", parts=[types.Part(text="TASK PROMPT")])
    async for _ in runner.run_async(user_id="u", session_id=s.id, new_message=msg):
        pass
    req = CAPTURED[0]
    si = req.config.system_instruction
    if not isinstance(si, str):
        si = "\n".join(p.text for p in getattr(si, "parts", []) or [] if getattr(p, "text", None))
    names = []
    for t in req.config.tools or []:
        for fd in getattr(t, "function_declarations", None) or []:
            names.append(fd.name)
    return si, names


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("submission")
    ap.add_argument("--out")
    a = ap.parse_args()
    si, names = asyncio.run(capture(Path(a.submission)))
    report = {
        "tools": names,
        "system_instruction_chars": len(si),
        "mentions_available_skills_xml": "<available_skills>" in si,
        "skill_names_in_prompt": [n for n in ("reproduce-first", "verify-before-submit", "recover-from-failed-calls") if n in si],
    }
    print(json.dumps(report, indent=2))
    if a.out:
        Path(a.out).write_text(f"# Prompt seen by the model\n\n```json\n{json.dumps(report, indent=2)}\n```\n\n"
                               f"## System instruction\n\n```text\n{si}\n```\n", encoding="utf-8")


if __name__ == "__main__":
    main()
