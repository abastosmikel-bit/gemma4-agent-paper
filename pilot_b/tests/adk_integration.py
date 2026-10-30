"""Offline integration check through the REAL harness code paths (no GPU, no model).

1. adk_submission.validate_directory + compile_submission accept a submission with the skill.
2. google.adk's skill-script wrapper + adk_eval_core's AdkSandboxCodeExecutor run the scripts
   against a repo checkout, and the edit shows up in `git diff`, i.e. the submitted patch.

usage (in a venv with the 4 harness wheels installed):
  python pilot_b/tests/adk_integration.py <repo_checkout_with_.git> <sample_submission_dir>
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILL = os.path.join(ROOT, "pilot_b", "skill", "graph-edit")


def check_compile(sample_dir: str) -> None:
    from adk_submission import validate_directory, compile_submission
    from adk_submission.registry import ModelRegistry
    d = tempfile.mkdtemp()
    sub = os.path.join(d, "sub")
    shutil.copytree(sample_dir, sub)
    shutil.rmtree(os.path.join(sub, "adapters"), ignore_errors=True)
    for dp, _, fns in os.walk(sub):
        for fn in fns:
            if fn.endswith(".yaml"):
                p = os.path.join(dp, fn)
                t = open(p).read()
                t = re.sub(r"^(\s*model:\s*).*$", r"\g<1>gemma-4-e4b-it-qat-w4a16-ct", t, flags=re.M)
                t = re.sub(r"^\s*adapter:\s*.*\n?", "", t, flags=re.M)
                open(p, "w").write(t)
    shutil.copytree(SKILL, os.path.join(sub, "skills", "graph-edit"), ignore=shutil.ignore_patterns("__pycache__"))
    with open(os.path.join(sub, "agent.yaml"), "a") as f:
        f.write("\nskills:\n  - skills/graph-edit\n")
    validate_directory(sub)
    print("validate_directory: ok")
    models = ModelRegistry()
    models.register("gemma-4-e4b-it-qat-w4a16-ct", "gemini-2.5-flash")   # never called offline
    tools = {}
    for name in ["run_command", "read_file", "edit_file", "write_file", "get_status", "submit_patch",
                 "get_code_neighbors", "search_similar_code", "get_code_subgraph"]:
        def _f(x: str = "") -> str:
            return "{}"
        _f.__name__ = name
        tools[name] = _f
    agent = compile_submission(submission_dir=sub, tool_registry=tools, model_registry=models)
    names = [type(t).__name__ for t in agent.tools]
    assert "SkillToolset" in names, names
    print("compile_submission: ok, root tools:", names)


async def check_script_path(repo: str) -> None:
    from google.adk.skills import load_skill_from_dir
    from google.adk.tools.skill_toolset import _SkillScriptCodeExecutor
    from adk_eval_core.sandbox.base import AdkSandboxCodeExecutor
    from adk_eval_core.sandbox.subprocess_sandbox import SubprocessSandbox
    skill = load_skill_from_dir(SKILL)
    box = SubprocessSandbox(work_dir=repo)
    box.initialize()
    ex = _SkillScriptCodeExecutor(AdkSandboxCodeExecutor(sandbox=box, timeout_seconds=60), 60)
    env_before = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = repo      # what swegemma's subprocess sandbox exports
    try:
        r = await ex.execute_script_async(None, skill, "scripts/show_symbol.py", {"symbol": "fastapi.encoders.decimal_encoder"})
        out = json.loads(r["stdout"])
        print("show_symbol:", out["status"], out.get("file"), out.get("lines"))
        r = await ex.execute_script_async(None, skill, "scripts/edit_symbol.py",
                                          {"symbol": "fastapi.encoders.decimal_encoder",
                                           "old_string": "return float(dec_value)", "new_string": "return float(dec_value)  # x"})
        out = json.loads(r["stdout"])
        print("edit_symbol:", out["status"], out.get("error_type", ""))
        diff = subprocess.run(["git", "-C", repo, "diff", "--stat"], capture_output=True, text=True).stdout
        print("git diff --stat:", diff.strip())
        assert "encoders.py" in diff
    finally:
        subprocess.run(["git", "-C", repo, "checkout", "-q", "--", "."])
        if env_before is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = env_before


if __name__ == "__main__":
    check_compile(sys.argv[2])
    asyncio.run(check_script_path(sys.argv[1]))
