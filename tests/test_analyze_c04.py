"""pilot_c/analyze_c04.py end to end on SYNTHETIC C04 output built around the real C03 results: merged pre-registered
tables (12b completed), exploratory tables and figures are produced, and merging behaves as specified."""
import json
import random
from pathlib import Path

from pilot_c import analyze_c04 as a4
from pilot_c import probe as pb

ROOT = Path(__file__).resolve().parents[1]


def make_synthetic(out: Path, seed: int = 3) -> Path:
    rnd = random.Random(seed)
    c03 = json.loads((ROOT / "results/C03_probe.json").read_text())
    ref = {(r["size"], r["state"], r["cond"], r["task"]): r["logp"] for r in c03["d1"] if r.get("ok") and r.get("rep", 1) == 1}

    def cell(size, task, state, cond, purpose, logp=None):
        lp = logp if logp is not None else -rnd.uniform(5, 80)
        act = -rnd.uniform(0.1, 6)
        return {"task": task, "size": size, "state": state, "cond": cond, "rep": 1, "purpose": purpose, "ok": True,
                "logp": round(lp, 4), "n_tok": 40, "n_tok_action": 6, "logp_action": round(act, 4), "logp_args": round(lp - act, 4),
                "mode": "direct"}
    d1, d2 = [], []
    for r in c03["d1"]:                       # 12b cells C03's time guard cut -> design rows
        if r.get("size") == "12b" and r.get("why") == "time_guard":
            d1.append(cell("12b", r["task"], r["state"], r["cond"], "design"))
    for size in ("12b", "31b", "e4b"):
        for t in c03["task_ids"]:
            d1 += [cell(size, t, st, "G-null", "control") for st in ("find", "use")]
            for st, conds in (("find", pb.RESCORE_FIND), ("use", pb.RESCORE_USE)):
                for c in conds:
                    base = ref.get((size, st, c, t))
                    d1.append(cell(size, t, st, c, "rescore", None if base is None else base + rnd.gauss(0, 0.5)))
            for c in ("X-graph", "G-null"):
                d2.append({"task": t, "size": size, "state": "find", "cond": c, "sample": 0, "ok": True, "tool": "read_file",
                           "hit_file": rnd.random() < 0.6, "hit_func": rnd.random() < 0.2, "followed_wrong": rnd.random() < 0.1})
            if size == "12b":                  # 12b depth 2 (design)
                d2 += [{"task": t, "size": "12b", "state": "find", "cond": c, "sample": 0, "ok": True, "tool": "read_file",
                        "tool_call": True, "hit_file": rnd.random() < 0.7, "hit_func": rnd.random() < 0.4, "followed_wrong": False}
                       for c in pb.D2_FIND]
                for c in pb.D2_USE:
                    for k in range(2):
                        ed = rnd.random() < 0.6
                        d2.append({"task": t, "size": "12b", "state": "use", "cond": c, "sample": k, "ok": True, "tool_call": True,
                                   "tool": "edit_file" if ed else "read_file", "edit_gold_file": ed, "applies": ed,
                                   "on_target": ed and rnd.random() < 0.6, "exact": ed and rnd.random() < 0.2, "followed_wrong": False})
    c04 = {"task_ids": c03["task_ids"], "d1": d1, "d2": d2, "session_elapsed_h": 1.5, "freezes": [],
           "sizes": [{"size": s, "planned": {}} for s in ("12b", "31b", "e4b")],
           "null_controls": {t: {"from": "x", "len_ratio": rnd.uniform(0.85, 1.15), "within_tol": True} for t in c03["task_ids"]}}
    p = out / "C04_probe_followup.json"
    p.write_text(json.dumps(c04))
    return p


def test_c04_analysis_on_synthetic_data(tmp_path):
    p = make_synthetic(tmp_path)
    A = a4.main(str(ROOT / "results/C03_probe.json"), str(p), str(tmp_path / "out"))
    out = tmp_path / "out"
    merged = json.loads((out / "C03C04_analysis.json").read_text())
    assert merged["depth1"]["12b/find/L2-L0"]["n"] == 30          # C03 had 28: the tail is merged in
    assert merged["depth1"]["31b/find/L2-L0"]["n"] == 30 and "12b" in merged["sizes_with_depth2"]
    assert "12b/L5" in merged["depth2"]["use"]
    assert A["graph_control"]["12b/find"]["G-json-G-null"]["n"] > 0 and "12b/G-null" in A["graph_control"]["depth2_find"]
    assert A["action_args"]["31b/find/L1-L0"]["d_action"]["n"] == 30 and A["reproducibility"]["31b"]["n"] > 0
    for f in ("C03C04_tables.md", "C04_tables.md", "C04_fig4_graph_control.png", "C04_fig5_action_args.png",
              "C03C04_fig1_depth1_deltas.png", "C03C04_fig2_depth2_use_edit.png", "C03C04_fig3_graph_vs_text.png"):
        assert (out / f).exists(), f
