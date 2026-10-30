"""Task loading and deterministic task splits.

No dependency on swegemma, so this also runs outside Kaggle. Only reads
tasks.jsonl; it never copies task content anywhere.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path

REPO_SHORT = {
    "fastapi/fastapi": "fastapi",
    "Textualize/rich": "rich",
    "psf/requests": "requests",
    "encode/httpx": "httpx",
}


def load_tasks(path: str | Path) -> list[dict]:
    """Return tasks.jsonl rows as dicts, in file order."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def repo_short(repo: str) -> str:
    return REPO_SHORT.get(repo, repo.split("/")[-1])


def by_repo(tasks: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for t in tasks:
        out[repo_short(t["repo"])].append(t)
    return dict(out)


def sample_ids(
    tasks: list[dict],
    repo: str,
    n: int,
    seed: int = 0,
    exclude: set[str] | None = None,
) -> list[str]:
    """Deterministically sample n instance_ids from one repo.

    Sorting before shuffling makes the split independent of file order, so
    every pilot that calls this with the same (repo, n, seed) gets the same ids.
    """
    exclude = exclude or set()
    pool = sorted(
        t["instance_id"]
        for t in tasks
        if repo_short(t["repo"]) == repo and t["instance_id"] not in exclude
    )
    if n > len(pool):
        raise ValueError(f"asked for {n} {repo} tasks, only {len(pool)} available")
    rng = random.Random(f"{repo}:{seed}")
    rng.shuffle(pool)
    return sorted(pool[:n])


def write_split(path: str | Path, splits: dict[str, list[str]]) -> None:
    """Write a split file (instance ids only, no task content)."""
    Path(path).write_text(json.dumps(splits, indent=2) + "\n", encoding="utf-8")


def read_split(path: str | Path) -> dict[str, list[str]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
