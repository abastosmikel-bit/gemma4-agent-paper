"""Does addressing an edit by symbol make a minimal old_string unique where file-wide it is not?

For every gold hunk (line-level opcode) that lies inside a def/class: take the minimal old_string a
model would write (the removed/changed lines; for a pure insertion, the line before it) and count its
occurrences in the whole file vs inside the innermost enclosing symbol. Aggregates only.

usage: python -m pilot_b.analysis.scoping
"""
from __future__ import annotations

import collections
import difflib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
from pilot_b.analysis.expressibility import git, sl, syms_of  # noqa: E402
from common.patches import file_diffs  # noqa: E402
from common.tasks import checkout, load_tasks, reset_checkout  # noqa: E402


def main():
    c = collections.Counter()
    for t in load_tasks():
        root = checkout(t)
        reset_checkout(root)
        fds = [fd for fd in file_diffs(t["patch"]) if fd["new_path"].endswith(".py") and not sl.is_test_path(fd["new_path"])]
        olds = {fd["old_path"]: sl.read(root, fd["old_path"]) for fd in fds if os.path.exists(os.path.join(root, fd["old_path"]))}
        git(root, "apply", "-", inp=t["patch"] + "\n")
        news = {p: sl.read(root, p) for p in olds}
        reset_checkout(root)
        for p, old in olds.items():
            osy = syms_of(old, p)
            if osy is None:
                continue
            ol, nl = old.split("\n"), news[p].split("\n")
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ol, nl, autojunk=False).get_opcodes():
                if tag == "equal":
                    continue
                inner = [s for s in osy if s[2] - 1 <= i1 and max(i2, i1 + 1) <= s[3]]
                if not inner:
                    continue
                q, k, s, e, _ = min(inner, key=lambda x: x[3] - x[2])
                chunk = ol[i1:i2] if i2 > i1 else ol[i1 - 1:i1]
                needle = "\n".join(chunk)
                if not needle.strip():
                    c["hunks.blank_old_text"] += 1
                    continue
                c["hunks"] += 1
                f_n = old.count(needle)
                s_n = "\n".join(ol[s - 1:e]).count(needle)
                c[f"file_{'unique' if f_n == 1 else 'ambiguous'}"] += 1
                c[f"symbol_{'unique' if s_n == 1 else 'ambiguous'}"] += 1
                if f_n > 1 and s_n == 1:
                    c["ambiguous_in_file_but_unique_in_symbol"] += 1
                if len(chunk) == 1:
                    c["single_line_needles"] += 1
    out = dict(c)
    out["share_file_ambiguous"] = c["file_ambiguous"] / c["hunks"]
    out["share_symbol_ambiguous"] = c["symbol_ambiguous"] / c["hunks"]
    with open(os.path.join(ROOT, "results", "scoping.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
