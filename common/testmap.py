"""Compute FAIL_TO_PASS / PASS_TO_PASS with the harness's own sandbox setup.

For each task: fresh sandbox -> extract snapshot -> harness test config -> baseline commit ->
apply test_patch -> pytest (JUnit) [state "base"]; then apply the gold patch -> pytest [state "gold"].
F2P = tests not passing at base and passing at gold; P2P = passing in both.
Node ids use the SWE-bench convention `path::Class::test[param]`.

Usage: python common/testmap.py --tasks T.jsonl --snapshots DIR --out TESTMAP.jsonl [--ids ...]
(run with the interpreter that has swegemma installed; subprocess backend)
"""
from __future__ import annotations

import argparse
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from swegemma.harness.container_setup import (apply_patch_in_container, extract_snapshot, setup_baseline_commit,
                                              setup_git_exclude, setup_workspace_test_config)
from swegemma.models import load_tasks
from swegemma.sandbox.subprocess import SubprocessManager


# Per-test timeout (pytest-timeout) used ONLY for labelling: a hang bug otherwise kills the whole
# base run, no JUnit is written, and every test of the file would be mislabelled FAIL_TO_PASS.
# Validity verdicts still come from verify_task, which runs with the harness's own timeout=0.
PER_TEST_TIMEOUT = 60


def _outcomes(sb, sid, targets: list[str]) -> dict[str, str]:
    xml = "/tmp/_testmap_junit.xml"
    cmd = (f"cd /workspace && rm -f {xml} && PYTHONSAFEPATH=1 PYTHONNOUSERSITE=1 python3 -s -m pytest "
           f"{' '.join(targets)} --junitxml={xml} -o junit_family=xunit1 -p no:anyio -o timeout={PER_TEST_TIMEOUT} "
           f"-o python_classes='Test* *Test' -q >/dev/null 2>&1; cat {xml}")
    out = sb.exec(sid, cmd).stdout or ""
    res: dict[str, str] = {}
    try:
        root = ET.fromstring(out[out.find("<"):])
    except ET.ParseError:
        return res
    for tc in root.iter("testcase"):
        f, cls, name = tc.get("file", ""), tc.get("classname", ""), tc.get("name", "")
        mod = f[:-3].replace("/", ".") if f.endswith(".py") else ""
        inner = cls[len(mod) + 1:] if mod and cls.startswith(mod + ".") else ""
        node = "::".join(x for x in (f, inner.replace(".", "::"), name) if x)
        state = ("failed" if tc.find("failure") is not None else "error" if tc.find("error") is not None
                 else "skipped" if tc.find("skipped") is not None else "passed")
        res[node] = state
    return res


def _apply(sb, sid, patch: str) -> int:
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as fh:
        fh.write(patch if patch.endswith("\n") else patch + "\n")
    sb.copy_to(sid, Path(fh.name), "/tmp/")
    code, _, _ = apply_patch_in_container(sb, sid, f"/tmp/{Path(fh.name).name}")
    Path(fh.name).unlink(missing_ok=True)
    return code


def testmap(task, snap: Path) -> dict:
    sb = SubprocessManager(timeout_seconds=600)
    sid = sb.start()
    try:
        extract_snapshot(sb, sid, snap)
        setup_git_exclude(sb, sid)
        setup_workspace_test_config(sb, sid, repo=task.repo)
        setup_baseline_commit(sb, sid, "eval_baseline")
        targets = [p for p in task.test_files if p.endswith(".py") and not p.endswith("conftest.py")]
        if _apply(sb, sid, task.test_patch) != 0:
            return {"instance_id": task.instance_id, "error": "test_patch did not apply"}
        base = _outcomes(sb, sid, targets)
        if _apply(sb, sid, task.patch) != 0:
            return {"instance_id": task.instance_id, "error": "gold patch did not apply"}
        gold = _outcomes(sb, sid, targets)
    finally:
        sb.stop(sid)
    f2p = sorted(n for n, s in gold.items() if s == "passed" and base.get(n) != "passed")
    p2p = sorted(n for n, s in gold.items() if s == "passed" and base.get(n) == "passed")
    broken = sorted(n for n, s in gold.items() if s in ("failed", "error"))
    skipped = sorted(n for n, s in gold.items() if s == "skipped")
    return {"instance_id": task.instance_id, "FAIL_TO_PASS": f2p, "PASS_TO_PASS": p2p,
            "gold_not_passing": broken, "gold_skipped": skipped, "n_tests": len(gold)}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", required=True)
    p.add_argument("--snapshots", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--ids", nargs="*")
    a = p.parse_args()
    with open(a.out, "w") as fh:
        for t in load_tasks(Path(a.tasks)):
            if a.ids and t.instance_id not in a.ids:
                continue
            rec = testmap(t, Path(a.snapshots) / f"{t.instance_id}.tgz")
            fh.write(json.dumps(rec) + "\n")
            print(t.instance_id, {k: (len(v) if isinstance(v, list) else v) for k, v in rec.items() if k != "instance_id"},
                  flush=True)
