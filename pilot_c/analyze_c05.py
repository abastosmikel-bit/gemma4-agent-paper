"""Analysis of the 12b rollout validation, as pre-registered in docs/PLAN_C05_validation.md §7. CPU only.

Inputs : results/C05_validation_12b.json (notebooks/C05_validation_12b__L4x4.ipynb)
         results/C03_probe.json (+ results/C04_probe_followup.json if present: 12b cells C03 did not complete)
Output : results/C05_analysis.json
Usage  : python -m pilot_c.analyze_c05 [validation.json] [c03.json] [c04.json] [out.json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from common import stats as cs

ROOT = Path(__file__).resolve().parents[1]
SIZE = "12b"
MIN_POSITIVES = 4
PREDICTORS = {  # name -> (state, cond, ref, label)
    "H6_d_use_L3-L0": ("use", "L3", "L0", "pre-registered (H6)"),
    "x_d_find_L2-L0": ("find", "L2", "L0", "exploratory"),
}


def probe_logp(paths: list[Path]) -> dict[tuple[str, str, str], float]:
    """(state, cond, task) -> logp for the 12b design cells (rep 1); later files only fill cells missing so far."""
    out: dict[tuple[str, str, str], float] = {}
    for p in paths:
        if not p.exists():
            continue
        for r in json.loads(p.read_text())["d1"]:
            if (r.get("ok") and r.get("size") == SIZE and r.get("rep", 1) == 1
                    and r.get("purpose", "design") == "design"):
                out.setdefault((r["state"], r["cond"], r["task"]), r["logp"])
    return out


def auc_block(scores: dict[str, float], labels: dict[str, int], seed: int = 0) -> dict:
    ts = sorted(set(scores) & set(labels))
    s = np.array([scores[t] for t in ts])
    y = np.array([labels[t] for t in ts])
    pos = int(y.sum())
    res = {"n": len(ts), "positives": pos, "negatives": len(ts) - pos, "auc": None, "ci": None, "dropped_resamples": None,
           "informative": pos >= MIN_POSITIVES and len(ts) - pos >= 1}
    if pos == 0 or pos == len(ts):
        return res
    res["auc"] = round(cs.auc(s, y), 4)
    rng = np.random.default_rng(seed)
    vals, dropped = [], 0
    for _ in range(10_000):
        i = rng.integers(0, len(ts), len(ts))
        a = cs.auc(s[i], y[i])
        if a is None:
            dropped += 1
        else:
            vals.append(a)
    res["ci"] = [round(float(np.quantile(vals, 0.025)), 4), round(float(np.quantile(vals, 0.975)), 4)] if vals else None
    res["dropped_resamples"] = dropped
    return res


def _end(x: dict) -> str:
    e = x.get("error") or ""
    if "ContextWindowExceeded" in e:
        return "context_window_exceeded"
    if "session timeout" in e:
        return "time_budget"
    if "tool call budget" in e:
        return "tool_call_budget"
    return "other_error" if e else "no_error"


def context_and_compaction(V: dict, per: dict, c01: dict | None) -> dict:
    """EXPLORATORY (not in docs/PLAN_C05_validation.md): how runs ended, how that relates to compaction and to the
    hint's effect, and which post-compaction requests still carried the task-prompt marker."""
    rows = {(r["condition"], x["instance_id"]): x for r in V["runs"] for x in r["rows"]}
    out: dict = {"label": "exploratory", "by_condition": {}}
    for c in V["conditions"]:
        xs = [x for (cc, _), x in rows.items() if cc == c]
        cwe = [x for x in xs if _end(x) == "context_window_exceeded"]
        comp = [x for x in xs if (x.get("cmp_compactions") or 0) > 0]
        after = sum(x.get("cmp_requests_after_first_compaction") or 0 for x in xs)
        marked = [x for x in comp if (x.get("cmp_after_with_task_prompt") or 0) > 0]
        out["by_condition"][c] = {
            "runs": len(xs), "ended": dict(sorted({k: sum(1 for x in xs if _end(x) == k) for k in
                                                   {_end(x) for x in xs}}.items())),
            "cwe_without_any_compaction": sum(1 for x in cwe if not x.get("cmp_compactions")),
            "cwe_after_compaction": sum(1 for x in cwe if x.get("cmp_compactions")),
            "tool_calls_at_cwe_without_compaction": sorted(x["tool_calls"] for x in cwe if not x.get("cmp_compactions")),
            "runs_with_compaction": len(comp),
            "compacted_runs_where_task_prompt_event_was_compacted": sum(bool(x.get("cmp_task_prompt_compacted")) for x in comp),
            "requests_after_first_compaction": after,
            "of_which_with_task_prompt_marker": sum(x.get("cmp_after_with_task_prompt") or 0 for x in xs),
            "runs_with_marker_after_compaction": len(marked),
            "marker_runs_all_or_nothing": all(x["cmp_after_with_task_prompt"] == x["cmp_requests_after_first_compaction"] for x in marked),
            "marker_runs": [{"task": x["instance_id"], "after": x["cmp_requests_after_first_compaction"],
                             "with_marker": x["cmp_after_with_task_prompt"], "compactions": x["cmp_compactions"]} for x in marked],
        }
    a, b = V["conditions"]
    ts = sorted(per)
    out["cwe_paired"] = {"both": sum(1 for t in ts if _end(rows[(a, t)]) == _end(rows[(b, t)]) == "context_window_exceeded"),
                         f"{a}_only": sum(1 for t in ts if _end(rows[(a, t)]) == "context_window_exceeded" != _end(rows[(b, t)])),
                         f"{b}_only": sum(1 for t in ts if _end(rows[(b, t)]) == "context_window_exceeded" != _end(rows[(a, t)]))}
    out["unresolved_at_O0_by_how_O0_ended"] = {
        k: {"tasks": len(g), "resolved_with_hint": sum(bool(per[t]["O-all"]) for t in g)}
        for k in sorted({_end(rows[("O0", t)]) for t in ts if not per[t]["O0"]})
        for g in [[t for t in ts if not per[t]["O0"] and _end(rows[("O0", t)]) == k]]}
    if c01:
        cr = [(r["model"], r["condition"], x) for r in c01["runs"] for x in r["rows"]]
        out["c01"] = {"cwe_by_size": {f"{m} {c}": sum(1 for mm, cc, x in cr if (mm, cc) == (m, c) and _end(x) == "context_window_exceeded")
                                      for m, c, _ in cr},
                      "runs_with_compaction": sum(1 for *_, x in cr if (x.get("cmp_compactions") or 0) > 0),
                      "compacted_runs_where_task_prompt_event_was_compacted": sum(1 for *_, x in cr if (x.get("cmp_compactions") or 0) > 0 and x.get("cmp_task_prompt_compacted")),
                      "requests_after_first_compaction": sum(x.get("cmp_requests_after_first_compaction") or 0 for *_, x in cr),
                      "of_which_with_task_prompt_marker": sum(x.get("cmp_after_with_task_prompt") or 0 for *_, x in cr),
                      "marker_runs": [{"run": f"{m} {c}", "task": x["instance_id"], "after": x["cmp_requests_after_first_compaction"],
                                       "with_marker": x["cmp_after_with_task_prompt"]} for m, c, x in cr if (x.get("cmp_after_with_task_prompt") or 0) > 0]}
    return out


def main(val="results/C05_validation_12b.json", c03="results/C03_probe.json", c04="results/C04_probe_followup.json",
         out_path="results/C05_analysis.json") -> dict:
    V = json.loads((ROOT / val).read_text())
    lp = probe_logp([ROOT / c03, ROOT / c04])
    per = {t: v for t, v in V["per_task"].items() if v.get("O0") is not None and v.get("O-all") is not None}
    flips = {"fail_to_pass": sorted(t for t, v in per.items() if not v["O0"] and v["O-all"]),
             "pass_to_fail": sorted(t for t, v in per.items() if v["O0"] and not v["O-all"]),
             "both": sorted(t for t, v in per.items() if v["O0"] and v["O-all"]),
             "neither": sorted(t for t, v in per.items() if not v["O0"] and not v["O-all"])}
    out = {"source": val, "tasks_run": len(per), "stopped": V.get("stopped"), "stages": V.get("stages"),
           "resolved": {c: sum(bool(v[c]) for v in per.values()) for c in ("O0", "O-all")},
           "flips": {k: len(v) for k, v in flips.items()}, "flip_tasks": flips,
           "mcnemar_exact_p": cs.mcnemar_exact(len(flips["fail_to_pass"]), len(flips["pass_to_fail"])),
           "predictors": {}}
    for name, (st, cond, ref, label) in PREDICTORS.items():
        sc = {t: lp[(st, cond, t)] - lp[(st, ref, t)] for t in per if (st, cond, t) in lp and (st, ref, t) in lp}
        primary = {t: int(per[t]["O-all"]) for t in per if not per[t]["O0"]}          # tasks unresolved at O0
        secondary = {t: int(not per[t]["O0"] and per[t]["O-all"]) for t in per}         # all tasks
        out["predictors"][name] = {"label": label, "n_with_value": len(sc),
                                   "primary_unresolved_at_O0": auc_block(sc, primary),
                                   "secondary_all_tasks": auc_block(sc, secondary)}
        p = out["predictors"][name]["primary_unresolved_at_O0"]
        p["criterion_auc_ge_0.65"] = None if not (p["informative"] and p["auc"] is not None) else p["auc"] >= 0.65
    c01p = ROOT / "results" / "C01_smoke_timing.json"
    out["exploratory"] = context_and_compaction(V, per, json.loads(c01p.read_text()) if c01p.exists() else None)
    (ROOT / out_path).write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "flip_tasks"}, indent=1)[:3000])
    return out


if __name__ == "__main__":
    main(*sys.argv[1:])
