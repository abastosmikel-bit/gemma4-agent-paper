"""Build a task snapshot .tgz in the same layout as the competition's snapshots/<instance_id>.tgz.

Observed dev layout (schema only): archive rooted at './', a git repo whose history is
`git fast-export` of the source up to base_commit piped into `git fast-import` (so commit hashes
differ from upstream; tasks.jsonl keeps the upstream base_commit), branches `export_ref` and
`main` (checked out) at the base, .git/config with user agent@eval / Agent, clean working tree.
History depth is whatever the source clone has (dev snapshots range from 4 to 6k commits).

Usage: python -I common/snapshot.py REPO_DIR BASE_COMMIT OUT.tgz
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def run(*cmd: str, cwd: str | None = None, stdin=None, stdout=None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE)


def build_snapshot(repo_dir: str, base_commit: str, out_tgz: str) -> dict:
    out = Path(out_tgz)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "ws"
        dst.mkdir()
        run("git", "init", "-q", "-b", "main", str(dst))
        run("git", "-C", repo_dir, "branch", "-f", "export_ref", base_commit)
        exp = subprocess.Popen(["git", "-C", repo_dir, "fast-export", "--signed-tags=strip",
                                "--tag-of-filtered-object=drop", "--reencode=yes", "refs/heads/export_ref"],
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        run("git", "-C", str(dst), "fast-import", "--quiet", stdin=exp.stdout)
        if exp.wait() != 0:
            raise RuntimeError("git fast-export failed")
        run("git", "-C", str(dst), "checkout", "-q", "-B", "main", "export_ref")
        run("git", "-C", str(dst), "config", "user.email", "agent@eval")
        run("git", "-C", str(dst), "config", "user.name", "Agent")
        run("git", "-C", str(dst), "gc", "-q", "--prune=now")
        # Same top-level shape as dev archives: entries prefixed with './'
        run("tar", "-C", str(dst), "-czf", str(out), ".")
        n_commits = int(subprocess.run(["git", "-C", str(dst), "rev-list", "--count", "HEAD"],
                                       capture_output=True, text=True).stdout.strip() or 0)
    return {"snapshot_bytes": out.stat().st_size, "history_commits": n_commits}


if __name__ == "__main__":
    print(build_snapshot(sys.argv[1], sys.argv[2], sys.argv[3]))
