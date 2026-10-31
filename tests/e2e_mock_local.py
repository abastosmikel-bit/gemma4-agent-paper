"""LOCAL-ONLY end-to-end test: real swegemma Evaluator + subprocess sandbox + scripted mock LLM.

Needs a local mirror of the competition layout (PILOT_DATA_DIR) and the harness wheels
installed. Exercises: hinted task copy -> prompt, tool loop, trace saving, trace parsing,
common metrics. Prints numbers only.
usage: PILOT_DATA_DIR=... PILOT_WORK_DIR=... python tests/e2e_mock_local.py <instance_id> [condition]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pilot_c import kaggle_runner as kr  # noqa: E402
from tests.mock_openai_server import _Handler, make_script, serve  # noqa: E402

iid = sys.argv[1]
cond = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "O-all"
kr.set_env()
kr.quiet_logs()
gold = kr.build_gold([iid])
g = gold[iid]
good = None
if "--good-edit" in sys.argv and g["functions"]:
    from common.tasks import read_snapshot_members
    fn = g["functions"][0]
    src = read_snapshot_members(kr.data_dir() / "snapshots" / f"{iid}.tgz", {fn["file"]})[fn["file"]].splitlines()
    body = next(l for l in src[fn["def_line"]:] if l.strip())  # first non-blank line after the def line
    good = (body, body + "  # mock edit")
srv = serve(make_script(g["src_files"][0], good))

from adk_submission import discover_adapters  # noqa: E402
from adk_submission.registry import ModelRegistry  # noqa: E402
from adk_submission.resolvers.generation import install_litellm_reasoning_patch  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS  # noqa: E402
import litellm  # noqa: E402

litellm.drop_params = True
install_litellm_reasoning_patch()
model = "gemma-4-e4b-it-qat-w4a16-ct"
agent_dir = kr.prepare_agent_dir(model, {"timeout_seconds": 60, "max_tool_calls": 20, "max_time_minutes": 5})
print(json.dumps(kr.describe_agent(agent_dir)))
models = ModelRegistry()
models.register(model, LiteLlm(model="openai/mock", api_base="http://127.0.0.1:8001/v1", api_key="EMPTY"))
adapters = discover_adapters(str(agent_dir), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)
run = kr.run_condition(agent_dir, models, adapters, [iid], gold, cond, 1, concurrency=1)
srv.shutdown()
print("REQUESTS", json.dumps(_Handler.log[:2]), "n_requests", len(_Handler.log))
print("ROW", json.dumps(run["rows"][0]))
print("AGG", json.dumps(run["aggregate"]))
