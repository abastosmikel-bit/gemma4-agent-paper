"""LOCAL-ONLY dry run of a generated Kaggle notebook against a fake /kaggle tree.

Executes every code cell in-process (handling %%writefile), after:
  - /kaggle/input/... symlinked to a local mirror of the competition data + harness wheels
  - kaggle_runner.start_server replaced by the scripted mock LLM (no GPU)
  - install_wheelhouse skipped (harness already installed in this venv)
usage: python tests/dryrun_notebook.py <notebook.ipynb> <local_comp_dir> [TASKS override comma list]
"""
import json
import os
import sys
from pathlib import Path

nb_path, comp = Path(sys.argv[1]), Path(sys.argv[2])
override = sys.argv[3].split(",") if len(sys.argv) > 3 else None
inp = Path("/kaggle/input")
(inp / "competitions").mkdir(parents=True, exist_ok=True)
(inp / "datasets" / "metric" / "gemma-4-developer-agent-wheelhouse").mkdir(parents=True, exist_ok=True)
link = inp / "competitions" / "gemma-4-developer-agent"
if not link.exists():
    link.symlink_to(comp)
Path("/kaggle/working").mkdir(parents=True, exist_ok=True)

nb = json.loads(nb_path.read_text())
g: dict = {"__name__": "__main__"}
patched = False
for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] != "code":
        continue
    src = "".join(cell["source"])
    if src.startswith("%%writefile"):
        first, _, body = src.partition("\n")
        p = Path(first.split(None, 1)[1].strip())
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
        continue
    if "kr.install_wheelhouse(" in src:
        src = src.replace("kr.install_wheelhouse(", "(lambda **k: None)(")
    if override and "TASKS = " in src:
        src = src + f"\nTASKS = {override!r}\n"
    if "PLAN = [" in src:  # keep dry runs short: first model only, its conditions as configured
        src = src + "\nPLAN = PLAN[:1]\n"
    print(f"--- cell {i}: {src.strip().splitlines()[0][:80]}")
    exec(compile(src, f"cell{i}", "exec"), g)
    if not patched and "kr" in g:
        kr = g["kr"]
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from tests.mock_openai_server import make_script, serve

        def fake_start_server(agent_dir):
            from adk_submission import discover_adapters
            from adk_submission.registry import ModelRegistry
            from adk_submission.resolvers.generation import install_litellm_reasoning_patch
            from google.adk.models.lite_llm import LiteLlm
            from swegemma.config import ALLOWED_ADAPTER_EXTENSIONS
            import litellm
            litellm.drop_params = True
            install_litellm_reasoning_patch()
            model = kr.describe_agent(agent_dir)["model"]
            srv = serve(make_script("README.md"))
            reg = ModelRegistry()
            reg.register(model, LiteLlm(model="openai/mock", api_base="http://127.0.0.1:8001/v1", api_key="EMPTY"))
            ad = discover_adapters(str(agent_dir), adapter_extensions=ALLOWED_ADAPTER_EXTENSIONS)

            class S:
                def stop(self):
                    srv.shutdown()
                    srv.server_close()
            return S(), reg, ad, 0.0

        kr.start_server = fake_start_server
        patched = True
print("DRY RUN OK")
