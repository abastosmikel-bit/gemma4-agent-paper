"""pilot_c/analyze_c03v.py on SYNTHETIC verification results joined to the real C03 samples (and a synthetic C04)."""
import json
import random
from pathlib import Path

from pilot_c import analyze_c03v as av

ROOT = Path(__file__).resolve().parents[1]


def test_c03v_analysis_on_synthetic_data(tmp_path):
    import sys
    sys.path.insert(0, str(ROOT / "tests"))
    from test_analyze_c04 import make_synthetic
    c04 = make_synthetic(tmp_path)
    rnd = random.Random(5)
    rows = []
    for f in (ROOT / "results/C03_probe.json", c04):
        for r in json.loads(Path(f).read_text())["d2"]:
            if r.get("ok") and r.get("state") == "use" and r.get("edit_gold_file") and r.get("applies"):
                rows.append({"task": r["task"], "size": r["size"], "cond": r["cond"], "sample": r["sample"],
                             "solves": bool(r.get("exact")) or rnd.random() < 0.2, "source": "C04" if f == c04 else "C03"})
    vp = tmp_path / "C03v_test_verify.json"
    vp.write_text(json.dumps({"rows": rows}))
    A = av.main(str(vp), str(ROOT / "results/C03_probe.json"), str(c04), str(tmp_path / "out"))
    assert A["verified_without_sample_row"] == 0 and set(A["V2"]) == {"e4b", "12b", "31b"}
    v = A["V1"]["31b/L5"]
    assert v["samples"] == 54 and v["exact_not_solves"] == 0 and v["solves"] >= v["exact"]
    assert sum(A["V2"]["e4b"].values()) == 30
    for f in ("C03v_analysis.json", "C03v_tables.md", "C03v_fig_solves.png"):
        assert (tmp_path / "out" / f).exists(), f
