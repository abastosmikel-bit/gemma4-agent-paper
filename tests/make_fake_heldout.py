"""LOCAL-ONLY: a synthetic stand-in for the output of notebooks/D0b_heldout_export__CPU.ipynb (pilot/d-heldout), for the
papermill dry runs of D1, D2 and D1v. It reuses local dev tasks (their snapshots, graphs, embeddings) under the
held-out layout: heldout_export/{tasks.jsonl, snapshots/, graphs/, embeddings/, wheels/, heldout_meta.jsonl, EXPORT.json}
and D0_summary.json. Nothing here is committed (it points at competition data on this machine).

Exercises: issue vs PR-body vs pending statements, the sympy exclusion (a task whose repo is sympy/sympy, no snapshot
needed: it is dropped before any snapshot is read), the known hang task id, rule 5 (>= 2 per repo), and the test-wheel
install (one missing pure-Python wheel is installed; an installed distribution and a cp313 wheel are skipped).
usage: python tests/make_fake_heldout.py <local_comp> <graphs_dir> <out_dir>
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ISSUE = ["fastapi_15588", "fastapi_14360", "rich_3454", "rich_3470", "rich_4079", "requests_7502", "requests_7433"]
PR_BODY = ["rich_3518"]
PENDING = ["requests_7309"]


def dummy_wheel(path: Path, name: str, version: str) -> None:
    files = {f"{name}/__init__.py": b"VALUE = 1\n",
             f"{name}-{version}.dist-info/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n".encode(),
             f"{name}-{version}.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: fake\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}
    rec = []
    for k, v in files.items():
        h = base64.urlsafe_b64encode(hashlib.sha256(v).digest()).rstrip(b"=").decode()
        rec.append(f"{k},sha256={h},{len(v)}")
    rec.append(f"{name}-{version}.dist-info/RECORD,,")
    files[f"{name}-{version}.dist-info/RECORD"] = ("\n".join(rec) + "\n").encode()
    with zipfile.ZipFile(path, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)


def main(comp: str, graphs: str, out: str) -> None:
    comp_p, graphs_p, out_p = Path(comp), Path(graphs), Path(out)
    E = out_p / "heldout_export"
    for d in ("snapshots", "graphs", "embeddings", "wheels"):
        (E / d).mkdir(parents=True, exist_ok=True)
    tasks = {json.loads(l)["instance_id"]: json.loads(l) for l in open(comp_p / "tasks.jsonl")}
    ids = ISSUE + PR_BODY + PENDING
    rows, meta = [], []
    for i in ids:
        t = tasks[i]
        rows.append(t)
        short = t["repo"].split("/")[1]
        for sub, src in (("snapshots", comp_p / "snapshots" / f"{i}.tgz"),
                         ("graphs", graphs_p / f"{short}_{t['base_commit']}.json"),
                         ("embeddings", comp_p / "embeddings" / f"{short}_{t['base_commit']}.npz")):
            dst = E / sub / src.name
            if src.exists() and not dst.exists():
                dst.symlink_to(src.resolve())
        src = f"issue#{i.split('_')[1]}" if i in ISSUE else (f"pr_body#{i.split('_')[1]}" if i in PR_BODY else "pending")
        meta.append({"instance_id": i, "problem_statement_source": src, "issue_refs": [], "probe": {"eligible": True}})
    # a sympy task (no snapshot: the repo exclusion drops it before any file is read) and the known hang task id
    fake = dict(tasks["requests_7502"], instance_id="sympy_30515", repo="sympy/sympy")
    rows.append(fake)
    meta.append({"instance_id": "sympy_30515", "problem_statement_source": "issue#1", "issue_refs": [1]})
    with open(E / "tasks.jsonl", "w") as f:
        f.writelines(json.dumps(t) + "\n" for t in rows)
    with open(E / "heldout_meta.jsonl", "w") as f:
        f.writelines(json.dumps(m) + "\n" for m in meta)
    dummy_wheel(E / "wheels" / "dtestdep-0.0.1-py3-none-any.whl", "dtestdep", "0.0.1")
    dummy_wheel(E / "wheels" / "six-0.0.1-py3-none-any.whl", "six", "0.0.1")          # installed already: skipped
    (E / "wheels" / "fakebin-1.0-cp313-cp313-manylinux_2_17_x86_64.whl").write_bytes(b"")  # other Python: skipped
    (E / "EXPORT.json").write_text(json.dumps({"format": "docs/PROBE_INPUT.md v2 Level A (paper/main)", "tasks": len(rows),
                                               "note": "LOCAL FAKE for dry runs"}))
    (out_p / "D0_summary.json").write_text(json.dumps({"built": len(rows), "valid_kaggle": len(rows), "note": "LOCAL FAKE",
                                                       "issue_text": {m["instance_id"]: m["problem_statement_source"] for m in meta}}))
    print("fake held-out export:", E, len(rows), "tasks")


if __name__ == "__main__":
    main(*sys.argv[1:4])
