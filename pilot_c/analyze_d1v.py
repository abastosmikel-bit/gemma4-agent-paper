"""Analysis of notebooks/D1v_test_verify__CPU.ipynb (exploratory, docs/PLAN_D1_heldout_probe.md §6): which of D1's sampled
S-use edits pass the required tests. Standalone (numpy; matplotlib optional); runs as D1v's last cell and offline; tested
on synthetic data (tests/test_analyze_d1v.py). Reuses C03v's join (pilot_c/analyze_c03v.py) so numbers are computed as
for the dev probe.

Per size and rung (L0, L2, L5): samples; edit rate (first action edits the gold file); pass rate with a cluster-bootstrap
CI; pass rate given an edit; tasks with >= 1 passing sample; exact edits; passing edits that are not exact; exact edits
that fail. Dev column: the same code on C03v (results/D1v_dev_reference.json, built by
`python -m pilot_c.analyze_d1v --dev-reference results/C03v_test_verify.json results/C03_probe.json results/C04_probe_followup.json <out>`).
Usage: python -m pilot_c.analyze_d1v <D1v_test_verify.json> <D1_heldout_probe.json> <D1v_dev_reference.json> <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from pilot_c import analyze_c03v as av

CONDS = ("L0", "L2", "L5")
SIZES = ("e4b", "12b", "31b")


def analyze(verify: dict, probe_files: list[str]) -> dict:
    S = av.samples(probe_files)
    S = {k: v for k, v in S.items() if k[1] in CONDS and k[0] in SIZES}
    solved = {(r["size"], r["cond"], r["task"], r["sample"]): bool(r["solves"]) for r in verify["rows"]}
    base = av.analyze({"rows": [r for r in verify["rows"] if r["cond"] in CONDS]}, probe_files)
    out = {"samples_known": len(S), "verified_rows": len(verify["rows"]),
           "verified_without_sample_row": sum(1 for k in solved if k[1] in CONDS and k not in S), "V": {}}
    for size in SIZES:
        for c in CONDS:
            keys = [k for k in S if k[0] == size and k[1] == c]
            if not keys:
                continue
            v1 = base["V1"].get(f"{size}/{c}", {})
            edits = [k for k in keys if S[k].get("edit_gold_file")]
            pe = sum(solved.get(k, False) for k in edits)
            out["V"][f"{size}/{c}"] = {**v1, "edit_rate": round(len(edits) / len(keys), 4), "edits": len(edits),
                                       "solves_given_edit": round(pe / len(edits), 4) if edits else None}
    out["H5_with_solves"] = base["V3"]
    return out


def tables_md(A: dict, dev: dict | None) -> str:
    dev = (dev or {}).get("V", {})
    pct = lambda x: "—" if x is None else f"{100 * x:.0f}%"  # noqa: E731
    L = ["# D1v — test verification of D1's sampled S-use edits (exploratory)", "",
         f"Samples in D1: {A['samples_known']}; verified edits: {A['verified_rows']} (without a matching sample row: "
         f"{A['verified_without_sample_row']}). Dev = C03 + C04 samples verified by C03v, same code.", "",
         "| size / rung | samples | edits gold file | passes [95% CI] | passes given an edit | tasks with ≥ 1 pass | exact | passes, not exact | exact, fails | dev: edits / passes / passes given edit |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in A["V"].items():
        ci = v.get("solves_rate_ci")
        d = dev.get(k, {})
        L.append(f"| {k} | {v['samples']} | {pct(v['edit_rate'])} | {pct(v['solves_rate'])}" + (f" [{pct(ci[0])}, {pct(ci[1])}]" if ci else "")
                 + f" | {pct(v['solves_given_edit'])} ({v['edits']} edits) | {v['tasks_any_solves']}/{v['tasks']} | {v['exact']} | "
                 f"{v['solves_not_exact']} | {v['exact_not_solves']} | {pct(d.get('edit_rate'))} / {pct(d.get('solves_rate'))} / "
                 f"{pct(d.get('solves_given_edit'))} |")
    L += ["", "Tasks with ≥ 1 passing sample at L2 and at L5 (H5 with passes; exploratory):", "",
          "| size | tasks | L2 | L5 |", "|---|---|---|---|"]
    for s, v in A["H5_with_solves"].items():
        L.append(f"| {s} | {v['tasks']} | {v['L2_any_solves']} | {v['L5_any_solves']} |")
    return "\n".join(L) + "\n"


def main(verify_path: str, d1_path: str, dev_path: str | None, out_dir: str = ".") -> dict:
    A = analyze(json.loads(Path(verify_path).read_text()), [d1_path])
    dev = json.loads(Path(dev_path).read_text()) if dev_path and Path(dev_path).exists() else None
    A.update({"notebook": "notebooks/D1v_test_verify__CPU.ipynb", "plan": "docs/PLAN_D1_heldout_probe.md §6 (exploratory)",
              "dev_reference": bool(dev)})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "D1v_analysis.json").write_text(json.dumps(A, indent=1))
    md = tables_md(A, dev)
    (out / "D1v_tables.md").write_text(md)
    print(md)
    return A


def dev_reference(verify_path: str, c03: str, c04: str, out_path: str) -> dict:
    A = analyze(json.loads(Path(verify_path).read_text()), [c03, c04])
    A["source"] = "dev: results/C03v_test_verify.json joined to C03 + C04 depth-2 rows (L0, L2, L5)"
    Path(out_path).write_text(json.dumps(A, indent=1))
    print(tables_md(A, None))
    return A


if __name__ == "__main__":
    if sys.argv[1] == "--dev-reference":
        dev_reference(*sys.argv[2:6])
    else:
        main(*sys.argv[1:5])
