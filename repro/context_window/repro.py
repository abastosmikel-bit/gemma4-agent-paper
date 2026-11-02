"""Minimal CPU reproduction: with the official starter's settings, one large tool output pushes the prompt past the
server's limit BEFORE ADK's compaction runs, and the request is rejected. With `max_output_tokens: 8192` it is accepted
and compaction then shrinks the context.

What is real and what is simulated
  real      : google-adk 1.36.1 (agent loop, token-threshold compaction, summarizer, how the summary enters the context),
              with the starter's EventsCompactionConfig(compaction_interval=15, overlap_size=2, token_threshold=14336,
              event_retention_size=5) and the agent's sampling setting max_output_tokens.
  simulated : the model and the server. The fake model counts prompt tokens as whitespace-separated words of the request,
              reports that count as usage (as vLLM does), and applies vLLM 0.19.1's length rule
              (vllm/entrypoints/openai/engine/serving.py: prompt + max_tokens > max_model_len -> HTTP 400):
                  reject if prompt_tokens + max_output_tokens > 32768
              It always calls one tool; the tool returns outputs of fixed sizes (5 reads of 2,000 words, then one
              4,000-word test log), the kind of outputs the agent's read_file and run_command produce.
Run (CPU, ~5 s):  pip install google-adk==1.36.1 && python repro.py
Expected: starter setting -> REJECTED at the request after the 4,000-word output, with no compaction before it;
          max_output_tokens 8192 -> that request is ACCEPTED, compaction runs before the next one, the prompt shrinks.
"""
from __future__ import annotations

import asyncio
import os
import sys
import warnings

os.environ.setdefault("OTEL_SDK_DISABLED", "true")
warnings.filterwarnings("ignore")
from typing import AsyncGenerator

from google.adk.agents import LlmAgent
from google.adk.apps import App
from google.adk.apps._configs import EventsCompactionConfig
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

MAX_MODEL_LEN = 32768                         # starter: VllmConfig(max_model_len=32768)
STARTER = dict(compaction_interval=15, overlap_size=2, token_threshold=14336, event_retention_size=5)   # starter notebook
TOOL_OUTPUT_WORDS = [2000, 2000, 2000, 2000, 2000, 4000, 500, 500, 500]   # the 6th call returns a large test log
TASK_WORDS = 2500                             # system prompt + tool schemas + task statement, roughly as in the dev tasks
LOG: list[dict] = []
MAX_AGENT_CALLS = 10                          # the fake model answers in text (ends the run) after this many calls


class ContextWindowExceeded(Exception):
    """What vLLM returns as HTTP 400 and litellm raises as ContextWindowExceededError."""


def _words(req: LlmRequest) -> int:
    n = len(str(req.config.system_instruction or "").split())
    for c in req.contents:
        for p in c.parts or []:
            if p.text:
                n += len(p.text.split())
            if p.function_call:
                n += 5 + len(str(p.function_call.args).split())
            if p.function_response:
                n += 5 + len(str(p.function_response.response).split())
    return n


class FakeServer(BaseLlm):
    """Fake model + server: counts the prompt, applies vLLM's length rule, reports usage, always calls read_file."""
    model: str = "fake-gemma"

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        prompt = _words(llm_request)
        is_summary = not llm_request.config.tools   # ADK's summarizer request carries no tools
        max_out = (llm_request.config.max_output_tokens or 0) if not is_summary else 0
        rec = {"kind": "summarizer" if is_summary else "agent", "prompt_tokens": prompt, "max_output_tokens": max_out}
        LOG.append(rec)
        if prompt + max_out > MAX_MODEL_LEN:
            rec["result"] = "REJECTED"
            raise ContextWindowExceeded(f"This model's maximum context length is {MAX_MODEL_LEN} tokens. However, you requested "
                                        f"{max_out} output tokens and your prompt contains {prompt} input tokens "
                                        f"({prompt} + {max_out} = {prompt + max_out} > {MAX_MODEL_LEN}).")
        rec["result"] = "ok"
        usage = types.GenerateContentResponseUsageMetadata(prompt_token_count=prompt, candidates_token_count=20,
                                                           total_token_count=prompt + 20)
        if is_summary:
            text = "Summary: the agent read several files and ran the tests; the bug is not fixed yet."
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]), usage_metadata=usage)
            return
        if sum(1 for r in LOG if r["kind"] == "agent") >= MAX_AGENT_CALLS:
            yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="Done.")]), usage_metadata=usage)
            return
        call = types.FunctionCall(name="read_file", args={"filepath": "src/module.py"})
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=call)]), usage_metadata=usage)


_calls = {"n": 0}


def read_file(filepath: str) -> dict:
    """Read a file from the workspace."""
    i = _calls["n"]
    _calls["n"] += 1
    n = TOOL_OUTPUT_WORDS[min(i, len(TOOL_OUTPUT_WORDS) - 1)]
    return {"filepath": filepath, "content": " ".join(["x"] * n)}


async def run(max_output_tokens: int) -> list[dict]:
    LOG.clear()
    _calls["n"] = 0
    fake = FakeServer()
    agent = LlmAgent(name="swe_agent", model=fake, instruction=" ".join(["rules"] * TASK_WORDS),
                     tools=[read_file], generate_content_config=types.GenerateContentConfig(max_output_tokens=max_output_tokens))
    app = App(name="repro", root_agent=agent, events_compaction_config=EventsCompactionConfig(**STARTER))
    runner = Runner(app=app, session_service=InMemorySessionService())
    sess = await runner.session_service.create_session(app_name="repro", user_id="u")
    msg = types.Content(role="user", parts=[types.Part(text="Problem Statement: fix the bug in src/module.py.")])
    try:
        async for _ in runner.run_async(user_id="u", session_id=sess.id, new_message=msg):
            pass
    except ContextWindowExceeded as e:
        LOG.append({"kind": "error", "detail": str(e)})
    return list(LOG)


def show(title: str, log: list[dict]) -> None:
    print(f"\n== {title}")
    print(f"{'#':>3}  {'request':<10} {'prompt':>7} {'+ max_out':>9} {'= total':>8}  result")
    k = 0
    for r in log:
        if r["kind"] == "error":
            print("     ->", r["detail"])
            continue
        k += 1
        tot = r["prompt_tokens"] + r["max_output_tokens"]
        note = "   (compaction: summarizer call)" if r["kind"] == "summarizer" else ""
        print(f"{k:>3}  {r['kind']:<10} {r['prompt_tokens']:>7} {r['max_output_tokens']:>9} {tot:>8}  {r['result']}{note}")


def main() -> int:
    starter = asyncio.run(run(16384))
    fixed = asyncio.run(run(8192))
    show("starter setting: max_output_tokens 16384 (effective prompt limit 32768 - 16384 = 16384)", starter)
    show("fix: max_output_tokens 8192 (effective prompt limit 24576)", fixed)
    rej = [i for i, r in enumerate(starter) if r.get("result") == "REJECTED"]
    ok = (bool(rej) and not any(r["kind"] == "summarizer" for r in starter[:rej[0]])
          and starter[rej[0]]["prompt_tokens"] > 16384
          and not any(r.get("result") == "REJECTED" for r in fixed) and any(r["kind"] == "summarizer" for r in fixed))
    print("\nREPRODUCED: the starter setting overflows before compaction runs; 8192 avoids it." if ok else "\nNOT REPRODUCED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
