"""Download individual competition files without a local Kaggle token.

The session proxy injects the Kaggle credential for *.kaggle.com, so we call the
same endpoint the official `kaggle` client uses (competitions.CompetitionApiService/
DownloadDataFile) and follow the signed-URL redirect. Never commit what this downloads.

Usage: python -I common/kaggle_fetch.py DEST_DIR FILE [FILE ...]
       python -I common/kaggle_fetch.py --list            (prints every file name + size)
"""
import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

COMP = "gemma-4-developer-agent"
API = "https://api.kaggle.com/v1/competitions.CompetitionApiService/DownloadDataFile"
LIST = f"https://www.kaggle.com/api/v1/competitions/data/list/{COMP}"


def list_files():
    tok, out = None, []
    while True:
        url = LIST + (f"?pageToken={urllib.parse.quote(tok)}" if tok else "")
        d = json.loads(subprocess.run(["curl", "-sf", url], capture_output=True, text=True, check=True).stdout)
        out += d["files"]
        tok = d.get("nextPageToken")
        if not tok:
            return out


def fetch(name: str, dest: Path) -> int:
    """Two steps: POST for the signed storage URL, then a plain GET (a forced POST on the
    redirect gets 403 from storage.googleapis.com)."""
    dest = dest / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({"competitionName": COMP, "fileName": name})
    r = subprocess.run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code} %{redirect_url}",
         "-H", "Content-Type: application/json", "--data", body, API],
        capture_output=True, text=True)
    code, _, signed = r.stdout.partition(" ")
    if code != "302" or not signed:
        return int(code or 0)
    g = subprocess.run(["curl", "-s", "-o", str(dest), "-w", "%{http_code}", signed],
                       capture_output=True, text=True)
    return int(g.stdout or 0)


if __name__ == "__main__":
    if sys.argv[1] == "--list":
        for f in list_files():
            print(f["name"], f.get("totalBytes"))
        sys.exit(0)
    dest = Path(sys.argv[1])
    for n in sys.argv[2:]:
        print(fetch(n, dest), n)
