"""Check the missing-embeddings confound is fixed: same prompt section and working graph tools as dev tasks.

For every task of an export (Level A layout) this calls the harness's OWN code:
  * swegemma.harness.agent_runner.build_agent_prompt with the sample agent's declared graph tools, once with the
    export's embeddings dir and once with an empty one: is "## Code Intelligence Tools" present?
  * SwegemmaContext(...).create_tools() offline (no sandbox): search_similar_code and get_code_neighbors on the
    task's first gold node (from heldout_meta.jsonl): status ok and non-empty results?
Prints aggregate counts; --dev TASKS.jsonl GRAPHS EMB runs the same check on dev tasks for comparison.

Usage: python pilot_d/check_prompt_parity.py EXPORT_DIR [--out RESULT.json]
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

SECTION = "## Code Intelligence Tools"
GRAPH_TOOLS = ("search_similar_code", "get_code_neighbors", "get_code_subgraph")


def tool_calls(task, node: str, graph_dir: str, emb_dir: str) -> dict:
    from swegemma.context import SwegemmaContext

    ctx = SwegemmaContext(docker_manager=None, task=task, repo=task.repo, graph_dir=graph_dir, embeddings_dir=emb_dir)
    tools = ctx.create_tools()
    out = {}
    for name, args in (("search_similar_code", {"query": node}), ("get_code_neighbors", {"node": node})):
        fn = next((f for k, f in tools.items() if name in k), None)
        try:
            r = fn(**args)
            r = json.loads(r) if isinstance(r, str) else r
            items = r.get("results") or r.get("neighbors") or r.get("similar_nodes") or r.get("matches") or []
            out[name] = {"ok": r.get("status") == "ok" and len(items) > 0, "n": len(items),
                         "keys": sorted(r)[:6]}
        except Exception as e:  # report, do not hide
            out[name] = {"ok": False, "error": f"{type(e).__name__}: {e}"[:120]}
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("export")
    p.add_argument("--out")
    a = p.parse_args()
    from swegemma.harness.agent_runner import build_agent_prompt
    from swegemma.models import load_tasks

    E = Path(a.export)
    tasks = load_tasks(E / "tasks.jsonl")
    meta = {json.loads(l)["instance_id"]: json.loads(l) for l in open(E / "heldout_meta.jsonl")}
    empty = tempfile.mkdtemp()
    rows = []
    for t in tasks:
        cfg = SimpleNamespace(graph_dir=str(E / "graphs"), embeddings_dir=str(E / "embeddings"),
                              enable_sandbox_testing=True, budget=None)
        with_emb = SECTION in build_agent_prompt(t, cfg, "", declared_tools=GRAPH_TOOLS)
        cfg.embeddings_dir = empty
        without = SECTION in build_agent_prompt(t, cfg, "", declared_tools=GRAPH_TOOLS)
        gold = (meta.get(t.instance_id, {}).get("gold_nodes") or [None])[0]
        tc = tool_calls(t, gold, str(E / "graphs"), str(E / "embeddings")) if gold and with_emb else {}
        rows.append({"instance_id": t.instance_id, "section_with_embeddings": with_emb,
                     "section_without_embeddings": without, "tools": tc})
    agg = {"tasks": len(rows),
           "section_present_with_embeddings": sum(r["section_with_embeddings"] for r in rows),
           "section_present_without_embeddings": sum(r["section_without_embeddings"] for r in rows),
           "search_similar_code_ok": sum(1 for r in rows if r["tools"].get("search_similar_code", {}).get("ok")),
           "get_code_neighbors_ok": sum(1 for r in rows if r["tools"].get("get_code_neighbors", {}).get("ok")),
           "tool_errors": sorted({v.get("error") for r in rows for v in r["tools"].values() if v.get("error")})[:5]}
    print(json.dumps(agg, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps({"aggregate": agg, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
