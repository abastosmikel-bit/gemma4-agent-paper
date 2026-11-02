"""Analysis of the C05 validation rerun with max_output_tokens = 8192, as pre-registered in
docs/PLAN_C06_validation_fix.md §6. Standalone: numpy + math only (matplotlib optional, for the figures), so it runs
in the notebook's last cell on Kaggle and offline.

Inputs : C06 output (notebooks/C06_validation_fix_12b__L4x4.ipynb), C05 output (results/C05_validation_12b.json),
         12b probe predictors (results/C06_predictors_12b.json, built from C03 by build_predictors),
         optionally the private summaries (private/runs/12b/*/summaries.jsonl, Kaggle only: numbers are extracted).
Outputs: C06_analysis.json, C06_tables.md, C06_fig1_how_runs_ended.png, C06_fig2_hint_effect.png,
         C06_fig3_summary_retention.png (numbers only; no task text).
Usage  : python -m pilot_c.analyze_c06 <c06.json> <c05.json> <predictors.json> <out_dir> [summaries_glob]
"""
from __future__ import annotations

import glob
import json
import math
import sys
from pathlib import Path

import numpy as np

CONDS = ("O0", "O-all")
ENDS = ("resolved", "context_crash", "time_budget", "tool_call_budget", "unresolved_other")
MIN_POSITIVES = 4
PREDICTORS = {"H6_d_use_L3-L0": ("d_use_L3_L0", "pre-registered (H6)"),
              "x_d_find_L2-L0": ("d_find_L2_L0", "exploratory")}


# --------------------------------------------------------------------------- small exact statistics (no scipy)

def mcnemar_exact(b: int, c: int) -> float | None:
    m = b + c
    if m == 0:
        return None
    k = min(b, c)
    return round(min(1.0, 2 * sum(math.comb(m, i) for i in range(k + 1)) / 2 ** m), 6)


def auc(scores: np.ndarray, labels: np.ndarray) -> float | None:
    pos, neg = scores[labels == 1], scores[labels == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def auc_block(scores: dict[str, float], labels: dict[str, int], seed: int = 0) -> dict:
    ts = sorted(set(scores) & set(labels))
    s, y = np.array([scores[t] for t in ts], float), np.array([labels[t] for t in ts], int)
    pos = int(y.sum())
    res = {"n": len(ts), "positives": pos, "negatives": len(ts) - pos, "auc": None, "ci": None,
           "dropped_resamples": None, "informative": pos >= MIN_POSITIVES and len(ts) - pos >= 1}
    a = auc(s, y)
    if a is None:
        return res
    res["auc"] = round(a, 4)
    rng = np.random.default_rng(seed)
    vals, dropped = [], 0
    for _ in range(10_000):
        i = rng.integers(0, len(ts), len(ts))
        v = auc(s[i], y[i])
        if v is None:
            dropped += 1
        else:
            vals.append(v)
    res["ci"] = [round(float(np.quantile(vals, 0.025)), 4), round(float(np.quantile(vals, 0.975)), 4)] if vals else None
    res["dropped_resamples"] = dropped
    return res


def _q(xs: list[float]) -> dict | None:
    v = [x for x in xs if x is not None]
    if not v:
        return None
    return {"n": len(v), "median": round(float(np.median(v)), 4), "q25": round(float(np.quantile(v, 0.25)), 4),
            "q75": round(float(np.quantile(v, 0.75)), 4), "max": round(float(max(v)), 4)}


# --------------------------------------------------------------------------- data access

def ended(x: dict) -> str:
    e = x.get("error") or ""
    if "ContextWindowExceeded" in e:
        return "context_crash"
    if x.get("resolved"):
        return "resolved"
    if "session timeout" in e:
        return "time_budget"
    if "tool call budget" in e:
        return "tool_call_budget"
    return "unresolved_other"


def rows_by(run: dict) -> dict[tuple[str, str], dict]:
    return {(r["condition"], x["instance_id"]): x for r in run["runs"] for x in r["rows"]}


def build_predictors(c03_path: str, c04_path: str | None = None, size: str = "12b") -> dict[str, dict[str, float]]:
    """Per task: Δ_use(L3−L0) (H6) and Δ_find(L2−L0) for `size`, from C03's depth-1 design cells; cells C03 did not
    complete are filled from C04 when given (PLAN_C05 §7). Numbers only."""
    lp: dict[tuple[str, str, str], float] = {}
    for p in [c03_path, c04_path]:
        if p and Path(p).exists():
            for r in json.loads(Path(p).read_text())["d1"]:
                if r.get("ok") and r.get("size") == size and r.get("rep", 1) == 1 and r.get("purpose", "design") == "design":
                    lp.setdefault((r["state"], r["cond"], r["task"]), r["logp"])
    tasks = sorted({k[2] for k in lp})
    out = {}
    for t in tasks:
        v = {}
        if ("use", "L3", t) in lp and ("use", "L0", t) in lp:
            v["d_use_L3_L0"] = round(lp[("use", "L3", t)] - lp[("use", "L0", t)], 4)
        if ("find", "L2", t) in lp and ("find", "L0", t) in lp:
            v["d_find_L2_L0"] = round(lp[("find", "L2", t)] - lp[("find", "L0", t)], 4)
        if v:
            out[t] = v
    return out


# --------------------------------------------------------------------------- analyses (PLAN_C06 §6)

def hint_effect(rows: dict, tasks: list[str], exclude_crash: bool) -> dict:
    keep = [t for t in tasks if all((c, t) in rows for c in CONDS)
            and not (exclude_crash and any(ended(rows[(c, t)]) == "context_crash" for c in CONDS))]
    res = {c: sum(bool(rows[(c, t)].get("resolved")) for t in keep) for c in CONDS}
    f2p = sum(1 for t in keep if not rows[("O0", t)].get("resolved") and rows[("O-all", t)].get("resolved"))
    p2f = sum(1 for t in keep if rows[("O0", t)].get("resolved") and not rows[("O-all", t)].get("resolved"))
    return {"tasks": len(keep), "resolved": res, "fail_to_pass": f2p, "pass_to_fail": p2f,
            "mcnemar_exact_p": mcnemar_exact(f2p, p2f)}


def summary_numbers(summaries_glob: str | None, rows06: dict) -> list[dict]:
    """Per-summary retention numbers. From the private summaries files when available (Kaggle), else per-run means."""
    out = []
    if summaries_glob:
        for f in sorted(glob.glob(summaries_glob)):
            cond = "O-all" if "/O-all_" in f else "O0"
            for line in open(f, encoding="utf-8"):
                s = json.loads(line)
                out.append({"condition": cond, "task": s.get("task"), "ngram5_recall": s.get("ngram5_recall"),
                            "word_recall": s.get("word_recall"), "has_marker": bool(s.get("has_marker")), "source": "summaries"})
    if not out:
        for (c, t), x in rows06.items():
            if x.get("cmp_summaries"):
                out.append({"condition": c, "task": t, "ngram5_recall": x.get("cmp_summary_ngram5_recall_mean"),
                            "word_recall": x.get("cmp_summary_word_recall_mean"),
                            "has_marker": bool(x.get("cmp_summaries_with_marker")), "source": "per-run mean"})
    return out


def compaction_block(rows: dict, c: str) -> dict:
    xs = [x for (cc, _), x in rows.items() if cc == c]
    comp = [x for x in xs if (x.get("cmp_compactions") or 0) > 0]
    g = lambda k: sum(x.get(k) or 0 for x in comp)  # noqa: E731
    return {"runs": len(xs), "runs_with_compaction": len(comp),
            "task_prompt_event_compacted": sum(bool(x.get("cmp_task_prompt_compacted")) for x in comp),
            "requests_after_first_compaction": g("cmp_requests_after_first_compaction"),
            "with_marker_any_source": g("cmp_after_with_task_prompt"),
            "marker_in_original_prompt": g("cmp_after_marker_in_prompt"),
            "marker_in_summary_only": g("cmp_after_marker_in_summary_only"),
            "marker_elsewhere_only": g("cmp_after_marker_other_only"),
            "with_original_prompt_present": g("cmp_after_with_original_prompt"),
            "summaries": sum(x.get("cmp_summaries") or 0 for x in xs),
            "summaries_with_marker": sum(x.get("cmp_summaries_with_marker") or 0 for x in xs)}


def context_block(rows: dict, c: str) -> dict:
    xs = [x for (cc, _), x in rows.items() if cc == c]
    req = sorted({v for x in xs for v in (x.get("cmp_requested_output_tokens") or [])})
    return {"requested_output_tokens_seen": req,
            "max_prompt_tokens": _q([x.get("cmp_max_prompt_tokens") for x in xs]),
            "context_errors": sum(x.get("cmp_context_errors") or 0 for x in xs),
            "prompt_tokens_before_first_context_error": sorted(x["cmp_prompt_tokens_before_first_context_error"] for x in xs
                                                               if x.get("cmp_prompt_tokens_before_first_context_error"))}


def common_metrics(rows: dict, c: str) -> dict:
    xs = [x for (cc, _), x in rows.items() if cc == c]
    m = lambda k: round(float(np.mean([x.get(k) or 0 for x in xs])), 3) if xs else None  # noqa: E731
    return {"runs": len(xs), "resolved": sum(bool(x.get("resolved")) for x in xs), "wall_s_mean": m("wall_s"),
            "tool_calls_mean": m("tool_calls"), "repeat_share_mean": m("repeat_share"),
            "malformed_share_mean": m("malformed_share"), "failed_edits_total": sum(x.get("failed_edits") or 0 for x in xs),
            "skill_calls_total": sum(x.get("skill_calls") or 0 for x in xs)}


def analyze(c06: dict, c05: dict, predictors: dict, summaries_glob: str | None = None) -> dict:
    r6, r5 = rows_by(c06), rows_by(c05)
    tasks = [t for t in c06["task_ids"] if all((c, t) in r6 for c in CONDS)]        # tasks C06 ran in both conditions
    A: dict = {"plan": "docs/PLAN_C06_validation_fix.md", "tasks_compared": len(tasks), "stopped": c06.get("stopped"),
               "stages": [{k: s.get(k) for k in ("stage", "discordant", "b_only", "a_only", "skipped")} for s in c06.get("stages", [])],
               "session_elapsed_h": c06.get("session_elapsed_h")}
    # setting check: every request must have asked for 8192 output tokens
    seen = sorted({v for x in r6.values() for v in (x.get("cmp_requested_output_tokens") or [])})
    A["setting_check"] = {"requested_output_tokens_seen": seen, "ok": seen == [8192]}
    # A1 crashes per condition, C06 vs C05 (same tasks)
    A["A1_crashes"] = {}
    for c in CONDS:
        t_ok = [t for t in tasks if (c, t) in r5]
        k5 = {t: int(ended(r5[(c, t)]) == "context_crash") for t in t_ok}
        k6 = {t: int(ended(r6[(c, t)]) == "context_crash") for t in t_ok}
        b = sum(1 for t in t_ok if k5[t] and not k6[t])
        cc = sum(1 for t in t_ok if not k5[t] and k6[t])
        A["A1_crashes"][c] = {"tasks": len(t_ok), "C05": sum(k5.values()), "C06": sum(k6.values()),
                              "crash_C05_only": b, "crash_C06_only": cc, "mcnemar_exact_p": mcnemar_exact(b, cc),
                              "ended_C05": {e: sum(1 for t in t_ok if ended(r5[(c, t)]) == e) for e in ENDS},
                              "ended_C06": {e: sum(1 for t in t_ok if ended(r6[(c, t)]) == e) for e in ENDS}}
    # A2 / A3 hint effect: all tasks (crash = failure) and with crashes removed; C05 on the same tasks for comparison
    A["A2_hint_effect_all"] = {"C06": hint_effect(r6, tasks, False), "C05": hint_effect(r5, tasks, False)}
    A["A3_hint_effect_crashes_removed"] = {"C06": hint_effect(r6, tasks, True), "C05": hint_effect(r5, tasks, True)}
    # A4 H6 replication on C06 outcomes
    A["A4_predictors"] = {}
    for name, (key, label) in PREDICTORS.items():
        sc = {t: predictors[t][key] for t in tasks if t in predictors and key in predictors[t]}
        primary = {t: int(bool(r6[("O-all", t)].get("resolved"))) for t in tasks if not r6[("O0", t)].get("resolved")}
        secondary = {t: int(not r6[("O0", t)].get("resolved") and bool(r6[("O-all", t)].get("resolved"))) for t in tasks}
        p = auc_block(sc, primary)
        p["criterion_auc_ge_0.65"] = None if not (p["informative"] and p["auc"] is not None) else p["auc"] >= 0.65
        A["A4_predictors"][name] = {"label": label, "n_with_value": len(sc), "primary_unresolved_at_O0": p,
                                    "secondary_all_tasks": auc_block(sc, secondary)}
    # A5 compaction and summaries; A6 context numbers; A7 common metrics
    A["A5_compaction"] = {c: compaction_block(r6, c) for c in CONDS}
    sn = summary_numbers(summaries_glob, r6)
    A["A5_summary_retention"] = {c: {"ngram5_recall": _q([s["ngram5_recall"] for s in sn if s["condition"] == c]),
                                     "word_recall": _q([s["word_recall"] for s in sn if s["condition"] == c]),
                                     "with_marker": sum(s["has_marker"] for s in sn if s["condition"] == c),
                                     "n": sum(1 for s in sn if s["condition"] == c),
                                     "source": sn[0]["source"] if sn else None} for c in CONDS}
    A["A5_summary_points"] = [{k: s[k] for k in ("condition", "ngram5_recall", "word_recall", "has_marker")} for s in sn]
    A["A6_context"] = {c: context_block(r6, c) for c in CONDS}
    A["A7_common_metrics"] = {"C06": {c: common_metrics(r6, c) for c in CONDS},
                              "C05_same_tasks": {c: common_metrics({k: v for k, v in r5.items() if k[1] in tasks}, c) for c in CONDS}}
    return A


# --------------------------------------------------------------------------- tables and figures

def _p(p):
    return "—" if p is None else ("<0.001" if p < 0.001 else f"{p:.3f}")


def tables_md(A: dict) -> str:
    L = ["# C06 validation rerun (max_output_tokens 8192) — tables (data only)", "",
         f"Plan: `{A['plan']}`. Tasks run in both conditions: {A['tasks_compared']}. Stopped: {A['stopped']}. "
         f"Session: {A['session_elapsed_h']} h. Setting check (requested output tokens seen): "
         f"{A['setting_check']['requested_output_tokens_seen']} → {'OK' if A['setting_check']['ok'] else 'NOT APPLIED'}.", "",
         "## A1. How runs ended, C05 vs C06 (same tasks)", "",
         "| Condition | Run | " + " | ".join(ENDS) + " | crash McNemar (C05→C06) |", "|---|---|" + "---|" * (len(ENDS) + 1)]
    for c, v in A["A1_crashes"].items():
        for run in ("C05", "C06"):
            L.append(f"| {c} | {run} | " + " | ".join(str(v[f"ended_{run}"][e]) for e in ENDS) + " | "
                     + (f"{v['crash_C05_only']} vs {v['crash_C06_only']}, p={_p(v['mcnemar_exact_p'])}" if run == "C06" else "") + " |")
    L += ["", "## A2–A3. Hint effect (O-all vs O0)", "", "| Run | Tasks | crashes | O0 resolved | O-all resolved | fail→pass | pass→fail | McNemar p |",
          "|---|---|---|---|---|---|---|---|"]
    for lab, key in (("all tasks (crash = failure)", "A2_hint_effect_all"), ("crashes removed", "A3_hint_effect_crashes_removed")):
        for run in ("C06", "C05"):
            h = A[key][run]
            L.append(f"| {run} | {h['tasks']} | {lab} | {h['resolved']['O0']} | {h['resolved']['O-all']} | {h['fail_to_pass']} | "
                     f"{h['pass_to_fail']} | {_p(h['mcnemar_exact_p'])} |")
    L += ["", "## A4. Probe predictors of fail→pass (C06 outcomes)", "", "| Predictor | Set | n | positives | AUC [95% CI] | criterion ≥ 0.65 |",
          "|---|---|---|---|---|---|"]
    for name, v in A["A4_predictors"].items():
        for setname in ("primary_unresolved_at_O0", "secondary_all_tasks"):
            b = v[setname]
            ci = f"{b['auc']} [{b['ci'][0]}, {b['ci'][1]}]" if b.get("auc") is not None and b.get("ci") else str(b.get("auc"))
            crit = v[setname].get("criterion_auc_ge_0.65", "—") if setname.startswith("primary") else "—"
            L.append(f"| {name} ({v['label']}) | {setname} | {b['n']} | {b['positives']} | {ci}{'' if b['informative'] else ' (not informative)'} | {crit} |")
    L += ["", "## A5. Compaction: where the task-prompt marker sits after compaction; summary retention", "",
          "| Condition | runs compacted | prompt event compacted | requests after | marker: original prompt | summary only | elsewhere only | original prompt present | summaries (with marker) | 5-gram recall median [IQR] (max) | word recall median |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in CONDS:
        b, r = A["A5_compaction"][c], A["A5_summary_retention"][c]
        g5, wr = r["ngram5_recall"], r["word_recall"]
        L.append(f"| {c} | {b['runs_with_compaction']}/{b['runs']} | {b['task_prompt_event_compacted']} | {b['requests_after_first_compaction']} | "
                 f"{b['marker_in_original_prompt']} | {b['marker_in_summary_only']} | {b['marker_elsewhere_only']} | {b['with_original_prompt_present']} | "
                 f"{b['summaries']} ({b['summaries_with_marker']}) | "
                 + (f"{g5['median']} [{g5['q25']}, {g5['q75']}] ({g5['max']})" if g5 else "—") + " | " + (f"{wr['median']}" if wr else "—") + " |")
    L += ["", "## A6. Context numbers", "", "| Condition | requested output tokens | max prompt tokens per run, median [IQR] (max) | context errors | prompt tokens before first error |",
          "|---|---|---|---|---|"]
    for c in CONDS:
        b = A["A6_context"][c]
        q = b["max_prompt_tokens"]
        L.append(f"| {c} | {b['requested_output_tokens_seen']} | " + (f"{q['median']} [{q['q25']}, {q['q75']}] ({q['max']})" if q else "—")
                 + f" | {b['context_errors']} | {b['prompt_tokens_before_first_context_error']} |")
    L += ["", "## A7. Common metrics", "", "| Run | Condition | runs | resolved | wall s mean | tool calls mean | repeat share | malformed share | failed edits | skill calls |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for run in ("C06", "C05_same_tasks"):
        for c in CONDS:
            m = A["A7_common_metrics"][run][c]
            L.append(f"| {run} | {c} | {m['runs']} | {m['resolved']} | {m['wall_s_mean']} | {m['tool_calls_mean']} | {m['repeat_share_mean']} | "
                     f"{m['malformed_share_mean']} | {m['failed_edits_total']} | {m['skill_calls_total']} |")
    return "\n".join(L) + "\n"


SURF, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e0"
END_COLORS = {"resolved": "#2a78d6", "context_crash": "#eb6834", "time_budget": "#1baf7a", "tool_call_budget": "#eda100",
              "unresolved_other": "#e87ba4"}
COND_COLORS = {"O0": "#2a78d6", "O-all": "#eb6834"}


def figures(A: dict, out_dir: Path) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # noqa: BLE001
        print("figures skipped (matplotlib unavailable):", type(e).__name__)
        return []
    made = []

    def style(ax):
        ax.set_facecolor(SURF)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color(INK2)
        ax.tick_params(colors=INK2, labelsize=8, length=0)
        ax.grid(axis="x", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)

    # fig 1: how runs ended
    labels, data = [], []
    for c in CONDS:
        for run in ("C05", "C06"):
            labels.append(f"{run} {c}")
            data.append(A["A1_crashes"][c][f"ended_{run}"])
    fig, ax = plt.subplots(figsize=(8, 3.2), facecolor=SURF)
    for i, d in enumerate(data):
        left = 0
        for e in ENDS:
            if d[e]:
                ax.barh(i, d[e], left=left, color=END_COLORS[e], edgecolor=SURF, linewidth=2, height=0.6)
                ax.text(left + d[e] / 2, i, str(d[e]), ha="center", va="center", fontsize=7, color=INK)
            left += d[e]
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("runs (12b, 30 tasks per condition)", color=INK2, fontsize=8)
    style(ax)
    import matplotlib.patches as mp
    fig.legend(handles=[mp.Patch(color=END_COLORS[e], label=e.replace("_", " ")) for e in ENDS], loc="upper left",
               bbox_to_anchor=(0.01, 0.92), ncol=len(ENDS), frameon=False, fontsize=7)
    fig.suptitle("How runs ended: C05 (max_output_tokens 16384) vs C06 (8192)", color=INK, fontsize=10, x=0.01, y=0.99, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.82))
    p = out_dir / "C06_fig1_how_runs_ended.png"
    fig.savefig(p, dpi=200, facecolor=SURF)
    plt.close(fig)
    made.append(str(p))

    # fig 2: hint effect, all tasks vs crashes removed
    rows = []
    for run in ("C05", "C06"):
        for lab, key in (("all tasks", "A2_hint_effect_all"), ("crashes removed", "A3_hint_effect_crashes_removed")):
            h = A[key][run]
            if h["tasks"]:
                rows.append((f"{run}, {lab} (n={h['tasks']})", {c: h["resolved"][c] / h["tasks"] for c in CONDS}))
    fig, ax = plt.subplots(figsize=(8, 2.8), facecolor=SURF)
    for i, (lab, v) in enumerate(rows):
        ax.plot([v["O0"], v["O-all"]], [i, i], color=GRID, linewidth=2, zorder=1)
        for c, dy in (("O0", -0.12), ("O-all", 0.12)):   # dodged so equal rates stay visible
            ax.plot([v[c]], [i + dy], marker="o" if c == "O0" else "D", color=COND_COLORS[c], markersize=6,
                    markeredgecolor=SURF, linestyle="none", zorder=2, label=c if i == 0 else None)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(-0.02, 1.02)
    ax.set_xlabel("share of tasks resolved", color=INK2, fontsize=8)
    style(ax)
    fig.legend(loc="upper left", bbox_to_anchor=(0.01, 0.92), ncol=2, frameon=False, fontsize=8)
    fig.suptitle("Hint effect (O-all vs O0), with and without crashed runs", color=INK, fontsize=10, x=0.01, y=0.99, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.80))
    p = out_dir / "C06_fig2_hint_effect.png"
    fig.savefig(p, dpi=200, facecolor=SURF)
    plt.close(fig)
    made.append(str(p))

    # fig 3: summary retention per summary
    pts = A["A5_summary_points"]
    fig, ax = plt.subplots(figsize=(8, 2.6), facecolor=SURF)
    rng = np.random.default_rng(0)
    for i, c in enumerate(CONDS):
        for mk in (False, True):
            xs = [s["ngram5_recall"] for s in pts if s["condition"] == c and s["has_marker"] == mk and s["ngram5_recall"] is not None]
            ys = i + rng.uniform(-0.18, 0.18, len(xs))
            ax.scatter(xs, ys, s=18, color=COND_COLORS[c] if mk else SURF, edgecolors=COND_COLORS[c], linewidths=1.2,
                       label=f"{c}, summary {'has' if mk else 'lacks'} the header")
    ax.set_yticks(range(len(CONDS)))
    ax.set_yticklabels(CONDS)
    ax.set_xlim(-0.02, 1.02)
    ax.set_xlabel("share of the task statement's word 5-grams kept in the summary", color=INK2, fontsize=8)
    style(ax)
    fig.legend(loc="upper left", bbox_to_anchor=(0.01, 0.92), ncol=2, frameon=False, fontsize=7)
    fig.suptitle("Compaction summaries: how much of the task statement survives", color=INK, fontsize=10, x=0.01, y=0.99, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.70))
    p = out_dir / "C06_fig3_summary_retention.png"
    fig.savefig(p, dpi=200, facecolor=SURF)
    plt.close(fig)
    made.append(str(p))
    return made


def main(c06_path: str, c05_path: str, predictors_path: str, out_dir: str = ".", summaries_glob: str | None = None) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    P = json.loads(Path(predictors_path).read_text())
    A = analyze(json.loads(Path(c06_path).read_text()), json.loads(Path(c05_path).read_text()),
                P.get("tasks", P), summaries_glob)
    A["figures"] = [Path(f).name for f in figures(A, out)]
    (out / "C06_analysis.json").write_text(json.dumps(A, indent=1))
    md = tables_md(A)
    (out / "C06_tables.md").write_text(md)
    print(md)
    return A


if __name__ == "__main__":
    main(*sys.argv[1:])
