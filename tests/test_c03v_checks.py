"""Synthetic check of pilot_c/c03v_checks.py: counts, edit/pass split and pairing."""
import json

from pilot_c import c03v_checks as cc


def _row(size, cond, task, k, edit, exact=False):
    return {"task": task, "size": size, "state": "use", "cond": cond, "sample": k, "ok": True, "tool_call": True,
            "tool": "edit_file" if edit else "read_file", "edit_gold_file": edit, "applies": edit, "exact": exact}


def test_checks(tmp_path):
    d2, ver = [], []
    for i in range(6):
        t = f"t{i}"
        for k in range(2):
            d2.append(_row("31b", "L0", t, k, False))
            d2.append(_row("31b", "L2", t, k, k == 0))                   # 1 of 2 edits, never passes
            d2.append(_row("31b", "W", t, k, True, exact=(i == 0)))      # always edits; passes on tasks 0-3
            ver.append({"task": t, "size": "31b", "cond": "W", "sample": k, "solves": i < 4})
            if k == 0:
                ver.append({"task": t, "size": "31b", "cond": "L2", "sample": k, "solves": False})
    pf = tmp_path / "p.json"
    pf.write_text(json.dumps({"d2": d2}))
    C = cc.checks({"rows": ver}, [str(pf)])
    k1 = C["K1"]
    assert k1["31b/L0"]["edit_rate"] == 0 and k1["31b/L0"]["solve_given_edit"] is None
    assert k1["31b/L2"]["edits_gold_file"] == 6 and k1["31b/L2"]["solve_given_edit"] == 0
    assert k1["31b/W"]["edit_rate"] == 1 and abs(k1["31b/W"]["solve_given_edit"] - 8 / 12) < 1e-3
    k2 = C["K2"]["31b"]
    assert k2["tasks"] == 6 and k2["tasks_any_pass"] == {"L0": 0, "L2": 0, "W": 4}
    assert k2["pairs"]["W-L0"]["tasks_up"] == 4 and k2["pairs"]["W-L0"]["any_pass_only_first"] == 4
    assert abs(k2["pairs"]["W-L2"]["mean_diff"] - 4 / 6) < 1e-3
    k3 = C["K3"]["31b/W"]
    assert k3["passes"] == 8 and k3["passes_and_exact"] == 2 and k3["passes_not_exact"] == 6
    assert k3["tasks_any_pass_no_exact"] == 3
    md = cc.tables_md(C)
    assert "K1." in md and "31b/W" in md
