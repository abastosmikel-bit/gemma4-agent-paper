"""AST index of a Python checkout, keyed by the same dotted names the competition graphs use.

Naming convention (inferred from the graphs, see pilot_b/analysis/graph_spans.py):
module = file path without ".py", "/" -> ".", with a leading "src/" or "docs_src/" removed
and a trailing "__init__" dropped; symbol = module + "." + enclosing class/def names.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field

STRIP_PREFIXES = ("src/", "docs_src/")
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".tox"}


@dataclass
class Symbol:
    qname: str
    path: str            # repo-relative file path
    kind: str            # "def" | "async def" | "class"
    lineno: int          # first line of the definition, decorators included (1-based)
    def_lineno: int      # line of the def/class keyword
    end_lineno: int
    col: int             # indentation of the def/class line
    parent_kind: str     # "module" | "class" | "def" | "async def"
    gname: str = ""      # graph-style name: enclosing *function* names are dropped (graphs flatten nested defs)
    node: ast.AST = field(repr=False, default=None)


def module_name(rel_path: str) -> str:
    p = rel_path
    for pre in STRIP_PREFIXES:
        if p.startswith(pre):
            p = p[len(pre):]
            break
    p = p[:-3] if p.endswith(".py") else p
    parts = p.split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def iter_py_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(".py"):
                full = os.path.join(dirpath, fn)
                yield os.path.relpath(full, root).replace(os.sep, "/")


def index_source(src: str, rel_path: str, module: str | None = None) -> list[Symbol]:
    """All class/def/async-def symbols of one file, nested ones included."""
    module = module if module is not None else module_name(rel_path)
    tree = ast.parse(src)
    out: list[Symbol] = []

    def visit(body, prefix, parent_kind, gprefix):
        for n in body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = {ast.FunctionDef: "def", ast.AsyncFunctionDef: "async def", ast.ClassDef: "class"}[type(n)]
                q = f"{prefix}.{n.name}" if prefix else n.name
                gq = f"{gprefix}.{n.name}" if gprefix else n.name
                start = min([d.lineno for d in n.decorator_list] + [n.lineno])
                out.append(Symbol(q, rel_path, kind, start, n.lineno, n.end_lineno, n.col_offset, parent_kind, gname=gq, node=n))
                visit(n.body, q, kind, gq if kind == "class" else gprefix)
            elif isinstance(n, (ast.If, ast.Try, ast.With, ast.For, ast.While)) or type(n).__name__ == "TryStar":
                # defs under `if TYPE_CHECKING:` / try-import blocks keep the enclosing prefix
                for sub in ("body", "orelse", "finalbody"):
                    visit(getattr(n, sub, []) or [], prefix, parent_kind, gprefix)
                for h in getattr(n, "handlers", []) or []:
                    visit(h.body, prefix, parent_kind, gprefix)

    visit(tree.body, module, "module", module)
    return out


def index_repo(root: str) -> tuple[dict[str, list[Symbol]], dict[str, str]]:
    """Return (qname -> symbols, rel_path -> parse error) for every .py file under root."""
    by_name: dict[str, list[Symbol]] = {}
    errors: dict[str, str] = {}
    for rel in iter_py_files(root):
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                src = f.read()
            syms = index_source(src, rel)
        except (SyntaxError, UnicodeDecodeError, ValueError) as e:
            errors[rel] = type(e).__name__
            continue
        for s in syms:
            by_name.setdefault(s.qname, []).append(s)
    return by_name, errors
