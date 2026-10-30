"""Exact emulation of how the competition graphs name nodes.

Reverse-engineered: the generator is an ast.NodeVisitor with only visit_ClassDef and
visit_FunctionDef. It keeps ONE "current class" variable that is set on entering a class and
reset to None on leaving it (not restored). Consequences:
  * async def is never a node (bodies are still descended, so defs nested in them are nodes);
  * nested defs are named module.[Class.]name, the enclosing function is dropped;
  * a class nested in a class is named module.Inner, and after any nested class ends, the outer
    class's remaining methods are named as module-level functions;
  * same-named defs collapse into one node (graph keys are names).
Reproduces 100% of node names on all graphs we checked (see pilot_b/analysis/graph_spans.py).
"""
from __future__ import annotations

import ast


class GraphNamer(ast.NodeVisitor):
    def __init__(self, module: str):
        self.module = module
        self.cls: str | None = None
        self.items: list[tuple[str, ast.AST]] = []   # (graph name, ast node), in visit order

    def visit_ClassDef(self, n: ast.ClassDef):
        self.cls = n.name
        self.items.append((f"{self.module}.{n.name}", n))
        self.generic_visit(n)
        self.cls = None

    def visit_FunctionDef(self, n: ast.FunctionDef):
        name = f"{self.module}.{self.cls}.{n.name}" if self.cls else f"{self.module}.{n.name}"
        self.items.append((name, n))
        self.generic_visit(n)


def graph_names(tree: ast.AST, module: str) -> list[tuple[str, ast.AST]]:
    v = GraphNamer(module)
    v.visit(tree)
    return v.items
