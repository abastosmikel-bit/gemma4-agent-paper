"""Oracle-hint rendering for Pilot C (locations and test names only, never patch content).

Conditions (nested for localization, orthogonal for tests):
  O0      no hint
  O-file  gold source file(s)
  O-func  gold file(s) + enclosing function/class names (with def line)
  O-test  scorer-required test names + their test file(s)
  O-all   O-func + O-test

Hints are appended to problem_statement in a LOCAL copy of the tasks used only
by the local evaluation runner. They must never be placed in a submission.
"""
from __future__ import annotations

import copy

CONDITIONS = ("O0", "O-file", "O-func", "O-test", "O-all")
_HEADER = "## Location hints (verified ground truth for this task)"


def _file_lines(g: dict) -> list[str]:
    out = []
    new = set(g.get("new_src_files") or [])
    for f in g.get("src_files") or []:
        out.append(f"- The fix changes `{f}`" + (" (a new file that does not exist yet)." if f in new else "."))
    if not out:
        out.append("- The fix does not change any existing non-test Python source file.")
    return out


def _func_lines(g: dict) -> list[str]:
    out = []
    by_file: dict[str, list[dict]] = {}
    for fn in g.get("functions") or []:
        by_file.setdefault(fn["file"], []).append(fn)
    for f in g.get("src_files") or []:
        for fn in by_file.get(f, []):
            what = "class body of" if fn["kind"] == "class" else "function"
            out.append(f"- In `{f}`: {what} `{fn['dotted']}` (defined at line {fn['def_line']}).")
        if f in (g.get("module_level_files") or []):
            out.append(f"- In `{f}`: module-level code (imports, constants, or new top-level definitions).")
    return out


def _test_lines(g: dict) -> list[str]:
    names = g.get("test_names") or []
    files = g.get("test_files") or []
    new = set(g.get("new_test_files") or [])
    out = []
    for f in files:
        status = "this test file does not exist yet; it will be added when your fix is verified" if f in new \
            else "this test file exists; the listed tests may be new or changed"
        out.append(f"- Verification runs `{f}` ({status}).")
    if names:
        out.append("- Tests that must pass: " + ", ".join(f"`{n}`" for n in names) + ".")
    return out


def render_hint(g: dict, condition: str) -> str:
    if condition not in CONDITIONS:
        raise ValueError(condition)
    if condition == "O0":
        return ""
    lines: list[str] = []
    if condition in ("O-file", "O-func", "O-all"):
        lines += _file_lines(g)
    if condition in ("O-func", "O-all"):
        lines += _func_lines(g)
    if condition in ("O-test", "O-all"):
        lines += _test_lines(g)
    return "\n".join([_HEADER, *lines])


def rewrite_task(task: dict, g: dict, condition: str) -> dict:
    """Return a copy of `task` with the hint appended to problem_statement."""
    t = copy.deepcopy(task)
    hint = render_hint(g, condition)
    if hint:
        t["problem_statement"] = t["problem_statement"].rstrip() + "\n\n" + hint + "\n"
    return t
