"""Task loading and source checkouts, shared by all pilots.

Data lives outside git. DATA_DIR (env var, default /tmp/kdata) is expected to hold:
  raw/tasks.jsonl                    competition tasks
  graphs/graphs/<repo>_<commit>.json competition code graphs (as `kaggle ... -f graphs/...` downloads them)
  up/<repo>/                         upstream git clones (fastapi, rich, requests, httpx)
Checkouts are git worktrees at wt/<commit>. We verified that snapshot tarballs equal the upstream
tree at base_commit (requests_6589, httpx_3672: 0 differing files), so upstream is used for CPU work.
"""
from __future__ import annotations

import json
import os
import subprocess

DATA_DIR = os.environ.get("DATA_DIR", "/tmp/kdata")
REPO_SHORT = {"fastapi/fastapi": "fastapi", "Textualize/rich": "rich", "psf/requests": "requests", "encode/httpx": "httpx"}
UPSTREAM_URL = {v: f"https://github.com/{k}.git" for k, v in REPO_SHORT.items()}


def load_tasks(path: str | None = None) -> list[dict]:
    path = path or os.path.join(DATA_DIR, "raw", "tasks.jsonl")
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def short_repo(task: dict) -> str:
    return REPO_SHORT[task["repo"]]


def graph_path(task: dict) -> str:
    return os.path.join(DATA_DIR, "graphs", "graphs", f"{short_repo(task)}_{task['base_commit']}.json")


def load_graph(task: dict) -> dict | None:
    p = graph_path(task)
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def checkout(task: dict) -> str:
    """Return a clean worktree of the task's repo at base_commit (created on first use)."""
    up = os.path.join(DATA_DIR, "up", short_repo(task))
    if not os.path.isdir(up):
        subprocess.run(["git", "clone", "-q", UPSTREAM_URL[short_repo(task)], up], check=True)
    wt = os.path.join(DATA_DIR, "wt", task["base_commit"])
    if not os.path.isdir(wt):
        subprocess.run(["git", "-C", up, "worktree", "add", "-f", "-q", "--detach", wt, task["base_commit"]], check=True)
    return wt


def reset_checkout(wt: str) -> None:
    subprocess.run(["git", "-C", wt, "checkout", "-q", "--", "."], check=True)
    subprocess.run(["git", "-C", wt, "clean", "-fdq"], check=True)
