"""Fill problem_statement / created_at from GitHub (issue first, PR body as fallback).

Run where api.github.com is reachable (Kaggle notebook with internet, or a laptop). Optional
GITHUB_TOKEN env var raises the rate limit; unauthenticated (60 req/h) suffices for ~25 tasks.

problem_statement follows the SWE-bench convention: "<title>\n<body>". created_at is the issue's
creation time (contamination dating). Provenance is recorded in meta: issue | pr_body.

Usage: python common/github_text.py TASKS.jsonl META.jsonl OUT_TASKS.jsonl OUT_META.jsonl
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


def gh(path: str) -> dict | None:
    req = urllib.request.Request(f"https://api.github.com{path}",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "heldout-builder"})
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    for attempt in range(4):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (403, 429):
                time.sleep(min(60, 2 ** attempt * 5))
                continue
            raise
    return None


def main():
    tasks = [json.loads(l) for l in open(sys.argv[1])]
    meta = {m["instance_id"]: m for m in map(json.loads, open(sys.argv[2]))}
    with open(sys.argv[3], "w") as ft, open(sys.argv[4], "w") as fm:
        for t in tasks:
            m = meta[t["instance_id"]]
            text, src, created = None, None, None
            for n in list(m.get("issue_refs", [])) + list(m.get("issue_refs_in_tests", [])):
                it = gh(f"/repos/{t['repo']}/issues/{n}")
                if it and "pull_request" not in it:  # a real issue, not a PR
                    text, src, created = f"{it['title']}\n{it.get('body') or ''}", f"issue#{n}", it["created_at"]
                    break
            if text is None and m.get("pr_number"):
                pr = gh(f"/repos/{t['repo']}/pulls/{m['pr_number']}")
                if pr:
                    text, src, created = f"{pr['title']}\n{pr.get('body') or ''}", f"pr_body#{m['pr_number']}", pr["created_at"]
            if text is not None:
                t["problem_statement"], t["created_at"] = text.replace("\r\n", "\n"), created
                m.update(needs_issue_text=False, problem_statement_source=src)
            ft.write(json.dumps(t) + "\n")
            fm.write(json.dumps(m) + "\n")
            print(t["instance_id"], src, flush=True)


if __name__ == "__main__":
    main()
