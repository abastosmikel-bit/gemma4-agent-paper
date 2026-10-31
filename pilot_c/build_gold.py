"""Derive gold locations (files, enclosing functions, required tests) for tasks.

usage:
  python -I pilot_c/build_gold.py --tasks tasks.jsonl --snapshots DIR --out gold.json [--ids a b ...]
         [--fetch]   # local only: download each missing snapshot with the kaggle CLI, then delete it

Output (gold.json) is DERIVED COMPETITION DATA: keep it out of git (it lives in
the data dir on Kaggle / outside the repo locally). Prints aggregate counts only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.tasks import gold_locations, load_tasks  # noqa: E402

COMP = "gemma-4-developer-agent"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--snapshots", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--fetch", action="store_true")
    a = ap.parse_args()

    tasks = load_tasks(a.tasks)
    if a.ids:
        keep = set(a.ids)
        tasks = [t for t in tasks if t["instance_id"] in keep]
    out_path = Path(a.out)
    done = json.loads(out_path.read_text()) if out_path.exists() else {}
    snap_dir = Path(a.snapshots)
    for i, t in enumerate(tasks, 1):
        iid = t["instance_id"]
        if iid in done:
            continue
        tgz = snap_dir / f"{iid}.tgz"
        tmp = None
        if not tgz.exists() and a.fetch:
            tmp = Path(tempfile.mkdtemp(prefix="snap_", dir=snap_dir))
            subprocess.run(["kaggle", "competitions", "download", COMP, "-f", f"snapshots/{iid}.tgz", "-p", str(tmp), "-q"],
                           check=True, capture_output=True)
            hits = list(tmp.rglob(f"{iid}.tgz"))
            tgz = hits[0] if hits else tgz
        g = gold_locations(t, tgz if tgz.exists() else None)
        done[iid] = g.to_dict()
        if tmp is not None:
            for p in sorted(tmp.rglob("*"), reverse=True):
                p.unlink() if p.is_file() else p.rmdir()
            tmp.rmdir()
        out_path.write_text(json.dumps(done))
        print(f"[{i}/{len(tasks)}] {iid}: files={len(g.src_files)} funcs={len(g.functions)} tests={len(g.test_names)}", flush=True)
    print(f"wrote {len(done)} records")


if __name__ == "__main__":
    main()
