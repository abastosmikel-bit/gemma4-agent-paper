"""Code graphs in the competition's released node-link schema, built with codegraph-loc.

Generator: codegraph-loc (Apache-2.0, https://github.com/danielmantiglia/codegraph-loc,
commit 1e8e0ab, D. Mantiglia 2026), used as a library: `cgl.graph.build_graph` +
`cgl.graph.official_view` (released id convention). This module adds a "released view"
reverse-engineered from the released graphs (schema notes in docs/FORMAT.md):
  * nodes: classes, functions, methods only (no module nodes); async defs dropped unless --fixed
  * node text: functions from the `def` keyword (original indentation kept); classes rendered as
    a skeleton: header, cleaned docstring (or `None`), then method signatures with `...` bodies
  * edges: type "calls", key 0, and SYMMETRIC: every containment pair and every resolved call is
    stored in both directions (in the released graphs 100% of edges have their reverse)
  * graph attribute repo_name = "<repo_short>_<base_commit>"; file name graphs/<repo_short>_<base_commit>.json

Usage:
  python common/graph_build.py build REPO_ROOT REPO_SHORT BASE_COMMIT OUT_DIR [--fixed]
  python common/graph_build.py fidelity OURS.json RELEASED.json
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


def _func_sig(n) -> str:
    s = f"def {n.name}({ast.unparse(n.args)})"
    if n.returns is not None:
        s += f" -> {ast.unparse(n.returns)}"
    return s + ":"


def _class_text(node: ast.ClassDef) -> str:
    bases = [ast.unparse(b) for b in node.bases] + [ast.unparse(k) for k in node.keywords]
    head = f"class {node.name}" + (f"({', '.join(bases)})" if bases else "") + ":"
    doc = ast.get_docstring(node)
    parts = [head, f'    """{doc}"""' if doc is not None else "    None", ""]
    for b in node.body:
        if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in b.decorator_list:
                parts.append(f"    @{ast.unparse(d)}")
            parts.append(f"    {_func_sig(b)}\n        ...\n")
    return "\n".join(parts).rstrip()


def _texts_for_file(path: Path) -> dict[int, str]:
    """Map definition line (the `def`/`class` keyword line) -> released-style text."""
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {}
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.ClassDef):
            out[n.lineno] = _class_text(n)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            seg = ast.get_source_segment(src, n) or ""
            out[n.lineno] = seg[seg.find("def ") if not seg.startswith("def ") else 0:] if "def " in seg else seg
    return out


RELEASED_CALL_RESOLUTIONS = {"module", "import", "local"}  # no self./typed/unique-name/super in released graphs


def released_ids_for_file(path: Path, module: str, fixed: bool = False) -> dict[int, str]:
    """Exact released id rule (reproduces 100% of node ids on the released requests/httpx graphs).

    The released generator keeps ONE "current class" variable, set on entering a class body and
    reset to None (not restored) on leaving it. So: classes -> <module>.<Class>; any def while a
    class is current -> <module>.<Class>.<name> (closures inside methods included); any def after a
    nested class body has closed inside an outer class -> <module>.<name> (the documented
    "methods labelled as module-level" bug). Async defs are skipped (released graphs have none).
    With fixed=True a proper class stack is used and async defs are kept.
    Returns {line of def/class keyword (and of each decorator): id}."""
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 50000))  # deeply nested generated code (see build)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return {}
    out: dict[int, str] = {}
    state = {"cls": None}
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef) if fixed else (ast.FunctionDef,)

    def mark(node, nid):
        out[node.lineno] = nid
        for d in node.decorator_list:
            out.setdefault(d.lineno, nid)

    def visit(node):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, ast.ClassDef):
                mark(ch, f"{module}.{ch.name}")
                prev = state["cls"]
                state["cls"] = ch.name
                visit(ch)
                state["cls"] = prev if fixed else None
            elif isinstance(ch, func_types):
                mark(ch, f"{module}.{state['cls']}.{ch.name}" if state["cls"] else f"{module}.{ch.name}")
                visit(ch)
            else:
                visit(ch)

    visit(tree)
    return out


def build(root: str, repo_short: str, base_commit: str, out_dir: str, fixed: bool = False) -> Path:
    """Node ids/texts from our AST rules; call resolution from codegraph-loc, re-keyed by (file, line)."""
    from cgl.graph import build_graph

    # Deeply nested generated code (e.g. sympy) exceeds the default recursion limit in the AST visitors.
    # Python >= 3.11 runs pure-Python recursion without consuming C stack, so a higher limit is safe.
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 50000))
    G0 = build_graph(root, module_scheme="official")  # package-relative names inside packages, else repo path
    rootp = Path(root)
    ids_cache: dict[str, dict[int, str]] = {}
    texts_cache: dict[str, dict[int, str]] = {}
    mapping, keep = {}, {}
    for n, a in G0.nodes(data=True):
        if a.get("kind") not in ("class", "function", "method") or not a.get("file"):
            continue
        f = a["file"]
        if f not in ids_cache:
            ids_cache[f] = released_ids_for_file(rootp / f, a.get("module"), fixed)
            texts_cache[f] = _texts_for_file(rootp / f)
        sl = a.get("start_line") or 0
        rid = ids_cache[f].get(sl)
        if rid is None:
            continue  # e.g. async def in faithful mode
        mapping[n] = rid
        if rid not in keep:  # released graphs collapse same-id defs into one node (first wins)
            text = next((texts_cache[f][ln] for ln in range(sl, sl + 50) if ln in texts_cache[f]), a.get("text", ""))
            keep[rid] = {"id": rid, "name": rid, "text": text}
    kind = {n: a.get("kind") for n, a in G0.nodes(data=True)}
    pairs = set()
    for u, v, a in G0.edges(data=True):
        if u not in mapping or v not in mapping:
            continue
        t = a.get("type")
        ok = (t == "calls" and (fixed or a.get("resolution") in RELEASED_CALL_RESOLUTIONS)) or \
             (t == "contains" and (fixed or (kind.get(u) == "class" and kind.get(v) == "method")))
        mu, mv = mapping[u], mapping[v]
        if ok and mu != mv:
            pairs.add((mu, mv))
            pairs.add((mv, mu))
    data = {"directed": True, "multigraph": True, "graph": {"repo_name": f"{repo_short}_{base_commit}"},
            "nodes": list(keep.values()),
            "edges": [{"type": "calls", "source": u, "target": v, "key": 0} for u, v in sorted(pairs)]}
    out = Path(out_dir) / f"{repo_short}_{base_commit}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data))
    return out


def fidelity(ours_path: str, released_path: str) -> dict:
    o, r = json.load(open(ours_path)), json.load(open(released_path))
    on, rn = {n["id"]: n for n in o["nodes"]}, {n["id"]: n for n in r["nodes"]}
    oe = {frozenset((e["source"], e["target"])) for e in o["edges"]}
    re_ = {frozenset((e["source"], e["target"])) for e in r["edges"]}
    common = set(on) & set(rn)
    re_in = {e for e in re_ if e <= set(on)}  # released edges whose endpoints we also have
    return {
        "released_nodes": len(rn), "our_nodes": len(on),
        "node_recall": round(len(common) / max(1, len(rn)), 4),
        "node_precision": round(len(common) / max(1, len(on)), 4),
        "text_exact_on_common": round(sum(on[i]["text"] == rn[i]["text"] for i in common) / max(1, len(common)), 4),
        "released_undirected_edges": len(re_), "our_undirected_edges": len(oe),
        "edge_recall": round(len(oe & re_) / max(1, len(re_)), 4),
        "edge_recall_on_shared_nodes": round(len(oe & re_in) / max(1, len(re_in)), 4),
        "edge_precision": round(len(oe & re_) / max(1, len(oe)), 4),
        "released_edges_all_reciprocal": all((e["target"], e["source"]) in {(x["source"], x["target"]) for x in r["edges"]}
                                             for e in r["edges"]),
    }


if __name__ == "__main__":
    if sys.argv[1] == "build":
        print(build(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], fixed="--fixed" in sys.argv))
    else:
        print(json.dumps(fidelity(sys.argv[2], sys.argv[3])))
