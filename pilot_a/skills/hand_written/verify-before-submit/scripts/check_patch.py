"""Pre-submit checklist. Runs inside the agent sandbox via run_skill_script.

Skill scripts start in a temporary directory, and in swegemma's subprocess sandbox
the literal path /workspace is only rewritten in shell commands, not inside Python
files. So we locate the repo from the launching shell's PWD / PYTHONPATH first.
Read-only: never stages anything (the harness's own .adk_exec_*.py temp file sits
in the workspace while this runs and must not end up in the index).
"""
import os
import re
import subprocess


def find_workspace():
    cands = [os.environ.get("PWD", "")] + os.environ.get("PYTHONPATH", "").split(os.pathsep) + ["/workspace"]
    for c in cands:
        if c and os.path.isdir(os.path.join(c, ".git")):
            return c
    return "/workspace"


WS = find_workspace()
PROTECTED = re.compile(
    r"(^|/)(tests?|testing)/|(^|/)test_[^/]*\.py$|_test\.py$|"
    r"(^|/)(conftest\.py|pytest\.ini|pyproject\.toml|setup\.cfg|tox\.ini)$"
)


def sh(cmd):
    r = subprocess.run(cmd, shell=True, cwd=WS, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


untracked = [f for f in sh("git ls-files --others --exclude-standard").splitlines()
             if f and not os.path.basename(f).startswith(".adk_exec_")]
changed = [f for f in sh("git diff --name-only HEAD").splitlines() if f] + untracked
print("== changed files")
print(sh("git diff --stat HEAD | tail -n 20") or "(none: your patch is EMPTY)")

print("== new files (scratch files belong in /tmp)")
print("\n".join(untracked) or "(none)")

print("== compile check")
bad = []
for f in changed:
    if f.endswith(".py"):
        try:
            with open(os.path.join(WS, f), encoding="utf-8") as fh:
                compile(fh.read(), f, "exec")  # in memory: leaves no __pycache__
        except (SyntaxError, ValueError, OSError) as e:
            bad.append(f)
            print(f"COMPILE FAIL: {f}: {e}")
print("COMPILE OK" if not bad else f"{len(bad)} file(s) do not compile")

print("== test/config files touched (graders discard these edits)")
print("\n".join(f for f in changed if PROTECTED.search(f)) or "(none)")
