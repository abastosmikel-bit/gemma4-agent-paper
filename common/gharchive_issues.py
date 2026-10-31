"""Recover verbatim issue/PR text for chosen repos from GH Archive (public hourly event dumps).

Why: the session cannot call the GitHub REST API for third-party repos. GH Archive events
(IssuesEvent, IssueCommentEvent, PullRequestEvent) embed the full issue/PR object incl. body.
Caveat: since 2025 the public feed is sampled (~4k events/hour), so coverage is partial;
the same mining step can use the GitHub API when available (see mine.py --issue-source api).

Usage: python -I common/gharchive_issues.py OUT.jsonl START_DATE END_DATE owner/repo [owner/repo ...]
Streams files, keeps only events for the given repos; never stores whole dumps.
"""
import gzip
import io
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

KEEP = {"IssuesEvent", "IssueCommentEvent", "PullRequestEvent"}


def hour_events(stamp, repos):
    url = f"https://data.gharchive.org/{stamp}.json.gz"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gemma4-pilot-d/0.1 (research; contact via repo)"})
        raw = urllib.request.urlopen(req, timeout=120).read()
    except Exception as e:
        return stamp, [], f"{type(e).__name__}"
    out = []
    with gzip.open(io.BytesIO(raw), "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"type":"' not in line:
                continue
            e = json.loads(line)
            if e.get("type") not in KEEP or e.get("repo", {}).get("name") not in repos:
                continue
            p = e["payload"]
            obj = p.get("issue") or p.get("pull_request") or {}
            out.append({
                "repo": e["repo"]["name"], "event": e["type"], "action": p.get("action"),
                "number": obj.get("number"), "is_pr": "pull_request" in p or "pull_request" in obj,
                "title": obj.get("title"), "body": obj.get("body"), "created_at": obj.get("created_at"),
                "closed_at": obj.get("closed_at"), "merged_at": obj.get("merged_at"),
                "user": (obj.get("user") or {}).get("login"), "seen_at": e.get("created_at"),
            })
    return stamp, out, None


def main():
    out, start, end, repos = sys.argv[1], sys.argv[2], sys.argv[3], set(sys.argv[4:])
    t, stop, stamps = datetime.fromisoformat(start), datetime.fromisoformat(end), []
    while t < stop:
        stamps.append(f"{t:%Y-%m-%d}-{t.hour}")
        t += timedelta(hours=1)
    n_ev = n_err = 0
    with open(out, "a") as fh, ThreadPoolExecutor(8) as ex:
        for stamp, evs, err in ex.map(lambda s: hour_events(s, repos), stamps):
            n_err += bool(err)
            for ev in evs:
                fh.write(json.dumps(ev) + "\n")
            n_ev += len(evs)
    print(json.dumps({"hours": len(stamps), "errors": n_err, "events": n_ev}))


if __name__ == "__main__":
    main()
