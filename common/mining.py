"""Mine candidate bug-fix tasks from a local git clone (no GitHub API needed).

Every filter step is counted so yield can be reported. Test/config classification mirrors
swegemma.harness.verification._is_protected_test_or_config_path, because that is what the
scorer strips from agent patches and resets before applying test_patch.

Usage:
  python -I common/mining.py REPO_DIR --repo owner/name --pkg PKGDIR --since 2026-05-01 \
      --out CANDIDATES.jsonl --funnel FUNNEL.json [--max-code-files 3] [--max-code-lines 200]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import PurePosixPath

PROTECTED_CONFIG = {"conftest.py", "pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg", ".pytest.ini",
                    "sitecustomize.py", "usercustomize.py", "_swegemma_stubs.py"}
FIX_RE = re.compile(r"^(fix|bug|bugfix|hotfix)\b|^BUG\b|^fix\(", re.I)
ISSUE_REF_RE = re.compile(r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\s*:?\s+#(\d+)", re.I)
TRAILING_PR_RE = re.compile(r"\(#(\d+)\)\s*$")
DOUBLE_REF_RE = re.compile(r"\(#(\d+)\)\s*\(#(\d+)\)\s*$")  # sqlglot style: (#issue) (#PR)
AI_RE = re.compile(r"\[CODEX\]|Co-authored-by:.*(Claude|Copilot|Codex|Devin|cursor)|Generated with \[?Claude|"
                   r"copilot-swe-agent|\bAI-assisted\b", re.I)


def is_test_path(p: str) -> bool:
    name = PurePosixPath(p).name
    parts = PurePosixPath(p).parts
    if not p.endswith(".py"):
        return any(d in ("tests", "test", "testing") for d in parts[:-1])  # fixtures/data under tests/
    return (name.startswith("test_") or name.endswith("_test.py")
            or any(d in ("tests", "test", "testing") for d in parts[:-1]))


def is_protected_config(p: str) -> bool:
    name = PurePosixPath(p).name
    return name in PROTECTED_CONFIG or name.endswith(".pth")


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=True).stdout


def to_dev_style(diff: str) -> str:
    """Rewrite `git diff` output into the dev set's style: only '--- a/X' / '+++ b/X' headers,
    '--- a/X' even for new files, '+++ b/X' even for deleted files, no trailing newline."""
    out, cur_old, cur_new = [], None, None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+) b/(.+)$", line)
            cur_old, cur_new = m.group(1), m.group(2)
            continue
        if line.startswith(("index ", "new file mode", "deleted file mode", "similarity index",
                            "rename from", "rename to", "old mode", "new mode")):
            continue
        if line.startswith("--- "):
            out.append(f"--- a/{cur_old}")
            continue
        if line.startswith("+++ "):
            out.append(f"+++ b/{cur_new}")
            continue
        out.append(line)
    return "\n".join(out)


def file_diff(repo: str, parent: str, commit: str, paths: list[str]) -> str:
    if not paths:
        return ""
    return git(repo, "diff", "--no-color", "--no-renames", "-U3", parent, commit, "--", *paths)


def mine(args) -> None:
    repo = args.repo_dir
    shas = git(repo, "log", "--first-parent", f"--since={args.since}", "--format=%H", args.branch).split()
    funnel = {"commits_since": len(shas)}
    steps = ["single_parent", "fix_message", "has_test_and_code_change", "has_py_test_file", "pkg_python_only",
             "no_protected_config_in_code", "size_ok"]
    for s in steps:
        funnel[s] = 0
    funnel["with_issue_ref_in_message"] = 0
    funnel["ai_authored_marker"] = 0
    out = open(args.out, "w")
    short = args.repo.split("/")[1].lower()
    for sha in shas:
        parents = git(repo, "log", "-1", "--format=%P", sha).split()
        if len(parents) != 1:
            continue
        funnel["single_parent"] += 1
        subject = git(repo, "log", "-1", "--format=%s", sha).strip()
        body = git(repo, "log", "-1", "--format=%b", sha)
        if not FIX_RE.search(subject):
            continue
        funnel["fix_message"] += 1
        parent = parents[0]
        names = [l.split("\t") for l in git(repo, "diff", "--no-renames", "--name-status", parent, sha).splitlines()]
        files = [n[-1] for n in names]
        test_files = [f for f in files if is_test_path(f)]
        code_files = [f for f in files if not is_test_path(f)]
        code_py = [f for f in code_files if f.endswith(".py")]
        if not test_files or not code_py:
            continue
        funnel["has_test_and_code_change"] += 1
        # The harness runs pytest on the .py files of test_patch; fixture-only test patches
        # make it pass a non-.py path to pytest ("no match"), so require a .py test file.
        if not any(f.endswith(".py") and PurePosixPath(f).name != "conftest.py" for f in test_files):
            continue
        funnel["has_py_test_file"] += 1
        # Code change must be Python inside the package; allow docs/changelog alongside (dropped from gold).
        pkg_files = [f for f in code_files if f.startswith(args.pkg + "/")]
        if any(not f.endswith(".py") for f in pkg_files) or not all(f in pkg_files for f in code_py):
            continue
        funnel["pkg_python_only"] += 1
        if any(is_protected_config(f) for f in code_files):
            continue
        funnel["no_protected_config_in_code"] += 1
        code_diff = file_diff(repo, parent, sha, pkg_files)
        added = sum(1 for l in code_diff.splitlines() if l.startswith(("+", "-")) and not l.startswith(("+++", "---")))
        if len(pkg_files) > args.max_code_files or added > args.max_code_lines:
            continue
        funnel["size_ok"] += 1
        m2 = DOUBLE_REF_RE.search(subject)
        issue_refs = sorted({int(x) for x in ISSUE_REF_RE.findall(subject + "\n" + body)}
                            | ({int(m2.group(1))} if m2 else set()))
        pr = int(m2.group(2)) if m2 else (int(TRAILING_PR_RE.search(subject).group(1)) if TRAILING_PR_RE.search(subject) else None)
        issue_refs = [i for i in issue_refs if i != pr]
        funnel["with_issue_ref_in_message"] += bool(issue_refs)
        ai = bool(AI_RE.search(subject + "\n" + body))
        funnel["ai_authored_marker"] += ai
        rec = {
            "instance_id": f"{short}_{pr or sha[:10]}",
            "repo": args.repo,
            "base_commit": parent,
            "fix_commit": sha,
            "pr_number": pr,
            "issue_refs": issue_refs,
            "subject": subject,
            "committed_at": git(repo, "log", "-1", "--format=%cI", sha).strip(),
            "authored_at": git(repo, "log", "-1", "--format=%aI", sha).strip(),
            "code_files": pkg_files,
            "test_files": test_files,
            "code_lines_changed": added,
            "ai_authored_marker": ai,
            "patch": to_dev_style(code_diff),
            "test_patch": to_dev_style(file_diff(repo, parent, sha, test_files)),
        }
        out.write(json.dumps(rec) + "\n")
    json.dump(funnel, open(args.funnel, "w"), indent=1)
    print(json.dumps(funnel))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("repo_dir")
    p.add_argument("--repo", required=True)
    p.add_argument("--pkg", required=True)
    p.add_argument("--since", default="2026-05-01")
    p.add_argument("--branch", default="HEAD")
    p.add_argument("--out", required=True)
    p.add_argument("--funnel", required=True)
    p.add_argument("--max-code-files", type=int, default=3)
    p.add_argument("--max-code-lines", type=int, default=200)
    mine(p.parse_args())
