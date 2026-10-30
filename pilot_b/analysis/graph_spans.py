"""Step 2: can every graph node be mapped to an exact span in the snapshot source?

For each task's graph: resolve node name -> file (via module path) -> AST node (via the emulated
graph naming), then compare the node text with the source. Also quantify what the graph leaves out.
Writes aggregate numbers only (no code text) to results/graph_spans.json.

usage: python -m pilot_b.analysis.graph_spans
"""
from __future__ import annotations

import ast
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from common.graphnames import graph_names  # noqa: E402
from common.pyindex import iter_py_files, module_name  # noqa: E402
from common.tasks import checkout, load_graph, load_tasks, short_repo  # noqa: E402

LIB_ROOTS = {"fastapi": ("fastapi/",), "rich": ("rich/",), "requests": ("src/requests/", "requests/"), "httpx": ("httpx/", "src/")}


def is_lib(repo: str, rel: str) -> bool:
    return rel.startswith(LIB_ROOTS[repo])


def true_qnames(tree: ast.AST, module: str) -> dict[int, tuple[str, str]]:
    """id(node) -> (correct dotted name with every enclosing scope, kind)."""
    out = {}

    def visit(node, prefix):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = f"{prefix}.{ch.name}"
                out[id(ch)] = (q, {ast.FunctionDef: "def", ast.AsyncFunctionDef: "async def", ast.ClassDef: "class"}[type(ch)])
                visit(ch, q)
            else:
                visit(ch, prefix)

    visit(tree, module)
    return out


def enclosing_kinds(tree: ast.AST) -> dict[int, str]:
    """id(def node) -> 'module' | 'class' | 'function' (innermost enclosing scope)."""
    out = {}

    def visit(node, scope):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out[id(ch)] = scope
                visit(ch, "class" if isinstance(ch, ast.ClassDef) else "function")
            else:
                visit(ch, scope)

    visit(tree, "module")
    return out


def norm_ws(s: str) -> str:
    return "\n".join(line.rstrip() for line in s.strip().splitlines())


def analyse_task(task: dict) -> dict:
    repo = short_repo(task)
    g = load_graph(task)
    root = checkout(task)
    files = {}
    mod_files = collections.defaultdict(list)
    for rel in iter_py_files(root):
        mod_files[module_name(rel)].append(rel)
        with open(os.path.join(root, rel), encoding="utf-8", errors="replace") as f:
            files[rel] = f.read()

    # per-file: emulated graph names, AST nodes
    per_file = {}
    for rel, src in files.items():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            per_file[rel] = None
            continue
        per_file[rel] = (tree, graph_names(tree, module_name(rel)), true_qnames(tree, module_name(rel)), enclosing_kinds(tree))

    c = collections.Counter()
    # ---- (a) node -> span mapping
    for node in g["nodes"]:
        name, text = node["name"], node["text"]
        scope = None
        # longest module prefix that is a known module
        parts = name.split(".")
        cand_files = []
        for k in range(len(parts) - 1, 0, -1):
            mod = ".".join(parts[:k])
            if mod in mod_files:
                cand_files = mod_files[mod]
                break
        if not cand_files:
            c["node.fail.no_file"] += 1
            continue
        if len(cand_files) > 1:
            c["node.module_maps_to_multiple_files"] += 1
        hits = []
        for rel in cand_files:
            pf = per_file.get(rel)
            if pf is None:
                continue
            hits += [(rel, n) for gname, n in pf[1] if gname == name]
        scope = "lib" if any(is_lib(repo, r) for r in cand_files) else "other"
        c[f"node.{scope}.total"] += 1
        if not hits:
            c[f"node.{scope}.fail.name_not_found"] += 1
            continue
        is_class = isinstance(hits[0][1], ast.ClassDef)
        kind = "class" if is_class else "def"
        c[f"node.{scope}.{kind}"] += 1
        if len(hits) > 1:
            c[f"node.{scope}.{kind}.collision"] += 1   # several defs share the graph name; graph kept one
        if is_class:
            hdr_ok = any(text.split("\n", 1)[0] == ast.get_source_segment(files[r], n).split("\n", 1)[0] for r, n in hits)
            c[f"node.{scope}.class.header_matches" if hdr_ok else f"node.{scope}.class.header_differs"] += 1
            exact = sum(text == ast.get_source_segment(files[r], n) for r, n in hits)
            c[f"node.{scope}.class.text_verbatim"] += bool(exact)
            continue
        segs = [(r, n, ast.get_source_segment(files[r], n)) for r, n in hits]
        exact = [s for s in segs if s[2] == text]
        if len(exact) == 1:
            c[f"node.{scope}.def.exact_unique"] += 1
        elif len(exact) > 1:
            c[f"node.{scope}.def.exact_ambiguous"] += 1     # identical duplicates (e.g. overloads)
        elif any(norm_ws(s[2]) == norm_ws(text) for s in segs):
            c[f"node.{scope}.def.ws_only"] += 1
        else:
            c[f"node.{scope}.def.fail.text_differs"] += 1
        # plain text search (what a string-matching tool would do with the node text)
        n_occ = sum(files[r].count(text) for r in cand_files)
        c[f"node.{scope}.def.textsearch_{'unique' if n_occ == 1 else ('none' if n_occ == 0 else 'multi')}"] += 1

    # ---- (b) what the graph leaves out (all AST defs in the checkout)
    gnames = {n["name"] for n in g["nodes"]}
    for rel, pf in per_file.items():
        if pf is None:
            c["files.parse_error"] += 1
            continue
        tree, items, tq, enc = pf
        scope = "lib" if is_lib(repo, rel) else "other"
        emitted = {id(n): gn for gn, n in items}
        name_count = collections.Counter(gn for gn, _ in items)
        for nid, (q, kind) in tq.items():
            c[f"defs.{scope}.total"] += 1
            c[f"defs.{scope}.{kind}"] += 1
            if kind == "async def":
                c[f"defs.{scope}.missing.async"] += 1
                continue
            gn = emitted.get(nid)
            if gn is None or gn not in gnames:
                c[f"defs.{scope}.missing.other"] += 1
                continue
            if name_count[gn] > 1:
                c[f"defs.{scope}.collapsed_duplicate_name"] += 1
            if gn != q:
                why = "nested_in_function" if enc[nid] == "function" else ("class_reset_bug" if enc[nid] in ("class", "module") else "other")
                c[f"defs.{scope}.renamed.{why}"] += 1
        # module-level code: lines of top-level statements that are not def/class
        for st in tree.body:
            if not isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "import" if isinstance(st, (ast.Import, ast.ImportFrom)) else "other_stmt"
                c[f"modlevel.{scope}.{kind}_lines"] += st.end_lineno - st.lineno + 1
            elif isinstance(st, ast.ClassDef):
                for cs in st.body:
                    if not isinstance(cs, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        c[f"classlevel.{scope}.stmt_lines"] += cs.end_lineno - cs.lineno + 1
    c["edges.total"] += len(g["edges"])
    for e in g["edges"]:
        c[f"edges.type.{e['type']}"] += 1
    return dict(c)


def main():
    tasks = load_tasks()
    seen, totals, per_repo, no_graph = set(), collections.Counter(), collections.defaultdict(collections.Counter), []
    for t in tasks:
        if load_graph(t) is None:
            no_graph.append(t["instance_id"])
            continue
        if t["base_commit"] in seen:
            continue
        seen.add(t["base_commit"])
        r = analyse_task(t)
        totals.update(r)
        per_repo[short_repo(t)].update(r)
        print(t["instance_id"], r.get("node.lib.total"), r.get("node.lib.def.exact_unique"), flush=True)
    out = {"graphs_analysed": len(seen), "tasks_without_graph": no_graph, "totals": dict(sorted(totals.items())),
           "per_repo": {k: dict(sorted(v.items())) for k, v in per_repo.items()}}
    os.makedirs("results", exist_ok=True)
    with open("results/graph_spans.json", "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out["totals"], indent=1))


if __name__ == "__main__":
    main()
