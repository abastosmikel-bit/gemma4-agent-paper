"""Synthetic test of the D1v analysis (pilot_c/analyze_d1v.py). usage: python -m tests.test_analyze_d1v"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pilot_c import analyze_d1v as av  # noqa: E402


def main() -> None:
    d2, rows = [], []
    for s in av.SIZES:
        for t in range(10):
            for c in av.CONDS:
                for k in range(2):
                    edit = (s == "e4b") or (c == "L5" and k == 0)
                    d2.append({"task": f"t{t}", "size": s, "state": "use", "cond": c, "sample": k, "ok": True, "tool_call": True,
                               "tool": "edit_file" if edit else "read_file", "edit_gold_file": edit, "applies": edit,
                               "on_target": edit, "exact": edit and c == "L5" and t < 3})
                    if edit:
                        rows.append({"task": f"t{t}", "size": s, "cond": c, "sample": k, "solves": c == "L5" and t < 6, "source": "D1"})
            d2.append({"task": f"t{t}", "size": s, "state": "find", "cond": "L0", "sample": 0, "ok": True, "hit_file": True})
    with tempfile.TemporaryDirectory() as td:
        p, v = Path(td) / "D1.json", Path(td) / "D1v.json"
        p.write_text(json.dumps({"d1": [], "d2": d2}))
        v.write_text(json.dumps({"rows": rows}))
        A = av.main(str(v), str(p), str(ROOT / "results" / "D1v_dev_reference.json"), td)
        e = A["V"]["e4b/L5"]
        assert e["samples"] == 20 and e["edit_rate"] == 1.0 and e["solves"] == 12 and e["solves_given_edit"] == 0.6
        assert e["exact"] == 6 and e["solves_not_exact"] == 6 and e["exact_not_solves"] == 0 and e["tasks_any_solves"] == 6
        b = A["V"]["12b/L2"]
        assert b["edit_rate"] == 0.0 and b["solves_given_edit"] is None and b["solves"] == 0
        assert A["V"]["31b/L5"]["edit_rate"] == 0.5 and A["V"]["31b/L5"]["solves_given_edit"] == 0.6
        assert A["H5_with_solves"]["e4b"]["L5_any_solves"] == 6 and A["verified_without_sample_row"] == 0
        assert (Path(td) / "D1v_tables.md").exists() and "dev:" in (Path(td) / "D1v_tables.md").read_text()
    print("test_analyze_d1v OK")


if __name__ == "__main__":
    main()
