"""Task loading and gold-location extraction (reusable; no pilot-specific logic).

Nothing here writes task data anywhere: callers decide where outputs go.
Competition data (tasks.jsonl, snapshots) must stay out of git.
"""
from __future__ import annotations

import json
import tarfile
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .diffs import FileDiff, is_test_path, parse_unified_diff, required_test_names
from .locate import changed_scopes, module_path


def load_tasks(path: str | Path) -> list[dict]:
    out, seen = [], set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                t = json.loads(line)
                if t["instance_id"] not in seen:
                    seen.add(t["instance_id"])
                    out.append(t)
    return out


def read_snapshot_members(tgz: str | Path, wanted: set[str]) -> dict[str, str]:
    """Return {path: text} for the wanted repo-relative paths, reading the archive in one pass.
    Never extracts to disk and never executes anything from the archive."""
    found: dict[str, str] = {}
    want = set(wanted)
    with tarfile.open(tgz, mode="r|gz") as tf:
        for m in tf:
            name = m.name[2:] if m.name.startswith("./") else m.name
            if name in want and m.isfile():
                fh = tf.extractfile(m)
                if fh is not None:
                    found[name] = fh.read().decode("utf-8", errors="replace")
                if len(found) == len(want):
                    break
    return found


@dataclass
class GoldFunction:
    file: str
    qualname: str  # relative to module, e.g. "APIRoute.__init__"
    dotted: str  # e.g. "fastapi.routing.APIRoute.__init__" (graph-node style)
    kind: str  # "function" | "class"
    def_line: int


@dataclass
class GoldLocations:
    instance_id: str
    repo: str
    src_files: list[str] = field(default_factory=list)  # non-test .py files changed by the gold patch
    new_src_files: list[str] = field(default_factory=list)  # subset absent from the base snapshot
    other_files: list[str] = field(default_factory=list)  # non-.py or test files in the gold patch
    functions: list[GoldFunction] = field(default_factory=list)
    module_level_files: list[str] = field(default_factory=list)  # files with changes outside any def/class
    test_files: list[str] = field(default_factory=list)
    new_test_files: list[str] = field(default_factory=list)  # test files absent from the base snapshot
    test_names: list[str] = field(default_factory=list)  # scorer-required test functions
    gold_added: int = 0
    gold_removed: int = 0
    parse_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def diff_scopes(diff_text: str, snapshot_tgz: str | Path, texts: dict[str, str] | None = None) -> list[str]:
    """Dotted names of the def/class scopes (in the base snapshot) changed by any diff,
    e.g. an agent's patch. Module-level changes are reported as '<module>:<path>'."""
    fds = [fd for fd in parse_unified_diff(diff_text) if fd.path.endswith(".py") and fd.old_path]
    if texts is None:
        texts = read_snapshot_members(snapshot_tgz, {fd.path for fd in fds})
    out: list[str] = []
    for fd in fds:
        if fd.path not in texts:
            continue
        try:
            scopes, mod_level = changed_scopes(texts[fd.path], fd)
        except SyntaxError:
            continue
        mod = module_path(fd.path)
        out += [f"{mod}.{s.qualname}" if mod else s.qualname for s in scopes]
        if mod_level:
            out.append(f"<module>:{fd.path}")
    return out


def gold_locations(task: dict, snapshot_tgz: str | Path | None) -> GoldLocations:
    """Derive gold file(s), enclosing function(s) and required test names for one task.

    Uses only *locations* from the gold patch (paths, line numbers) and test
    names from test_patch; the base-file AST comes from the snapshot.
    If snapshot_tgz is None, function-level fields stay empty.
    """
    g = GoldLocations(task["instance_id"], task["repo"])
    fdiffs: list[FileDiff] = parse_unified_diff(task["patch"])
    tdiffs: list[FileDiff] = parse_unified_diff(task["test_patch"])
    py_src = [fd for fd in fdiffs if fd.path.endswith(".py") and not is_test_path(fd.path)]
    g.src_files = list(dict.fromkeys(fd.path for fd in py_src))
    g.other_files = [fd.path for fd in fdiffs if fd not in py_src]
    g.gold_added = sum(fd.added for fd in fdiffs)
    g.gold_removed = sum(fd.removed for fd in fdiffs)
    g.test_files = list(dict.fromkeys(fd.path for fd in tdiffs if fd.new_path))
    g.test_names = required_test_names(task["test_patch"])

    if snapshot_tgz is None:
        return g
    wanted = {fd.path for fd in py_src if fd.old_path} | set(g.test_files)
    texts = read_snapshot_members(snapshot_tgz, wanted)
    g.new_test_files = [p for p in g.test_files if p not in texts]
    for fd in py_src:
        if fd.path not in texts:
            g.new_src_files.append(fd.path)
            continue
        try:
            scopes, mod_level = changed_scopes(texts[fd.path], fd)
        except SyntaxError as e:  # pragma: no cover - base files should parse
            g.parse_errors.append(f"{fd.path}: {e}")
            continue
        mod = module_path(fd.path)
        for s in scopes:
            g.functions.append(GoldFunction(fd.path, s.qualname, f"{mod}.{s.qualname}" if mod else s.qualname, s.kind, s.def_line))
        if mod_level:
            g.module_level_files.append(fd.path)
    return g
