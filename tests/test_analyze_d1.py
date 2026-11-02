"""Synthetic test of the frozen D1 analysis (pilot_c/analyze_d1.py): planted effects must give the planted verdicts, and
the analysis cell's outputs must be written. usage: python -m tests.test_analyze_d1"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot_c import analyze_d1 as ad  # noqa: E402

# planted medians (nats) relative to L0, per state; R2 fails for 12b (W does not help), R4 fails for 31b (G-json >> G-null)
EFFECT = {"find": {"L0": 0, "L1": 8, "L2": 20, "W": 6, "G-json": 9, "G-null": 2, "X-func": 6, "X-graph": 8.5},
          "use": {"L0": 0, "L2": 1, "W": 10, "T": 3, "L5": 30, "G-json": 3, "G-null": 2}}


def synth(n: int = 24, seed: int = 1, drop_size: str | None = None) -> dict:
    rng = np.random.default_rng(seed)
    tasks = [f"repo{t % 3}_{t}" for t in range(n)]
    d1, d2 = [], []
    for s in ad.SIZES:
        if s == drop_size:
            continue
        for t in tasks:
            base = {st: -40 + rng.normal(0, 5) for st in ("find", "use")}
            for st, conds in (("find", ad.FIND), ("use", ad.USE)):
                for c in conds:
                    eff = EFFECT[st][c]
                    if s == "12b" and st == "use" and c == "W":
                        eff = -3
                    if s == "31b" and st == "use" and c == "G-json":
                        eff = 12
                    d1.append({"task": t, "size": s, "state": st, "cond": c, "rep": 1, "ok": True, "mode": "direct",
                               "logp": base[st] + eff + rng.normal(0, 2)})
            for c in ad.D2_FIND:
                d2.append({"task": t, "size": s, "state": "find", "cond": c, "sample": 0, "ok": True, "tool_call": True,
                           "hit_file": bool(rng.random() < (0.9 if c in ("L2", "G-json") else 0.4)),
                           "hit_func": bool(rng.random() < (0.8 if c == "L2" else 0.2)), "followed_wrong": c == "X-graph"})
            for c in ad.D2_USE:
                for k in range(2):
                    e = bool(rng.random() < 0.6)
                    d2.append({"task": t, "size": s, "state": "use", "cond": c, "sample": k, "ok": True, "tool_call": True,
                               "tool": "edit_file" if e else "read_file", "edit_gold_file": e, "applies": e,
                               "on_target": e and rng.random() < 0.7, "exact": e and c == "L5" and rng.random() < 0.5,
                               "followed_wrong": False})
    d1.append({"size": "e4b", "ok": False, "why": "time_guard"})
    return {"notebook": "notebooks/D1_heldout_probe__L4x4.ipynb", "task_ids": tasks, "d1": d1, "d2": d2,
            "selection": {"selected_by_repo": {"a/repo0": 8, "b/repo1": 8, "c/repo2": 8}}, "depth2": True}


def main() -> None:
    dev = json.load(open(ROOT / "results" / "D1_dev_reference.json"))
    assert all(v == "replicated" for v in dev["verdicts"].values()), dev["verdicts"]
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "D1_heldout_probe.json"
        p.write_text(json.dumps(synth()))
        A = ad.main(str(p), str(ROOT / "results" / "D1_dev_reference.json"), td)
        assert A["verdicts"]["R1"] == "replicated", A["verdicts"]
        assert A["verdicts"]["R2"].startswith("not replicated (2 of 3"), A["verdicts"]
        assert A["R2_claim1_words_and_diff"]["12b"]["holds"] is False
        assert A["verdicts"]["R3"] == "replicated", A["R3_claim3_graph_find"]
        assert A["R4_claim3_graph_use"]["31b"]["holds"] is False and A["R4_claim3_graph_use"]["e4b"]["holds"] is True
        assert A["R5_depth2"]["use"]["e4b/L5"]["samples"] == 48 and A["R5_depth2"]["find"]["12b/L2"]["tasks"] == 24
        assert A["figures"] == ["D1_fig1_criteria.png", "D1_fig2_depth2.png"]
        for f in ("D1_analysis.json", "D1_tables.md", *A["figures"]):
            assert (Path(td) / f).exists(), f
        md = (Path(td) / "D1_tables.md").read_text()
        assert "| R1 | replicated | replicated |" in md and "not evaluable" not in md.split("## R5")[0]
        # a missing size makes the verdicts "incomplete", never "replicated"
        p.write_text(json.dumps(synth(drop_size="31b")))
        B = ad.main(str(p), None, td)
        assert B["verdicts"]["R1"].startswith("incomplete") and B["R1_claim1_find_vs_use"]["31b"]["holds"] is None
        # depth 1 only (fallback version): R5 empty, R1-R4 unaffected
        d = synth()
        d["d2"], d["depth2"] = [], False
        p.write_text(json.dumps(d))
        C = ad.main(str(p), None, td)
        assert C["R5_depth2"] == {"find": {}, "use": {}} and C["verdicts"]["R1"] == "replicated"
    print("test_analyze_d1 OK")


if __name__ == "__main__":
    main()
