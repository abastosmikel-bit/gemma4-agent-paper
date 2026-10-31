"""Unified-diff parsing helpers (no task data, no pilot-specific logic).

Parses the `--- a/X / +++ b/X / @@ ... @@` diffs used in the competition's
`patch` and `test_patch` fields into per-file change records with old-side
line numbers, so callers can map changes onto the base snapshot.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

# Mirrors the scorer's notion of protected test files (HARNESS_README §8.1).
_TEST_DIR_PARTS = {"tests", "test", "testing"}


def is_test_path(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    return name.endswith(".py") and any(p in _TEST_DIR_PARTS for p in parts[:-1])


@dataclass
class Insertion:
    """Lines added after old line `after_old` (0 = at file start)."""

    after_old: int
    lines: list[str]


@dataclass
class FileDiff:
    old_path: str | None
    new_path: str | None
    removed_old_lines: list[int] = field(default_factory=list)  # old-side line numbers deleted/replaced
    insertions: list[Insertion] = field(default_factory=list)
    hunks: int = 0
    added: int = 0
    removed: int = 0
    all_hunks_from_zero: bool = True  # every hunk is "@@ -0,0 ..." (file absent on old side)

    @property
    def path(self) -> str:
        return self.new_path or self.old_path or ""

    @property
    def maybe_new_file(self) -> bool:
        return self.old_path is None or (self.hunks > 0 and self.all_hunks_from_zero)

    @property
    def deleted_file(self) -> bool:
        return self.new_path is None


def _strip_prefix(p: str) -> str | None:
    p = p.split("\t", 1)[0].strip()
    if p == "/dev/null":
        return None
    if p.startswith('"') and p.endswith('"'):
        p = p[1:-1]
    if p.startswith(("a/", "b/")):
        p = p[2:]
    return p


def parse_unified_diff(text: str) -> list[FileDiff]:
    """Parse a unified diff into FileDiff records (robust to missing `diff --git` headers)."""
    files: list[FileDiff] = []
    cur: FileDiff | None = None
    lines = text.splitlines()
    i = 0
    old_ln = new_ln = 0
    rem_old = rem_new = 0
    pending: Insertion | None = None

    def flush_pending() -> None:
        nonlocal pending
        if pending is not None and cur is not None:
            cur.insertions.append(pending)
        pending = None

    while i < len(lines):
        line = lines[i]
        in_hunk = rem_old > 0 or rem_new > 0
        if not in_hunk and line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            flush_pending()
            cur = FileDiff(old_path=_strip_prefix(line[4:]), new_path=_strip_prefix(lines[i + 1][4:]))
            files.append(cur)
            i += 2
            continue
        if not in_hunk and line.startswith("@@ ") and cur is not None:
            flush_pending()
            m = _HUNK_RE.match(line)
            if m:
                o_start = int(m.group(1))
                o_cnt = int(m.group(2)) if m.group(2) is not None else 1
                n_cnt = int(m.group(4)) if m.group(4) is not None else 1
                cur.hunks += 1
                if not (o_start == 0 and o_cnt == 0):
                    cur.all_hunks_from_zero = False
                # old_ln = number of the last old line consumed so far
                old_ln = o_start - 1 if o_cnt > 0 else o_start
                rem_old, rem_new = o_cnt, n_cnt
            i += 1
            continue
        if in_hunk and cur is not None:
            if line.startswith("\\"):  # "\ No newline at end of file"
                i += 1
                continue
            tag = line[:1]
            body = line[1:]
            if tag == "+":
                if pending is None or pending.after_old != old_ln:
                    flush_pending()
                    pending = Insertion(after_old=old_ln, lines=[])
                pending.lines.append(body)
                cur.added += 1
                rem_new -= 1
            elif tag == "-":
                flush_pending()
                old_ln += 1
                cur.removed_old_lines.append(old_ln)
                cur.removed += 1
                rem_old -= 1
            else:  # context (' ' or empty line inside hunk)
                flush_pending()
                old_ln += 1
                rem_old -= 1
                rem_new -= 1
            i += 1
            continue
        i += 1
    flush_pending()
    return files


_ADDED_TEST_DEF = re.compile(r"^\+\s*(?:async\s+)?def\s+(test_[A-Za-z0-9_]+)\s*\(", re.M)
_REMOVED_TEST_DEF = re.compile(r"^-\s*(?:async\s+)?def\s+(test_[A-Za-z0-9_]+)\s*\(", re.M)
_HUNK_HEADER_TEST = re.compile(r"^@@[^@]+@@\s*(?:async\s+)?def\s+(test_[A-Za-z0-9_]+)\b", re.M)
_CONTEXT_TEST_DEF = re.compile(r"^ \s*(?:async\s+)?def\s+(test_[A-Za-z0-9_]+)\s*\(", re.M)


def required_test_names(test_patch: str) -> list[str]:
    """Test function names the scorer requires to pass, derived from test_patch.

    Re-implements the documented rule of the scorer (swegemma 0.2.11,
    `_extract_test_functions_from_patch`): added `def test_*` lines if any;
    otherwise test functions named in hunk headers / context, minus removed ones.
    Verified equal to the scorer's function on all 129 dev tasks (see
    pilot_c/check_test_names.py).
    """
    if not test_patch:
        return []
    added = _ADDED_TEST_DEF.findall(test_patch)
    if added:
        return list(dict.fromkeys(added))
    removed = set(_REMOVED_TEST_DEF.findall(test_patch))
    headers = _HUNK_HEADER_TEST.findall(test_patch)
    context = _CONTEXT_TEST_DEF.findall(test_patch)
    ctx = set(context)
    out = []
    for fn in dict.fromkeys(headers + context):
        if fn in removed:
            continue
        if fn not in ctx and (any(r.startswith(fn) for r in removed) or any(c != fn and c.startswith(fn) for c in ctx)):
            continue
        out.append(fn)
    return out
