"""Assemble the held-out export in docs/PROBE_INPUT.md "Level A" layout (pilot C's probe input).

OUT/
  tasks.jsonl                 exactly the 8 string fields of PROBE_INPUT (no FAIL_TO_PASS/PASS_TO_PASS: with them the
                              scorer would use F2P+P2P as required tests instead of the test_patch rule the dev tasks use)
  snapshots/<id>.tgz          dev layout (common/snapshot.py)
  graphs/<short>_<base>.json  released-rule graphs (common/graph_build.py faithful mode; generator: codegraph-loc
                              1e8e0ab + exact released id/text/edge rules; 100% node-id match on 7/7 dev graphs)
  embeddings/<short>_<base>.npz   disclosed substitute (common/embed_nodes.py; see EXPORT.json "embeddings")
  wheels/*.whl                test-only deps (cp312 for the Kaggle subprocess host, cp313 for the Docker image)
  heldout_meta.jsonl          sidecar per task: provenance, F2P/P2P, gold nodes, verified repro test, probe eligibility
  EXPORT.json                 versions, generator, embedding model, counts, known gaps
Only tasks valid in the harness (gold passes, empty patch fails) are exported. Tasks with an empty
problem_statement are kept but flagged (needs_issue_text): fill them with common/github_text.py where
api.github.com is reachable (Kaggle notebook with Internet ON, or a laptop) BEFORE any probe or rollout.

Usage:
  python pilot_d/export_level_a.py --work WORK/heldout --out OUT [--tasks tasks_text.jsonl] [--meta meta_text.jsonl]
         [--embed-model gte --embed-input text --embed-map W.npz] [--wheels-req pilot_d/env/*.txt]
(interpreter with swegemma + codegraph-loc; --embed-* needs sentence-transformers)
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.graph_build import build as build_graph  # noqa: E402

FIELDS = ("instance_id", "repo", "base_commit", "patch", "test_patch", "problem_statement", "hints_text", "created_at")


def jl(p: Path) -> list[dict]:
    return [json.loads(l) for l in open(p)] if p.exists() else []


def required_test_names(test_patch: str) -> list[str]:
    from swegemma.harness.verification import _extract_test_functions_from_patch
    return _extract_test_functions_from_patch(test_patch)


def probe_eligibility(task: dict, ann: dict) -> dict:
    """PROBE_INPUT §3 rule 3, mirrored from pilot_c/select_tasks.eligible (minus its dev-repo filter)."""
    files = re.findall(r"^\+\+\+ b/(\S+)", task["patch"], re.M)
    py = [f for f in files if f.endswith(".py")]
    new_files = sorted({h["file"] for h in ann.get("edit_hunks", [])
                        if h.get("old_start") == 0 and h.get("old_len") == 0})
    changed = sum(1 for l in task["patch"].splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---")))
    funcs = [s for s in ann.get("gold_nodes", [])] + [s for s in ann.get("gold_nodes_missing_from_graph_rule", [])
                                                      if "<module>" not in s]
    names = required_test_names(task["test_patch"])
    checks = {"one_src_py_file": len(files) == 1 and len(py) == 1, "file_exists_at_base": not new_files,
              "one_or_two_functions": 1 <= len(funcs) <= 2, "max_40_changed_lines": changed <= 40,
              "has_required_test_name": len(names) >= 1}
    return {"eligible": all(checks.values()), "checks": checks, "changed_lines": changed,
            "n_functions": len(funcs), "required_test_names": names}


_EMB_CACHE: dict[str, dict[str, "object"]] = {}


def write_embeddings(gpath: Path, epath: Path, short: str, a) -> None:
    """Embed one graph's nodes, re-using vectors of identical input texts across commits of the same repo
    (consecutive base commits share almost all nodes, so each new commit costs only its changed nodes)."""
    import hashlib

    import numpy as np

    from common.embed_nodes import apply_map, embed_texts, node_inputs

    if epath.exists():
        return
    cache = _EMB_CACHE.setdefault(short, {})
    ids, texts = node_inputs(json.load(open(gpath)), a.embed_input)
    keys = [hashlib.sha1(t.encode("utf-8", "replace")).hexdigest() for t in texts]
    todo = sorted({k: t for k, t in zip(keys, texts) if k not in cache}.items())
    if todo:
        vecs = embed_texts(a.embed_model, [t for _, t in todo])
        cache.update({k: v for (k, _), v in zip(todo, vecs)})
    X = np.stack([cache[k] for k in keys])
    if a.embed_map:
        X = apply_map(X, np.load(a.embed_map)["W"])
    np.savez_compressed(epath, **{i: X[n].astype(np.float32) for n, i in enumerate(ids)})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--work", required=True, help="dir with tasks.jsonl, meta.jsonl, snapshots/, val_subprocess.jsonl, "
                                                 "testmap.jsonl, annotations.jsonl")
    p.add_argument("--out", required=True)
    p.add_argument("--tasks", default="tasks.jsonl")
    p.add_argument("--meta", default="meta.jsonl")
    p.add_argument("--validation", default="val_subprocess.jsonl")
    p.add_argument("--embed-model")
    p.add_argument("--embed-input", default="text")
    p.add_argument("--embed-map")
    p.add_argument("--wheels-req", nargs="*", default=[])
    p.add_argument("--wheels-dir", help="offline: copy the test-only wheels from this directory instead of downloading")
    p.add_argument("--symlink-snapshots", action="store_true", help="local use: link instead of copying")
    a = p.parse_args()
    W, O = Path(a.work), Path(a.out)
    for d in ("snapshots", "graphs", "embeddings", "wheels"):
        (O / d).mkdir(parents=True, exist_ok=True)
    valid = {r["instance_id"] for r in jl(W / a.validation) if r.get("valid")}
    meta = {m["instance_id"]: m for m in jl(W / a.meta)}
    tm = {r["instance_id"]: r for r in jl(W / "testmap.jsonl")}
    ann = {r["instance_id"]: r for r in jl(W / "annotations.jsonl")}
    tasks = [t for t in jl(W / a.tasks) if t["instance_id"] in valid]
    commits = {}
    with open(O / "tasks.jsonl", "w") as ft, open(O / "heldout_meta.jsonl", "w") as fm:
        for t in tasks:
            iid = t["instance_id"]
            ft.write(json.dumps({k: str(t.get(k) or "") for k in FIELDS}) + "\n")
            src, dst = W / "snapshots" / f"{iid}.tgz", O / "snapshots" / f"{iid}.tgz"
            if not dst.exists():
                (dst.symlink_to(src.resolve()) if a.symlink_snapshots else shutil.copy2(src, dst))
            commits.setdefault((t["repo"].split("/")[1].lower(), t["base_commit"]), iid)
            m, A = meta.get(iid, {}), ann.get(iid, {})
            fm.write(json.dumps({
                "instance_id": iid, "fix_commit": m.get("fix_commit"), "pr_number": m.get("pr_number"),
                "issue_refs": sorted(set((m.get("issue_refs") or []) + (m.get("issue_refs_in_tests") or []))),
                "problem_statement_source": m.get("problem_statement_source", "pending"),
                "needs_issue_text": not (t.get("problem_statement") or "").strip(),
                "committed_at": m.get("committed_at"), "ai_authored_marker": m.get("ai_authored_marker"),
                "FAIL_TO_PASS": tm.get(iid, {}).get("FAIL_TO_PASS", []),
                "PASS_TO_PASS": tm.get(iid, {}).get("PASS_TO_PASS", []),
                "gold_nodes": A.get("gold_nodes", []), "edit_hunks": A.get("edit_hunks", []),
                "added_symbols": A.get("added_symbols", []),
                "repro_test": A.get("repro_test"), "probe": probe_eligibility(t, A),
            }) + "\n")
    # graphs (+ embeddings) once per (repo, base_commit)
    for (short, base), iid in commits.items():
        gpath = O / "graphs" / f"{short}_{base}.json"
        if not gpath.exists():
            with tempfile.TemporaryDirectory() as td:
                with tarfile.open(W / "snapshots" / f"{iid}.tgz") as tf:
                    tf.extractall(td, filter="data")
                build_graph(td, short, base, str(O / "graphs"))
        if a.embed_model:
            write_embeddings(gpath, O / "embeddings" / f"{short}_{base}.npz", short, a)
    if a.wheels_dir:  # offline (D0b): wheels were downloaded by D0a
        for w in Path(a.wheels_dir).glob("*.whl"):
            shutil.copy2(w, O / "wheels" / w.name)
    for req in ([] if a.wheels_dir else a.wheels_req):  # test-only deps, both interpreters used by the two backends
        if not any(l.split("#")[0].strip() for l in open(req)):
            continue  # this repo declares no test-only deps
        for pyv in ("3.12", "3.13"):
            pip = [shutil.which("pip")] if shutil.which("pip") else [sys.executable, "-m", "pip"]
            subprocess.run([*pip, "download", "-q", "--no-deps", "-r", req, "--only-binary=:all:",
                            "--python-version", pyv, "--platform", "manylinux2014_x86_64", "--platform",
                            "manylinux_2_17_x86_64", "--platform", "manylinux_2_28_x86_64", "-d", str(O / "wheels")],
                           check=True)
    rows = jl(O / "heldout_meta.jsonl")
    info = {
        "format": "docs/PROBE_INPUT.md v2 Level A (paper/main)", "tasks": len(rows),
        "repos": sorted({t["repo"] for t in tasks}),
        "probe_eligible": sum(r["probe"]["eligible"] for r in rows),
        "needs_issue_text": sum(r["needs_issue_text"] for r in rows),
        "graph_generator": "pilot/d-heldout common/graph_build.py (faithful) on codegraph-loc 1e8e0ab",
        "embeddings": ({"model": a.embed_model, "input": a.embed_input, "map": bool(a.embed_map),
                        "note": "disclosed open-model substitute; released dev embeddings come from an undisclosed "
                                "Google-internal model. Present so the harness shows the same 'Code Intelligence "
                                "Tools' prompt section as on dev tasks."} if a.embed_model else None),
        "test_dep_wheels": sorted(x.name for x in (O / "wheels").glob("*.whl")),
        "subprocess_backend_note": "the subprocess sandbox inherits the HOST site-packages: pip install the wheels/ "
                                   "matching the host Python into the notebook before running the harness",
    }
    (O / "EXPORT.json").write_text(json.dumps(info, indent=1))
    print(json.dumps({k: info[k] for k in ("tasks", "repos", "probe_eligible", "needs_issue_text")}))


if __name__ == "__main__":
    main()
