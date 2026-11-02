"""Three exploratory checks on C03v's test verification of the probe's sampled S-use edits (CPU, numbers only).

Inputs : C03v_test_verify.json, C03_probe.json and C04_probe_followup.json (their depth-2 S-use rows: every sample, edited
         or not, with `tool`, `edit_gold_file`, `applies`, `exact`).
Outputs: <out_dir>/C03v_checks.json and C03v_checks.md.
  K1 edit vs correctness: per size x condition, the share of samples that edit the gold file, and the share of those
     edits that pass the required tests. Says whether a low pass rate is "doesn't edit" or "edits wrongly".
  K2 paired W vs L2 vs L0 on the tasks that have all three, per size: per-task pass share (0, 0.5 or 1 of 2 samples),
     mean differences with a task bootstrap CI, Wilcoxon signed-rank on the per-task differences (Holm over the three
     comparisons within a size), exact McNemar on "at least one sample passes", and Cochran's Q across the three.
  K3 exact-match undercount: per size x condition, passing samples that are not an exact match of the scored gold edit.
Not pre-registered (docs/PLAN.md §11). Single run, 1-2 samples per cell.
Usage: python -m pilot_c.c03v_checks <C03v_test_verify.json> <C03_probe.json> <C04_probe_followup.json> <out_dir>
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from common.stats import bootstrap_ci, bootstrap_ratio_ci, cochran_q, holm, mcnemar_exact, wilcoxon_p
from pilot_c.analyze_c03v import samples

SIZES = ("e2b", "e4b", "12b", "31b")
K1_CONDS = ("L0", "L2", "W", "L5")
K3_CONDS = ("L0", "L2", "L3", "L4", "L5", "T", "W", "G-json", "X-func", "X-test")
PAIRS = (("W", "L2"), ("W", "L0"), ("L2", "L0"))
MIN_EDITS_FOR_CI = 5   # as in analyze_c03's figure 2: no interval on fewer edits


def _r(x, d=4):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), d)


def _what(r: dict) -> str:
    if r.get("edit_gold_file"):
        return "edits gold file"
    if r.get("tool") in ("edit_file", "write_file"):
        return "edits another file"
    if not r.get("tool_call"):
        return "no tool call"
    return f"calls {r.get('tool')}"


def checks(verify: dict, probe_files: list[str]) -> dict:
    S = samples(probe_files)
    solved = {(r["size"], r["cond"], r["task"], r["sample"]): bool(r["solves"]) for r in verify["rows"]}
    sizes = [s for s in SIZES if any(k[0] == s for k in S)]
    out: dict = {"K1": {}, "K2": {}, "K3": {}}

    for size in sizes:
        for cond in K1_CONDS:
            keys = [k for k in S if k[0] == size and k[1] == cond]
            if not keys:
                continue
            tasks = sorted({k[2] for k in keys})
            ed = {t: [k for k in keys if k[2] == t and S[k].get("edit_gold_file")] for t in tasks}
            sol = {t: sum(solved.get(k, False) for k in ed[t]) for t in tasks}
            n_ed = sum(len(v) for v in ed.values())
            n_ap = sum(1 for k in keys if S[k].get("applies"))
            out["K1"][f"{size}/{cond}"] = {
                "samples": len(keys), "edits_gold_file": n_ed, "edit_rate": _r(n_ed / len(keys)),
                "edit_rate_ci": [_r(v) for v in bootstrap_ratio_ci([len(ed[t]) for t in tasks],
                                                                   [sum(k[2] == t for k in keys) for t in tasks])],
                "edits_apply": n_ap, "solves": sum(sol.values()),
                "solve_rate": _r(sum(sol.values()) / len(keys)),
                "solve_given_edit": _r(sum(sol.values()) / n_ed) if n_ed else None,
                "solve_given_edit_ci": [_r(v) for v in bootstrap_ratio_ci([sol[t] for t in tasks], [len(ed[t]) for t in tasks])]
                if n_ed >= MIN_EDITS_FOR_CI else None,
                "first_action": dict(Counter(_what(S[k]) for k in keys).most_common())}

        conds = ("L0", "L2", "W")
        tasks = sorted(t for t in {k[2] for k in S if k[0] == size}
                       if all(any(k[0] == size and k[1] == c and k[2] == t for k in S) for c in conds))
        share = {c: [] for c in conds}
        anyp = {c: [] for c in conds}
        for t in tasks:
            for c in conds:
                ks = [k for k in S if k[0] == size and k[1] == c and k[2] == t]
                v = [solved.get(k, False) for k in ks]
                share[c].append(sum(v) / len(v))
                anyp[c].append(int(any(v)))
        res = {"tasks": len(tasks), "mean_pass_share": {c: _r(np.mean(share[c])) if tasks else None for c in conds},
               "tasks_any_pass": {c: int(sum(anyp[c])) for c in conds}, "pairs": {}}
        ps = {}
        for a, b in PAIRS:
            d = np.asarray(share[a]) - np.asarray(share[b])
            up = sum(1 for x, y in zip(anyp[a], anyp[b]) if x and not y)
            down = sum(1 for x, y in zip(anyp[a], anyp[b]) if y and not x)
            ps[f"{a}-{b}"] = wilcoxon_p(d.tolist())
            res["pairs"][f"{a}-{b}"] = {
                "mean_diff": _r(d.mean()) if len(d) else None,
                "mean_diff_ci": [_r(v) for v in bootstrap_ci(d.tolist(), stat=np.mean)],
                "tasks_up": int((d > 0).sum()), "tasks_down": int((d < 0).sum()), "wilcoxon_p": _r(ps[f"{a}-{b}"]),
                "any_pass_only_first": up, "any_pass_only_second": down, "mcnemar_p": _r(mcnemar_exact(up, down))}
        for k, p in holm(ps).items():
            res["pairs"][k]["wilcoxon_p_holm"] = _r(p)
        q = cochran_q([[anyp[c][i] for c in conds] for i in range(len(tasks))])
        res["cochran_q_any_pass"] = {k: _r(v) if isinstance(v, float) else v for k, v in q.items()}
        out["K2"][size] = res

        for cond in K3_CONDS:
            keys = [k for k in S if k[0] == size and k[1] == cond]
            if not keys:
                continue
            pas = [k for k in keys if solved.get(k, False)]
            ex = [k for k in keys if S[k].get("exact")]
            tasks = {k[2] for k in keys}
            out["K3"][f"{size}/{cond}"] = {
                "samples": len(keys), "passes": len(pas), "exact": len(ex),
                "passes_and_exact": sum(1 for k in pas if S[k].get("exact")),
                "passes_not_exact": sum(1 for k in pas if not S[k].get("exact")),
                "exact_not_passes": sum(1 for k in ex if not solved.get(k, False)),
                "share_of_passes_missed_by_exact": _r(sum(1 for k in pas if not S[k].get("exact")) / len(pas)) if pas else None,
                "tasks": len(tasks), "tasks_any_pass": len({k[2] for k in pas}), "tasks_any_exact": len({k[2] for k in ex}),
                "tasks_any_pass_no_exact": len({k[2] for k in pas} - {k[2] for k in ex})}
    return out


def tables_md(C: dict) -> str:
    pc = lambda x: "—" if x is None else f"{x:.0%}"  # noqa: E731
    ci = lambda c: "" if not c or c[0] is None else f" [{c[0]:.0%}, {c[1]:.0%}]"  # noqa: E731
    L = ["# C03v checks — edit vs correctness, paired W/L2/L0, exact-match undercount (data only, exploratory)", "",
         "Source: `C03v_test_verify.json` + depth-2 S-use rows of `C03_probe.json` and `C04_probe_followup.json`; "
         "`pilot_c/c03v_checks.py`. 1-2 samples per task and cell; CIs resample tasks; no CI on fewer than "
         f"{MIN_EDITS_FOR_CI} edits.", "",
         "## K1. Does it edit, and is the edit right? (first sampled action at S-use)", "",
         "| Size / condition | samples | edits gold file [95% CI] | edits that pass [95% CI] | pass rate (all samples) | what the other samples do |",
         "|---|---|---|---|---|---|"]
    for k, v in C["K1"].items():
        other = ", ".join(f"{a} {n}" for a, n in v["first_action"].items() if a != "edits gold file")
        L.append(f"| {k} | {v['samples']} | {v['edits_gold_file']} ({pc(v['edit_rate'])}{ci(v['edit_rate_ci'])}) | "
                 f"{v['solves']}/{v['edits_gold_file']} ({pc(v['solve_given_edit'])}{ci(v['solve_given_edit_ci'])}) | "
                 f"{pc(v['solve_rate'])} | {other} |")
    L += ["", "## K2. Paired W vs L2 vs L0 on the tasks that have all three", "",
          "Per-task pass share = passing samples / 2. Δ = mean over tasks of the per-task difference (equals the difference "
          "in pass rate). Wilcoxon on the per-task differences, Holm over the three pairs within a size; McNemar on "
          "\"≥ 1 sample passes\"; Cochran's Q on \"≥ 1 passes\" across L0, L2, W.", "",
          "| Size | tasks | pass rate L0 / L2 / W | tasks ≥1 pass L0 / L2 / W | pair | Δ pass rate [95% CI] | tasks up / down | "
          "Wilcoxon p (Holm) | McNemar p (only first / only second) | Cochran's Q p |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for s, v in C["K2"].items():
        m, a = v["mean_pass_share"], v["tasks_any_pass"]
        for i, (pk, p) in enumerate(v["pairs"].items()):
            head = (f"| {s} | {v['tasks']} | {pc(m['L0'])} / {pc(m['L2'])} / {pc(m['W'])} | {a['L0']} / {a['L2']} / {a['W']} "
                    if i == 0 else "| | | | ")
            lo, hi = p["mean_diff_ci"]
            wp = "—" if p["wilcoxon_p"] is None else f"{p['wilcoxon_p']:.3f} ({p['wilcoxon_p_holm']:.3f})"
            mp = "—" if p["mcnemar_p"] is None else f"{p['mcnemar_p']:.3f}"
            q = v["cochran_q_any_pass"].get("p")
            L.append(head + f"| {pk} | {p['mean_diff']:+.0%} [{lo:+.0%}, {hi:+.0%}] | {p['tasks_up']} / {p['tasks_down']} | {wp} | "
                     f"{mp} ({p['any_pass_only_first']} / {p['any_pass_only_second']}) | "
                     + (("—" if q is None else f"{q:.3f}") if i == 0 else "") + " |")
    L += ["", "## K3. Passing edits that exact-match grading misses", "",
          "| Size / condition | samples | pass | exact | pass & exact | pass, not exact | share of passes missed by exact | "
          "exact but fails | tasks ≥1 pass / ≥1 exact / pass but no exact |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k, v in C["K3"].items():
        L.append(f"| {k} | {v['samples']} | {v['passes']} | {v['exact']} | {v['passes_and_exact']} | {v['passes_not_exact']} | "
                 f"{pc(v['share_of_passes_missed_by_exact'])} | {v['exact_not_passes']} | "
                 f"{v['tasks_any_pass']} / {v['tasks_any_exact']} / {v['tasks_any_pass_no_exact']} |")
    L += ["", "`exact` compares the edited file with the scored gold edit, which covers only the gold function; "
          "`outside_edits` in `C03_probe.json` counts gold-patch lines outside it (non-zero for 12 of the 30 tasks), so an "
          "exact edit can still fail the tests."]
    return "\n".join(L) + "\n"


def main(verify_path: str, *rest: str) -> dict:
    *probe_files, out_dir = rest
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    C = checks(json.loads(Path(verify_path).read_text()), probe_files)
    (out / "C03v_checks.json").write_text(json.dumps(C, indent=1))
    md = tables_md(C)
    (out / "C03v_checks.md").write_text(md)
    print(md)
    return C


if __name__ == "__main__":
    main(*sys.argv[1:])
