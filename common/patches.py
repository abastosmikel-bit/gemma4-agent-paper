"""Minimal unified-diff parsing (file list + added/removed line counts)."""
from __future__ import annotations

import re

_HDR_OLD = re.compile(r"^--- (?:a/)?(.+?)(?:\t.*)?$")
_HDR_NEW = re.compile(r"^\+\+\+ (?:b/)?(.+?)(?:\t.*)?$")


def file_diffs(patch: str) -> list[dict]:
    """[{old_path, new_path, added, removed}] for each file section of a unified diff."""
    out: list[dict] = []
    lines = patch.split("\n")
    i = 0
    while i < len(lines):
        m_old = _HDR_OLD.match(lines[i])
        if m_old and i + 1 < len(lines) and _HDR_NEW.match(lines[i + 1]):
            old = m_old.group(1)
            new = _HDR_NEW.match(lines[i + 1]).group(1)
            cur = {"old_path": "/dev/null" if old == "/dev/null" else old,
                   "new_path": "/dev/null" if new == "/dev/null" else new, "added": 0, "removed": 0}
            out.append(cur)
            i += 2
            continue
        if out and not lines[i].startswith(("diff --git", "index ")):
            if lines[i].startswith("+") and not lines[i].startswith("+++"):
                out[-1]["added"] += 1
            elif lines[i].startswith("-") and not lines[i].startswith("---"):
                out[-1]["removed"] += 1
        i += 1
    return out
