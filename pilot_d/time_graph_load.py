"""Time swegemma's get_graph (graph + embeddings load) per repo of an export.

Shows the harness's O(N^2) load above ~25k nodes: embedding_utils._CACHE is an LRU of 50,000 entries filled with
node ids and node texts, so on large graphs the ids are evicted and each per-node lookup becomes a linear scan.
Usage: timeout 900 python pilot_d/time_graph_load.py EXPORT_DIR repo_short [repo_short ...]
(local measurement 2026-11-02: pyparsing 1,963 nodes 0.2 s; sqlglot 5,902 nodes 0.9 s; networkx 8,124 nodes 1.2 s;
sympy 39,539 nodes > 300 s, not finished)
"""
import glob
import json
import sys
import time

from swegemma.graph import graph_utils

E = sys.argv[1]
for short in sys.argv[2:]:
    f = sorted(glob.glob(f"{E}/graphs/{short}_*.json"))[0]
    base = f.rsplit("/", 1)[1].split("_", 1)[1][:-5]
    n = len(json.load(open(f))["nodes"])
    t = time.time()
    graph_utils.get_graph(repo_name=short, graph_dir=f"{E}/graphs", embeddings_dir=f"{E}/embeddings", base_commit=base)
    print(short, n, "nodes: get_graph", round(time.time() - t, 1), "s", flush=True)
