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
    "fastapi_15763": ("C. test plugin missing", "required tests are `async def` and no async pytest plugin is active in the sandbox",
                      "pytest: 'async def functions are not natively supported' for the 3 required tests", "verified"),
    "fastapi_15785": ("C. test plugin missing", "required tests are `async def` and no async pytest plugin is active in the sandbox",
                      "same 3 tests, same pytest message", "verified"),
    "rich_3486": ("E. required test skipped on the sandbox's Python", "the required test is skipped on Python >= 3.11; the sandbox runs 3.12",
                  "the test patch marks the required test to be skipped on Python 3.11 and later; pytest reports it skipped", "verified"),
    "rich_3296": ("D. environment-dependent expected output", "expected styled output differs: pygments picks the IPython lexer (IPython is installed on the host)",
                  "AssertionError 'IPython' == 'Python' plus ANSI-output mismatches", "likely"),
    "rich_4070": ("D. environment-dependent expected output", "expected styled output differs: pygments picks the IPython lexer (IPython is installed on the host)",
                  "AssertionError 'IPython' == 'Python' / 'ipython' == 'python' plus ANSI-output mismatches", "likely"),
    "rich_3064": ("D. environment-dependent expected output", "expected ANSI output of syntax-highlighted markdown differs in this environment",
                  "test_markdown: test_markdown_render, test_inline_code fail on styled strings", "cause of the difference not verified"),
    "rich_3130": ("D. environment-dependent expected output", "expected ANSI output of syntax-highlighted markdown differs in this environment",
                  "same two markdown tests fail on styled strings", "cause of the difference not verified"),
    "rich_3469": ("D. environment-dependent expected output", "expected ANSI output of syntax-highlighted markdown differs in this environment",
                  "test_inline_code fails on styled strings", "cause of the difference not verified"),
}


def reason(row: dict, imp: dict | None) -> tuple[str, str, str, str]:
    """(category, reason, evidence, certainty)."""
    iid, cls, mods = row["instance_id"], row["failure_class"], row.get("missing_modules") or []
    if imp and imp.get("as_harness_imported_from") == "venv/host site-packages":
        pkg = f"{imp['package']} {imp.get('as_harness_version')}"
        txt = f"tests import the host's installed {pkg}, not the repo ({imp['layout']} layout), so the patch cannot change the outcome"
        ev = (f"import check: host copy; with the repo's src/ first: gold={imp.get('src_first_gold')}, "
              f"no patch={imp.get('src_first_no_patch')}; Kaggle C00: gold={row['gold_resolved']}, no patch={row['baseline_resolved']}")
        if imp.get("src_first_gold") is True and imp.get("src_first_no_patch") is False:
            return ("B1. host's installed package shadows the repo (valid once src/ is imported)", txt + "; valid once src/ is imported",
                    ev, "verified (local)")
        extra = f"; also pytest fixture missing (pytest-httpbin): {', '.join(sorted(set(mods)))}" if cls == "missing_fixture" else ""
        return ("B2. host's installed package shadows the repo, and a test fixture is missing", txt + extra, ev, "verified (local)")
    if row.get("gold_resolved") and row.get("baseline_resolved"):
        return ("F. tests pass with no patch", "tests pass with NO patch", "Kaggle C00: gold and no-patch both pass", "verified")
    if iid in OBSERVED:
        return OBSERVED[iid]
    if cls == "missing_module":
        return ("A. test dependency missing in the sandbox image", f"missing module(s): {', '.join(sorted(mods))}",
                "Kaggle C00: ModuleNotFoundError", "verified")
    if cls == "missing_fixture":
        return ("G. test fixture missing", f"pytest fixture missing: {', '.join(sorted(set(mods)))}", "Kaggle C00: fixture not found", "verified")
    return ("H. not determined", "gold patch fails its required tests (cause not determined)", f"Kaggle C00: {cls}", "unknown")


def main() -> dict:
    c00 = json.loads((ROOT / "results/C00_gold_check.json").read_text())
    ip = ROOT / "results/C00_audit_imports.json"
    imports = {r["instance_id"]: r for r in json.loads(ip.read_text())["rows"]} if ip.exists() else {}
    rows = []
    for r in c00["rows"]:
        if r.get("valid"):
            continue
        cat, why, evidence, certainty = reason(r, imports.get(r["instance_id"]))
        rows.append({"instance_id": r["instance_id"], "repo": r["repo"], "gold": r["gold_resolved"], "no_patch": r["baseline_resolved"],
                     "c00_class": r["failure_class"], "category": cat, "reason": why, "evidence": evidence, "certainty": certainty})
    groups = collections.Counter(x["category"] for x in rows)
    controls = {k: v for k, v in imports.items() if k not in {x["instance_id"] for x in rows}}
    L = ["# Benchmark audit: why each invalid dev task is invalid (data only)", "",
         f"Valid = the gold patch passes AND no patch fails, in the official sandbox (Kaggle, `notebooks/C00_gold_check__CPU.ipynb`). "
         f"Valid: {sum(1 for r in c00['rows'] if r.get('valid'))}/{len(c00['rows'])}. Invalid: {len(rows)}. "
         "Produced by `pilot_c/audit_table.py` from `results/C00_gold_check.json` and `results/C00_audit_imports.json`.", "",
         "## Reasons (counts)", "", "| Category | Tasks |", "|---|---|"]
    L += [f"| {k} | {n} |" for k, n in sorted(groups.items())]
    L += ["", "## Import check controls (valid tasks, same probe)", "", "| Task | layout | imported from (as the harness runs) |", "|---|---|---|"]
    L += [f"| {k} | {v['layout']} | {v.get('as_harness_imported_from')} {v.get('as_harness_version') or ''} |" for k, v in controls.items()]
    L += ["", "## Per task", "", "| Task | Repo | Gold (Kaggle) | No patch (Kaggle) | C00 class | Category | Reason | Evidence | Certainty |",
          "|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {x['instance_id']} | {x['repo']} | {x['gold']} | {x['no_patch']} | {x['c00_class']} | {x['category']} | {x['reason']} | {x['evidence']} | {x['certainty']} |"
          for x in sorted(rows, key=lambda x: (x["category"], x["instance_id"]))]
    (ROOT / "results/C00_audit.md").write_text("\n".join(L) + "\n")
    out = {"invalid": len(rows), "reasons": dict(groups), "rows": rows}
    (ROOT / "results/C00_audit.json").write_text(json.dumps(out, indent=1))
    print("\n".join(L[:20]))
    return out


if __name__ == "__main__":
    main()
