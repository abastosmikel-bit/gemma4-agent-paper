"""Map diff changes onto enclosing Python scopes (def/class) of the base file.

Given the base-commit source of a file and a parsed FileDiff, returns the
innermost enclosing function/class for every changed region, using `ast` on
the base file. Deleted/replaced lines map by line number; inserted blocks map
by their anchor line plus indentation (an insertion indented less than a
scope's body belongs to the parent scope).
"""
from __future__ import annotations

import ast
from dataclasses import dataclass

from .diffs import FileDiff


@dataclass(frozen=True)
class Scope:
    qualname: str  # e.g. "APIRoute.__init__" (relative to module)
    kind: str  # "function" | "class"
    start: int  # first line incl. decorators
    def_line: int
    end: int
    body_indent: int
    depth: int
    header_indent: int = 0


def module_path(file_path: str) -> str:
    """'src/requests/models.py' -> 'requests.models'; 'pkg/__init__.py' -> 'pkg'."""
    p = file_path[:-3] if file_path.endswith(".py") else file_path
    parts = [x for x in p.split("/") if x]
    if parts and parts[0] in ("src", "lib"):
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def collect_scopes(source: str) -> list[Scope]:
    tree = ast.parse(source)
    scopes: list[Scope] = []

    def visit(node: ast.AST, prefix: str, depth: int) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                q = f"{prefix}.{child.name}" if prefix else child.name
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                body_indent = child.body[0].col_offset if child.body else child.col_offset + 4
                kind = "class" if isinstance(child, ast.ClassDef) else "function"
                scopes.append(Scope(q, kind, start, child.lineno, child.end_lineno or child.lineno, body_indent, depth, child.col_offset))
                visit(child, q, depth + 1)
            else:
                visit(child, prefix, depth)

    visit(tree, "", 0)
    return scopes


def _innermost(scopes: list[Scope], line: int) -> list[Scope]:
    """Scopes containing `line`, outermost first."""
    return sorted((s for s in scopes if s.start <= line <= s.end), key=lambda s: s.depth)


def _indent(s: str) -> int:
    return len(s) - len(s.lstrip(" \t"))


def report_scope(chain: list[Scope]) -> Scope | None:
    """Collapse a containment chain to what a developer would name:
    the outermost function (methods count as functions), or the innermost class
    if the change is in a class body outside any method."""
    if not chain:
        return None
    for s in chain:
        if s.kind == "function":
            return s
    return chain[-1]


def changed_scopes(source: str, fd: FileDiff) -> tuple[list[Scope], bool]:
    """Return (scopes touched by the diff, touches_module_level_code)."""
    scopes = collect_scopes(source)
    src_lines = source.splitlines()
    hits: dict[str, Scope] = {}
    module_level = False

    def last_code_line_at_or_before(n: int) -> int:
        while n >= 1 and (n > len(src_lines) or not src_lines[n - 1].strip()):
            n -= 1
        return n

    for ln in fd.removed_old_lines:
        s = report_scope(_innermost(scopes, ln))
        if s is None:
            module_level = True
        else:
            hits.setdefault(s.qualname, s)

    removed = set(fd.removed_old_lines)
    for ins in fd.insertions:
        code = [x for x in ins.lines if x.strip()]
        if not code:
            continue
        ind = _indent(code[0])
        if ins.after_old in removed:
            # replacement: the new lines take the place of removed ones, so they may
            # sit at a scope's header level (e.g. an edited decorator or signature)
            chain = [s for s in _innermost(scopes, ins.after_old) if s.header_indent <= ind]
        else:
            anchor = last_code_line_at_or_before(ins.after_old)
            chain = [s for s in _innermost(scopes, anchor) if s.body_indent <= ind] if anchor >= 1 else []
        s = report_scope(chain)
        if s is None:
            module_level = True
        else:
            hits.setdefault(s.qualname, s)

    ordered = sorted(hits.values(), key=lambda s: s.def_line)
    return ordered, module_level
