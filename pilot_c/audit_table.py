"""Benchmark audit table: one row per dev task that is NOT valid in the official sandbox (gold passes AND no patch fails),
with the reason. Inputs: results/C00_gold_check.json (Kaggle), results/C00_audit_imports.json (import check,
pilot_c/audit_imports.py, local Python 3.12 + wheelhouse). Output: results/C00_audit.md and results/C00_audit.json.
Reasons for the tasks whose gold patch fails its own tests were read from local reruns of the gold verification
(test output kept private); EVIDENCE records what was seen, CERTAINTY how sure the cause is.
Usage: python -m pilot_c.audit_table
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Read from local gold reruns (Python 3.12 + wheelhouse, 2026-11-02); test output not committed.
OBSERVED = {
    "fastapi_15763": ("required tests are `async def` and no async pytest plugin is active in the sandbox",
                      "pytest: 'async def functions are not natively supported' for the 3 required tests", "verified"),
    "fastapi_15785": ("required tests are `async def` and no async pytest plugin is active in the sandbox",
                      "same 3 tests, same pytest message", "verified"),
    "rich_3486": ("the required test is skipped on Python >= 3.11; the sandbox runs 3.12",
                  "test_patch: @pytest.mark.skipif(sys.version_info.minor >= 11); pytest: 1 skipped", "verified"),
    "rich_3296": ("expected styled output differs: pygments picks the IPython lexer (IPython is installed on the host)",
                  "AssertionError 'IPython' == 'Python' plus ANSI-output mismatches", "likely"),
    "rich_4070": ("expected styled output differs: pygments picks the IPython lexer (IPython is installed on the host)",
                  "AssertionError 'IPython' == 'Python' / 'ipython' == 'python' plus ANSI-output mismatches", "likely"),
    "rich_3064": ("expected ANSI output of syntax-highlighted markdown differs in this environment",
                  "test_markdown: test_markdown_render, test_inline_code fail on styled strings", "cause of the difference not verified"),
    "rich_3130": ("expected ANSI output of syntax-highlighted markdown differs in this environment",
                  "same two markdown tests fail on styled strings", "cause of the difference not verified"),
    "rich_3469": ("expected ANSI output of syntax-highlighted markdown differs in this environment",
                  "test_inline_code fails on styled strings", "cause of the difference not verified"),
}


def reason(row: dict, imp: dict | None) -> tuple[str, str, str]:
    iid, cls, mods = row["instance_id"], row["failure_class"], row.get("missing_modules") or []
    if row.get("gold_resolved") and row.get("baseline_resolved"):
        base = ("tests pass with NO patch", "Kaggle C00: gold and no-patch both pass", "verified")
    elif iid in OBSERVED:
        base = OBSERVED[iid]
    elif cls == "missing_module":
        base = (f"test dependency missing in the sandbox image: {', '.join(sorted(mods))}", "Kaggle C00: ModuleNotFoundError", "verified")
    elif cls == "missing_fixture":
        base = (f"pytest fixture missing (pytest-httpbin): {', '.join(sorted(set(mods)))}", "Kaggle C00: fixture not found", "verified")
    else:
        base = ("gold patch fails its required tests (cause not determined)", f"Kaggle C00: {cls}", "unknown")
    if imp and imp.get("as_harness_imported_from") == "venv/host site-packages":
        fix_ok = imp.get("src_first_gold") is True and imp.get("src_first_no_patch") is False
        txt = (f"tests import the host's installed {imp['package']} {imp.get('as_harness_version')} instead of the repo "
               f"({imp['layout']} layout), so the patch cannot change the outcome")
        if fix_ok:
            return (txt + "; valid once the repo's src/ is imported", base[1] + f"; import check: host copy; src first: gold passes, no patch fails", "verified (local)")
        return (txt + "; with src/ first still not valid: " + base[0], base[1] + f"; import check: host copy; src first: gold={imp.get('src_first_gold')}, no patch={imp.get('src_first_no_patch')}", "verified (local)")
    return base


def main() -> dict:
    c00 = json.loads((ROOT / "results/C00_gold_check.json").read_text())
    ip = ROOT / "results/C00_audit_imports.json"
    imports = {r["instance_id"]: r for r in json.loads(ip.read_text())["rows"]} if ip.exists() else {}
    rows = []
    for r in c00["rows"]:
        if r.get("valid"):
            continue
        why, evidence, certainty = reason(r, imports.get(r["instance_id"]))
        rows.append({"instance_id": r["instance_id"], "repo": r["repo"], "gold": r["gold_resolved"], "no_patch": r["baseline_resolved"],
                     "c00_class": r["failure_class"], "reason": why, "evidence": evidence, "certainty": certainty})
    groups = collections.Counter(x["reason"].split(";")[0].split(":")[0] for x in rows)
    controls = {k: v for k, v in imports.items() if k not in {x["instance_id"] for x in rows}}
    L = ["# Benchmark audit: why each invalid dev task is invalid (data only)", "",
         f"Valid = the gold patch passes AND no patch fails, in the official sandbox (Kaggle, `notebooks/C00_gold_check__CPU.ipynb`). "
         f"Valid: {sum(1 for r in c00['rows'] if r.get('valid'))}/{len(c00['rows'])}. Invalid: {len(rows)}. "
         "Produced by `pilot_c/audit_table.py` from `results/C00_gold_check.json` and `results/C00_audit_imports.json`.", "",
         "## Reasons (counts)", "", "| Reason | Tasks |", "|---|---|"]
    L += [f"| {k} | {n} |" for k, n in groups.most_common()]
    L += ["", "## Import check controls (valid tasks, same probe)", "", "| Task | layout | imported from (as the harness runs) |", "|---|---|---|"]
    L += [f"| {k} | {v['layout']} | {v.get('as_harness_imported_from')} {v.get('as_harness_version') or ''} |" for k, v in controls.items()]
    L += ["", "## Per task", "", "| Task | Repo | Gold (Kaggle) | No patch (Kaggle) | C00 class | Reason | Evidence | Certainty |",
          "|---|---|---|---|---|---|---|---|"]
    L += [f"| {x['instance_id']} | {x['repo']} | {x['gold']} | {x['no_patch']} | {x['c00_class']} | {x['reason']} | {x['evidence']} | {x['certainty']} |"
          for x in sorted(rows, key=lambda x: (x["repo"], x["reason"], x["instance_id"]))]
    (ROOT / "results/C00_audit.md").write_text("\n".join(L) + "\n")
    out = {"invalid": len(rows), "reasons": dict(groups), "rows": rows}
    (ROOT / "results/C00_audit.json").write_text(json.dumps(out, indent=1))
    print("\n".join(L[:20]))
    return out


if __name__ == "__main__":
    main()
