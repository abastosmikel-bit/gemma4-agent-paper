"""Why did edit_file fail? Replays a run's file states from the snapshot and classifies every failed edit (CPU).

For each run: start from the task snapshot, apply the run's successful edit_file / write_file calls in trace order (with
the harness's own matcher, adk-eval-core `apply_replacement`, via pilot_c.probe.apply_edit), and test each FAILED edit's
old_string against
  current : the file as it was at that moment (if the harness matcher accepts it here, the tool, not the model, failed)
  base    : the file as it was before any of the agent's edits (accepted only here -> the model edited from a stale view)
  seen    : whether the old_string occurs verbatim in an earlier read_file output of the same file in this run
Otherwise the old_string never matched the file in any version the replay knows (the model wrote text that is not there).
Limitation: changes made through run_command (sed, scripts) are not replayed.
Inputs are private (traces from private/runs/..., snapshots); the output is counts only.
Usage: python -m pilot_c.edit_failures <out.json> <run_label> <trace.json> [<trace.json> ...]
"""
from __future__ import annotations

import json
import sys
import tarfile
from pathlib import Path

from common.trace import load_trace, pair_tool_calls
from pilot_c import kaggle_runner as kr
from pilot_c.probe import _norm_path, apply_edit


def _result(c) -> dict:
    try:
        r = json.loads(c.result) if c.result else {}
    except ValueError:
        return {}
    if isinstance(r, dict) and isinstance(r.get("result"), str) and r["result"].lstrip().startswith("{"):
        try:
            r = json.loads(r["result"])
        except ValueError:
            pass
    return r if isinstance(r, dict) else {}


def _snapshot_file(task: str, path: str) -> str | None:
    tgz = kr.data_dir() / "snapshots" / f"{task}.tgz"
    with tarfile.open(tgz, "r|gz") as tf:
        for m in tf:
            n = m.name[2:] if m.name.startswith("./") else m.name
            if n == path and m.isfile():
                fh = tf.extractfile(m)
                return fh.read().decode("utf-8", errors="replace") if fh else None
    return None


def replay(task: str, trace: Path, first_compaction_at_call: int | None = None) -> dict:
    calls = pair_tool_calls(load_trace(trace))
    base: dict[str, str | None] = {}
    cur: dict[str, str | None] = {}
    seen: dict[str, list[str]] = {}
    out = {"task": task, "edits": 0, "failed": 0, "tool_would_accept_now": 0, "matches_pre_edit_file_only": 0,
           "never_matched": 0, "path_not_found": 0, "seen_verbatim_in_earlier_read": 0, "after_first_compaction": 0,
           "same_old_string_repeated": 0}
    prev_failed: set[str] = set()
    for c in calls:
        path = _norm_path(c.args.get("filepath") or c.args.get("path"))
        if c.tool == "read_file":
            content = _result(c).get("content")
            if isinstance(content, str):
                seen.setdefault(path, []).append(content)
            continue
        if c.tool not in ("edit_file", "write_file") or not path:
            continue
        if path not in cur:
            base[path] = cur[path] = _snapshot_file(task, path)
        r = _result(c)
        ok = r.get("status") == "ok"
        if c.tool == "write_file":
            if ok:
                cur[path] = str(c.args.get("content", ""))
            continue
        out["edits"] += 1
        old, new = str(c.args.get("old_string", "")), str(c.args.get("new_string", ""))
        if ok:
            if cur[path] is not None:
                ed, _ = apply_edit(cur[path], old, new)
                cur[path] = ed if ed is not None else cur[path]
            continue
        out["failed"] += 1
        if first_compaction_at_call is not None and c.index >= first_compaction_at_call:
            out["after_first_compaction"] += 1
        if old in prev_failed:
            out["same_old_string_repeated"] += 1
        prev_failed.add(old)
        if any(old.strip() and old.strip() in s for s in seen.get(path, [])):
            out["seen_verbatim_in_earlier_read"] += 1
        if cur[path] is None:
            out["path_not_found"] += 1
        elif apply_edit(cur[path], old, new)[0] is not None:
            out["tool_would_accept_now"] += 1
        elif base[path] is not None and apply_edit(base[path], old, new)[0] is not None:
            out["matches_pre_edit_file_only"] += 1
        else:
            out["never_matched"] += 1
    return out


def main(out_path: str, run_label: str, *traces: str) -> dict:
    rows = json.loads(Path(run_label).read_text()) if Path(run_label).exists() else None
    fc = {}
    if rows:   # optional: a validation output file, to know each task's first compaction (O0 runs)
        fc = {x["instance_id"]: x.get("cmp_first_compaction_at_call") for r in rows["runs"] if r["condition"] == "O0" for x in r["rows"]}
    res = [replay(Path(t).name[len("trace_"):-len(".json")], Path(t), fc.get(Path(t).name[len("trace_"):-len(".json")])) for t in traces]
    tot = {k: sum(r[k] for r in res) for k in res[0] if k != "task"} if res else {}
    Path(out_path).write_text(json.dumps({"runs": res, "total": tot}, indent=1))
    for r in res:
        print(r)
    print("TOTAL", tot)
    return {"runs": res, "total": tot}


if __name__ == "__main__":
    main(*sys.argv[1:])
