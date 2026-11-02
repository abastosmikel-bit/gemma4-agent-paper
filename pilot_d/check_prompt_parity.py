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
MAX_TOOL_NODES = 20000
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
    p.add_argument("--tool-sample", type=int, default=2,
                   help="call the graph tools on at most this many tasks per repo (the prompt check covers every task); "
                        "search_similar_code on very large graphs (sympy: 39k nodes) takes minutes per call")
    a = p.parse_args()
    from swegemma.harness.agent_runner import build_agent_prompt
    from swegemma.models import load_tasks

    E = Path(a.export)
    tasks = load_tasks(E / "tasks.jsonl")
    meta = {json.loads(l)["instance_id"]: json.loads(l) for l in open(E / "heldout_meta.jsonl")}
    empty = tempfile.mkdtemp()
    rows, tooled = [], {}
    for t in tasks:
        cfg = SimpleNamespace(graph_dir=str(E / "graphs"), embeddings_dir=str(E / "embeddings"),
                              enable_sandbox_testing=True, budget=None)
        with_emb = SECTION in build_agent_prompt(t, cfg, "", declared_tools=GRAPH_TOOLS)
        cfg.embeddings_dir = empty
        without = SECTION in build_agent_prompt(t, cfg, "", declared_tools=GRAPH_TOOLS)
        gold = (meta.get(t.instance_id, {}).get("gold_nodes") or [None])[0]
        tc = {}
        gfile = E / "graphs" / f"{t.repo.split('/')[1]}_{t.base_commit}.json"
        n_nodes = len(json.load(open(gfile))["nodes"]) if gfile.exists() else 0
        if gold and with_emb and n_nodes > MAX_TOOL_NODES:
            # swegemma's embedding cache is an LRU of 50,000 entries filled with node ids AND node texts; above
            # ~25k nodes the ids are evicted and every per-node lookup in get_graph becomes a linear scan
            # (O(N^2) load: > 5 min for sympy's 39.5k nodes vs 1.2 s for 8.1k). Report instead of stalling.
            tc = {"skipped": f"graph has {n_nodes} nodes > {MAX_TOOL_NODES} (harness O(N^2) load)"}
        elif gold and with_emb and tooled.get(t.repo, 0) < a.tool_sample:
            tooled[t.repo] = tooled.get(t.repo, 0) + 1
            tc = tool_calls(t, gold, str(E / "graphs"), str(E / "embeddings"))
        rows.append({"instance_id": t.instance_id, "section_with_embeddings": with_emb,
                     "section_without_embeddings": without, "tools": tc})
    agg = {"tasks": len(rows),
           "section_present_with_embeddings": sum(r["section_with_embeddings"] for r in rows),
           "section_present_without_embeddings": sum(r["section_without_embeddings"] for r in rows),
           "tool_checked_tasks": sum(1 for r in rows if r["tools"] and "skipped" not in r["tools"]),
           "tool_skipped_large_graph": sum(1 for r in rows if "skipped" in r["tools"]),
           "search_similar_code_ok": sum(1 for r in rows if r["tools"].get("search_similar_code", {}).get("ok")),
           "get_code_neighbors_ok": sum(1 for r in rows if r["tools"].get("get_code_neighbors", {}).get("ok")),
           "tool_errors": sorted({v.get("error") for r in rows for v in r["tools"].values() if isinstance(v, dict) and v.get("error")})[:5]}
    print(json.dumps(agg, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps({"aggregate": agg, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
