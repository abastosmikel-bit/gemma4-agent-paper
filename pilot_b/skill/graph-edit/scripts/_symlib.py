"""Symbol-addressed view/edit of Python source. Stdlib only; runs inside the task sandbox.

Symbols are addressed by dotted name, as the code-graph tools print them
(pkg.module.Class.method), or by `path/to/file.py:Class.method`, or by a unique suffix
(`Class.method`). Both the true nested name and the graph's own (flattened) name resolve.
Spans are recomputed from the current file with `ast` on every call, so earlier edits never
leave stale offsets.
"""
from __future__ import annotations

import ast
import difflib
import json
import os
import re
import sys
import textwrap

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", "build", "dist", ".tox",
             "site-packages", ".pytest_cache", ".mypy_cache"}
STRIP_PREFIXES = ("src/", "docs_src/")
MAX_OUT = 6000
DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
KIND = {ast.FunctionDef: "def", ast.AsyncFunctionDef: "async def", ast.ClassDef: "class"}


class SymError(Exception):
    def __init__(self, error_type: str, message: str, **details):
        super().__init__(message)
        self.error_type, self.message, self.details = error_type, message, details


# ---------------------------------------------------------------- workspace / files
def find_root() -> str:
    cands = [os.environ.get("GRAPH_EDIT_ROOT"), "/workspace"]
    cands += (os.environ.get("PYTHONPATH") or "").split(os.pathsep)
    cands += [os.environ.get("PWD"), os.getcwd()]
    for c in cands:
        if c and os.path.exists(os.path.join(c, ".git")):
            return os.path.abspath(c)
    raise SymError("WorkspaceNotFound", "could not locate the repository root (/workspace)")


def module_name(rel: str) -> str:
    p = rel
    for pre in STRIP_PREFIXES:
        if p.startswith(pre):
            p = p[len(pre):]
            break
    parts = (p[:-3] if p.endswith(".py") else p).split("/")
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def iter_py(root: str):
    for dp, dns, fns in os.walk(root):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS and not d.startswith("."))
        for fn in sorted(fns):
            if fn.endswith(".py"):
                yield os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/")


def read(root: str, rel: str) -> str:
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


def is_test_path(rel: str) -> bool:
    b = os.path.basename(rel)
    return b.startswith("test_") or b.endswith("_test.py") or b == "conftest.py" or \
        any(part in ("tests", "test", "testing") for part in rel.split("/")[:-1])


def is_aux_path(rel: str) -> bool:
    return rel.split("/")[0] in ("docs_src", "docs", "examples", "benchmarks", "scripts", "tests", "test")


# ---------------------------------------------------------------- symbol index
class Sym:
    __slots__ = ("qname", "gname", "rel", "node", "parent", "start", "end", "col")

    def __init__(self, qname, gname, rel, node, parent):
        self.qname, self.gname, self.rel, self.node, self.parent = qname, gname, rel, node, parent
        self.start = min([d.lineno for d in node.decorator_list] + [node.lineno])
        self.end, self.col = node.end_lineno, node.col_offset

    @property
    def kind(self):
        return KIND[type(self.node)]

    def brief(self):
        return {"symbol": self.qname, "kind": self.kind, "file": self.rel, "lines": [self.start, self.end]}


def index_file(root: str, rel: str, src: str | None = None) -> list[Sym]:
    src = read(root, rel) if src is None else src
    tree = ast.parse(src)
    mod = module_name(rel)
    out: list[Sym] = []
    state = {"cls": None}  # emulates the competition graph's (flattening) naming

    def visit(node, prefix, parent):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, DEF_TYPES):
                q = f"{prefix}.{ch.name}"
                if isinstance(ch, ast.ClassDef):
                    g = f"{mod}.{ch.name}"
                else:
                    g = f"{mod}.{state['cls']}.{ch.name}" if state["cls"] else f"{mod}.{ch.name}"
                s = Sym(q, g, rel, ch, parent)
                out.append(s)
                if isinstance(ch, ast.ClassDef):
                    state["cls"] = ch.name
                    visit(ch, q, s)
                    state["cls"] = None
                else:
                    visit(ch, q, s)
            else:
                visit(ch, prefix, parent)

    visit(tree, mod, None)
    return out


def _split_symbol(symbol: str):
    symbol = symbol.strip().strip("`'\"")
    m = re.match(r"^(?:/?workspace/)?(?P<path>[\w./-]+\.py)\s*(?:::?|#)\s*(?P<rest>[\w.]*)$", symbol)
    if m:
        return m.group("path").lstrip("/"), m.group("rest")
    if symbol.endswith(".py"):
        return symbol.lstrip("/"), ""
    return None, symbol


def resolve(root: str, symbol: str, kinds=None) -> Sym:
    symbol = symbol.strip()
    at_line = None
    m = re.match(r"^(.*?)@(\d+)$", symbol)            # name@<line> picks among same-named defs
    if m:
        symbol, at_line = m.group(1), int(m.group(2))
    path, dotted = _split_symbol(symbol)
    if path is not None:
        if not os.path.isfile(os.path.join(root, path)):
            raise SymError("FileNotFound", f"no such file: {path}")
        files = [path]
        if not dotted:
            raise SymError("NotASymbol", "a file was given; use show_symbol on the file to list its symbols")
        mod = module_name(path)
        full = f"{mod}.{dotted}" if mod and not dotted.startswith(mod + ".") else dotted
        cands = [s for s in index_file(root, path)
                 if full in (s.qname, s.gname) or s.qname.endswith("." + dotted) or s.gname.endswith("." + dotted)]
    else:
        full = dotted
        parts = dotted.split(".")
        files, cands = [], []
        mods = {}
        for rel in iter_py(root):
            mods.setdefault(module_name(rel), []).append(rel)
        for k in range(len(parts) - 1, 0, -1):          # longest module prefix wins
            mod = ".".join(parts[:k])
            if mod in mods:
                files = mods[mod]
                for rel in files:
                    cands += [s for s in _safe_index(root, rel) if dotted in (s.qname, s.gname)]
                break
        if not cands:                                     # suffix search across the repo
            suffix = "." + dotted
            for rel in sorted(set(r for v in mods.values() for r in v)):
                for s in _safe_index(root, rel):
                    if s.qname.endswith(suffix) or s.gname.endswith(suffix):
                        cands.append(s)
    if kinds:
        cands = [c for c in cands if c.kind in kinds]
    cands = list({(c.rel, c.start): c for c in cands}.values())
    if at_line is not None:
        hit = [c for c in cands if c.start <= at_line <= c.end]
        hit.sort(key=lambda c: c.end - c.start)          # innermost containing the line
        cands = hit[:1] or cands
    # ranking: exact true name > exact graph name > suffix; then library > tests > docs/examples
    for keep in (lambda c: c.qname == full, lambda c: c.gname == full,
                 lambda c: not is_test_path(c.rel), lambda c: not is_aux_path(c.rel)):
        if len(cands) > 1:
            kept = [c for c in cands if keep(c)]
            if kept:
                cands = kept
    if not cands:
        near = _near_misses(root, dotted, files)
        raise SymError("SymbolNotFound", f"no symbol named {symbol!r}", did_you_mean=near)
    if len(cands) > 1:
        raise SymError("AmbiguousSymbol", f"{len(cands)} definitions match {symbol!r}; pass a full dotted name, "
                       "file.py:Name, or append @<line> (a line inside the one you mean)",
                       candidates=[c.brief() for c in cands[:10]])
    return cands[0]


def _safe_index(root, rel):
    try:
        return index_file(root, rel)
    except (SyntaxError, UnicodeDecodeError, ValueError, OSError):
        return []


def _near_misses(root, dotted, files):
    last = dotted.split(".")[-1]
    pool = []
    for rel in (files or []):
        pool += [s.qname for s in _safe_index(root, rel)]
    if not pool:
        for rel in iter_py(root):
            if is_test_path(rel):
                continue
            pool += [s.qname for s in _safe_index(root, rel) if s.node.name.lower() == last.lower()
                     or last.lower() in s.node.name.lower()]
            if len(pool) > 4000:
                break
    close = difflib.get_close_matches(dotted, pool, n=5, cutoff=0.5)
    return close or pool[:5]


# ---------------------------------------------------------------- snippet normalisation
FENCE = re.compile(r"^\s*```[\w-]*\s*$")


def clean_snippet(code: str) -> str:
    lines = code.replace("\r\n", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    # strip a markdown fence only when it wraps the whole snippet (never inside docstrings)
    if len(lines) >= 2 and FENCE.match(lines[0]) and FENCE.match(lines[-1]):
        lines = lines[1:-1]
    if not lines:
        raise SymError("EmptySource", "new_source is empty")
    return "\n".join(lines)


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _norm_dump(tree) -> str:
    class N(ast.NodeTransformer):
        def visit_Constant(self, n):
            if isinstance(n.value, str):
                return ast.copy_location(ast.Constant(" ".join(n.value.split())), n)
            return n
    return ast.dump(N().visit(tree))


def parse_snippet(code: str) -> tuple[list[str], ast.AST]:
    """Return (lines at column 0 with 4-space body indent where possible, the single def/class node)."""
    code = clean_snippet(code)
    lines = code.split("\n")
    # "graph text" style: first line at col 0, body at its original deeper indentation
    if len(lines) > 1 and _indent(lines[0]) == 0:
        body_ind = [_indent(ln) for ln in lines[1:] if ln.strip()]
        if body_ind and min(body_ind) > 0:
            pass  # already parseable as-is; relative indentation fixed below
    text = textwrap.dedent("\n".join(lines))
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        raise SymError("SyntaxError", f"new_source does not parse: {e.msg} (snippet line {e.lineno})",
                       line=e.lineno, text=(e.text or "").rstrip()[:200])
    defs = [n for n in tree.body if isinstance(n, DEF_TYPES)]
    if len(tree.body) != 1 or len(defs) != 1:
        raise SymError("NotASingleDefinition",
                       "new_source must contain exactly one def/async def/class (decorators allowed); "
                       f"got {len(tree.body)} top-level statements",
                       top_level=[type(n).__name__ for n in tree.body][:10])
    node = defs[0]
    lines = text.split("\n")
    # normalise an over-indented body (e.g. copied from graph/search output) to +4
    if node.body:
        b0 = node.body[0].lineno - 1
        d = _indent(lines[b0])
        region = [ln for ln in lines[b0:] if ln.strip()]
        if d > 4 and all(_indent(ln) >= d for ln in region):
            cand = lines[:b0] + [ln[d - 4:] if ln.strip() else ln for ln in lines[b0:]]
            try:
                t2 = ast.parse("\n".join(cand))
                if _norm_dump(t2) == _norm_dump(tree):
                    lines, tree, node = cand, t2, t2.body[0]
            except SyntaxError:
                pass
    return lines, node


def reindent(lines: list[str], col: int) -> list[str]:
    return [(" " * col + ln) if ln.strip() else "" for ln in lines]


# ---------------------------------------------------------------- edit ops
def unified(rel, old, new, limit=MAX_OUT - 1500):
    d = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{rel}", f"b/{rel}", n=2))
    return d if len(d) <= limit else d[:limit] + "\n... [diff truncated]"


def check_compiles(src: str, rel: str):
    try:
        compile(src, rel, "exec", flags=ast.PyCF_ONLY_AST, dont_inherit=True)
        compile(src, rel, "exec", dont_inherit=True)
    except SyntaxError as e:
        raise SymError("SyntaxError", f"edited file would not compile: {e.msg} (file line {e.lineno}); file left unchanged",
                       line=e.lineno, text=(e.text or "").rstrip()[:200])


def write_checked(root, rel, old_src, new_src):
    if new_src == old_src:
        raise SymError("NoChange", "new_source is identical to the current source; nothing written")
    check_compiles(new_src, rel)
    with open(os.path.join(root, rel), "w", encoding="utf-8") as f:
        f.write(new_src)


def edit_symbol(root, symbol, new_source=None, allow_rename=False, old_string=None, new_string=None):
    target = resolve(root, symbol)
    old_src = read(root, target.rel)
    if old_string is not None:
        return _scoped_replace(root, target, old_src, old_string, new_string if new_string is not None else "")
    if new_source is None:
        raise SymError("MissingArgument", "give new_source (whole new definition) or old_string+new_string (change inside the symbol)")
    lines, node = parse_snippet(new_source)
    tk, nk = target.kind, KIND[type(node)]
    if (tk == "class") != (nk == "class"):
        raise SymError("KindMismatch", f"{target.qname} is a {tk}; new_source defines a {nk}")
    if node.name != target.node.name and not str(allow_rename).lower() in ("1", "true", "yes"):
        raise SymError("NameMismatch", f"new_source defines {node.name!r} but the target is {target.node.name!r}; "
                       "pass allow_rename=true to rename, or use insert_symbol to add a new definition")
    file_lines = old_src.split("\n")
    # keep existing decorators when the snippet has none
    start = target.start if node.decorator_list else target.node.lineno
    new_block = reindent(lines, target.col)
    new_lines = file_lines[:start - 1] + new_block + file_lines[target.end:]
    new_src = "\n".join(new_lines)
    write_checked(root, target.rel, old_src, new_src)
    return {"status": "ok", "symbol": target.qname, "file": target.rel,
            "old_lines": [start, target.end], "new_lines": [start, start + len(new_block) - 1],
            "diff": unified(target.rel, old_src, new_src)}


def _scoped_replace(root, target, old_src, old_string, new_string):
    """Replace old_string inside the symbol's span only; uniqueness is checked within the symbol."""
    lines = old_src.split("\n")
    a, b = target.start - 1, target.end
    span = "\n".join(lines[a:b])
    n = span.count(old_string)
    how = "exact"
    if n == 0:   # tolerate indentation drift: match line-by-line on stripped text, re-indent replacement
        ol = [x.strip() for x in old_string.strip("\n").split("\n")]
        sl_ = lines[a:b]
        hits = [i for i in range(len(sl_) - len(ol) + 1) if [x.strip() for x in sl_[i:i + len(ol)]] == ol]
        if len(hits) == 1:
            i = hits[0]
            base = _indent(sl_[i])
            nl_ = textwrap.dedent(new_string.strip("\n")).split("\n") if new_string.strip() else []
            rep = [(" " * base + x) if x.strip() else "" for x in nl_]
            new_span_lines = sl_[:i] + rep + sl_[i + len(ol):]
            new_src = "\n".join(lines[:a] + new_span_lines + lines[b:])
            write_checked(root, target.rel, old_src, new_src)
            return {"status": "ok", "symbol": target.qname, "file": target.rel, "match": "indent_flexible",
                    "diff": unified(target.rel, old_src, new_src)}
        n = len(hits)
        how = "flexible"
    if n == 0:
        raise SymError("NoMatch", f"old_string not found inside {target.qname} (lines {target.start}-{target.end}); "
                       "use show_symbol to see its current source")
    if n > 1:
        raise SymError("MultipleMatches", f"old_string occurs {n} times inside {target.qname} ({how} match); add context lines")
    new_span = span.replace(old_string, new_string, 1)
    new_src = "\n".join(lines[:a] + new_span.split("\n") + lines[b:])
    write_checked(root, target.rel, old_src, new_src)
    return {"status": "ok", "symbol": target.qname, "file": target.rel, "match": "exact",
            "diff": unified(target.rel, old_src, new_src)}


def insert_symbol(root, new_source, after=None, before=None, into=None):
    lines, node = parse_snippet(new_source)
    if sum(bool(x) for x in (after, before, into)) != 1:
        raise SymError("BadArguments", "give exactly one of after=<symbol>, before=<symbol> or into=<class symbol | file.py>")
    blank_after = 0
    if after or before:
        anchor = resolve(root, after or before)
        rel, col = anchor.rel, anchor.col
        siblings = _siblings(root, anchor)
        blank = 1 if anchor.parent is not None and anchor.parent.kind == "class" else 2
        if after:
            at = anchor.end
        else:
            at, blank_after, blank = anchor.start - 1, blank, 0
    else:
        path, dotted = _split_symbol(into)
        if path and not dotted:
            rel = path
            if not os.path.isfile(os.path.join(root, rel)):
                raise SymError("FileNotFound", f"no such file: {rel}")
            src = read(root, rel)
            col, at, blank = 0, len(src.rstrip("\n").split("\n")), 2
            siblings = [s.node.name for s in index_file(root, rel) if s.parent is None]
        else:
            cls = resolve(root, into, kinds={"class"})
            rel, at, blank = cls.rel, cls.end, 1
            col = cls.node.body[0].col_offset if cls.node.body else cls.col + 4
            siblings = [n.name for n in cls.node.body if isinstance(n, DEF_TYPES)]
    if node.name in siblings:
        raise SymError("AlreadyExists", f"{node.name!r} already exists in that scope; use edit_symbol to change it")
    old_src = read(root, rel)
    file_lines = old_src.split("\n")
    body = reindent(lines, col)
    new_block = [""] * blank + body + [""] * blank_after
    new_lines = file_lines[:at] + new_block + file_lines[at:]
    new_src = "\n".join(new_lines)
    write_checked(root, rel, old_src, new_src)
    first = at + blank + 1
    return {"status": "ok", "inserted": node.name, "file": rel, "new_lines": [first, first + len(body) - 1],
            "diff": unified(rel, old_src, new_src)}


def _siblings(root, anchor):
    if anchor.parent is None:
        return [s.node.name for s in index_file(root, anchor.rel) if s.parent is None]
    return [n.name for n in anchor.parent.node.body if isinstance(n, DEF_TYPES)]


def show_symbol(root, symbol, max_lines=150):
    max_lines = int(max_lines)
    path, dotted = _split_symbol(symbol)
    if path and not dotted:                          # outline of a file
        syms = index_file(root, path)
        return {"status": "ok", "file": path, "module": module_name(path),
                "symbols": [f"{s.kind} {s.qname}  [{s.start}-{s.end}]" for s in syms][:300]}
    s = resolve(root, symbol)
    src_lines = read(root, s.rel).split("\n")
    body = src_lines[s.start - 1:s.end]
    out = {"status": "ok", "symbol": s.qname, "kind": s.kind, "file": s.rel, "lines": [s.start, s.end]}
    if s.gname != s.qname:
        out["graph_name"] = s.gname
    if s.kind == "class":
        out["members"] = [f"{KIND[type(n)]} {n.name}  [{n.lineno}-{n.end_lineno}]" for n in s.node.body if isinstance(n, DEF_TYPES)]
    if len(body) > max_lines:
        body = body[:max_lines] + [f"... [{len(src_lines[s.start - 1:s.end]) - max_lines} more lines; "
                                   "show a member symbol instead]"]
        out["truncated"] = True
    out["source"] = textwrap.dedent("\n".join(body))
    return out


# ---------------------------------------------------------------- CLI glue
def parse_args(argv):
    """Accept --key value pairs (ADK dict args) and bare positionals."""
    opts, pos, i = {}, [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--":
            pos += argv[i + 1:]
            break
        if a.startswith("--") and "=" in a:
            k, v = a[2:].split("=", 1)
            opts[k.replace("-", "_")] = v
        elif a.startswith("--") and i + 1 < len(argv):
            opts[a[2:].replace("-", "_")] = argv[i + 1]
            i += 1
        else:
            pos.append(a)
        i += 1
    return opts, pos


def emit(obj):
    s = json.dumps(obj, ensure_ascii=False)
    if len(s) > MAX_OUT and "source" in obj:
        obj["source"] = obj["source"][: max(500, MAX_OUT - (len(s) - len(obj["source"])) - 200)] + "\n... [truncated]"
        obj["truncated"] = True
        s = json.dumps(obj, ensure_ascii=False)
    print(s)


def run(fn, required, aliases=None):
    opts, pos = parse_args(sys.argv[1:])
    for k, alts in (aliases or {}).items():
        for a in alts:
            if a in opts and k not in opts:
                opts[k] = opts.pop(a)
    for k in required:
        if k not in opts and pos:
            opts[k] = pos.pop(0)
    try:
        missing = [k for k in required if k not in opts]
        if missing:
            raise SymError("MissingArgument", f"missing argument(s): {', '.join(missing)}")
        emit(fn(find_root(), **opts))
    except SymError as e:
        emit({"status": "error", "error_type": e.error_type, "error_message": e.message, **e.details})
    except TypeError as e:
        emit({"status": "error", "error_type": "BadArguments", "error_message": str(e)})
