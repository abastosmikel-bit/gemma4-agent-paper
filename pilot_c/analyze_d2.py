"""Frozen analysis of notebooks/D2_heldout_rollouts_12b__L4x4.ipynb, as pre-registered in docs/PLAN_D2_heldout_rollouts_12b.md §5.
Standalone: numpy only (matplotlib optional, for the figures); runs as D2's last cell on Kaggle and offline; tested on
synthetic data (tests/test_analyze_d2.py). Reuses C06's helpers (pilot_c/analyze_c06.py) so every number is computed as
in C06.

The dev column comes from the same code run on C06's no-hint runs (30 dev tasks): results/D2_dev_reference.json, built
offline by `python -m pilot_c.analyze_d2 --dev-reference results/C06_validation_fix_12b.json results/C06_failed_edits.json <out>`.

Inputs : D2_heldout_rollouts_12b.json (the notebook's output), D2_dev_reference.json, optionally D2_failed_edits.json
         (pilot_c/edit_failures.py on this session's traces) and the private summaries (Kaggle; numbers are extracted).
Outputs: D2_analysis.json, D2_tables.md, D2_fig1_how_runs_ended.png, D2_fig2_summary_retention.png (numbers only).
Usage  : python -m pilot_c.analyze_d2 <D2_heldout_rollouts_12b.json> <D2_dev_reference.json> <out_dir> [failed_edits.json] [summaries_glob]
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

from pilot_c import analyze_c06 as a6

COND = "O0"
MAX_CRASHES = 1             # R7: at most 1 run ends in ContextWindowExceeded
NEGLIGIBLE_SSC = 0.05       # search_similar_code below 5% of tool calls counts as negligible


def wilson(k: int, n: int, z: float = 1.959964) -> list[float] | None:
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rows_o0(run: dict) -> dict:
    return {k: v for k, v in a6.rows_by(run).items() if k[0] == COND}


def failed_edits_block(fe: dict | None) -> dict | None:
    if not fe:
        return None
    t = fe.get("total", {})
    return {"runs_replayed": len(fe.get("runs", [])), "edits": t.get("edits", 0), "failed": t.get("failed", 0),
            "failed_after_first_compaction": t.get("after_first_compaction", 0),
            "never_matched": t.get("never_matched", 0), "tool_would_accept_now": t.get("tool_would_accept_now", 0),
            "matches_pre_edit_file_only": t.get("matches_pre_edit_file_only", 0),
            "same_old_string_repeated": t.get("same_old_string_repeated", 0)}


def analyze_rows(run: dict, failed_edits: dict | None = None, summaries_glob: str | None = None) -> dict:
    r = rows_o0(run)
    xs = list(r.values())
    n, k = len(xs), sum(bool(x.get("resolved")) for x in xs)
    ends = {e: sum(1 for x in xs if a6.ended(x) == e) for e in a6.ENDS}
    comp = a6.compaction_block(r, COND)
    sn = a6.summary_numbers(summaries_glob, r)
    tools = sum(x.get("tool_calls") or 0 for x in xs)
    ssc = sum((x.get("calls_by_tool") or {}).get("search_similar_code", 0) for x in xs)
    seen = sorted({v for x in xs for v in (x.get("cmp_requested_output_tokens") or [])})
    A = {"runs": n, "setting_check": {"requested_output_tokens_seen": seen, "ok": seen == [8192]},
         "solve_rate": {"resolved": k, "runs": n, "rate": round(k / n, 4) if n else None, "wilson95": wilson(k, n)},
         "ended": ends}
    # R7 / claim 4: the 8192 fix prevents crashes
    A["R7_claim4_crashes"] = {"crashed_runs": ends["context_crash"], "max_allowed": MAX_CRASHES,
                              "context_errors": sum(x.get("cmp_context_errors") or 0 for x in xs),
                              "holds": (ends["context_crash"] <= MAX_CRASHES) if n else None}
    # R6 / claim 2: after compaction no request contains the original statement
    evaluable = comp["runs_with_compaction"] > 0 and comp["requests_after_first_compaction"] > 0
    A["R6_claim2_compaction"] = {**comp, "evaluable": evaluable,
                                 "holds": (comp["with_original_prompt_present"] == 0 and comp["marker_in_original_prompt"] == 0)
                                 if evaluable else None}
    A["summary_retention"] = {"ngram5_recall": a6._q([s["ngram5_recall"] for s in sn]),
                              "word_recall": a6._q([s["word_recall"] for s in sn]),
                              "with_marker": sum(s["has_marker"] for s in sn), "n": len(sn),
                              "source": sn[0]["source"] if sn else None}
    A["summary_points"] = [{k2: s[k2] for k2 in ("ngram5_recall", "word_recall", "has_marker")} for s in sn]
    A["context"] = a6.context_block(r, COND)
    A["failed_edits"] = failed_edits_block(failed_edits)
    A["common_metrics"] = a6.common_metrics(r, COND)
    A["search_similar_code"] = {"calls": ssc, "tool_calls": tools, "share": round(ssc / tools, 4) if tools else None,
                                "runs_using_it": sum(1 for x in xs if (x.get("calls_by_tool") or {}).get("search_similar_code")),
                                "negligible": (ssc / tools < NEGLIGIBLE_SSC) if tools else None}
    A["tool_mix"] = {t: sum((x.get("calls_by_tool") or {}).get(t, 0) for x in xs)
                     for t in sorted({t for x in xs for t in (x.get("calls_by_tool") or {})})}
    A["per_task_resolved"] = {t: bool(x.get("resolved")) for (_, t), x in sorted(r.items())}
    return A


def _verdict(x):
    return {True: "holds", False: "fails", None: "not evaluable"}[x]


def _pct(x):
    return "—" if x is None else f"{100 * x:.0f}%"


def tables_md(A: dict, dev: dict | None) -> str:
    dev = dev or {}
    g = lambda *ks: _get(dev, ks)  # noqa: E731
    s, c, cx = A["solve_rate"], A["R6_claim2_compaction"], A["R7_claim4_crashes"]
    sr, sm = A["summary_retention"], A["search_similar_code"]
    wci = "—" if not s["wilson95"] else f"{100 * s['wilson95'][0]:.0f}–{100 * s['wilson95'][1]:.0f}%"
    T = ["# D2 held-out rollouts, 12b, C06 configuration (docs/PLAN_D2_heldout_rollouts_12b.md)", "",
         f"{A['runs']} held-out tasks ({A.get('selection', {}).get('selected_by_repo')}), no hint (O0), 1 run each, "
         "`max_output_tokens` 8192. Dev = C06's no-hint runs on the 30 dev tasks, same code.", "",
         f"Setting check (every request asked for 8192 output tokens): {'ok' if A['setting_check']['ok'] else 'FAILED'} "
         f"{A['setting_check']['requested_output_tokens_seen']}.", "",
         "| measure | held-out | dev (C06, O0) | criterion |", "|---|---|---|---|",
         f"| solved (scorer rule) | {s['resolved']}/{s['runs']} = {_pct(s['rate'])}, Wilson 95% "
         f"{wci} | "
         f"{g('solve_rate', 'resolved')}/{g('solve_rate', 'runs')} | reported, no test (repos differ) |",
         f"| R7: runs ending in ContextWindowExceeded | {cx['crashed_runs']} | {g('R7_claim4_crashes', 'crashed_runs')} | ≤ {MAX_CRASHES}: **{_verdict(cx['holds'])}** |",
         f"| R6: post-compaction requests with the original statement | {c['with_original_prompt_present']} of "
         f"{c['requests_after_first_compaction']} ({c['runs_with_compaction']} runs compacted) | "
         f"{g('R6_claim2_compaction', 'with_original_prompt_present')} of {g('R6_claim2_compaction', 'requests_after_first_compaction')} | "
         f"0: **{_verdict(c['holds'])}** |",
         f"| marker only in a summary after compaction | {c['marker_in_summary_only']} | {g('R6_claim2_compaction', 'marker_in_summary_only')} | — |",
         f"| summaries; with the marker | {c['summaries']}; {c['summaries_with_marker']} | {g('R6_claim2_compaction', 'summaries')}; "
         f"{g('R6_claim2_compaction', 'summaries_with_marker')} | — |",
         f"| statement 5-gram retention per summary, median | {_q(sr['ngram5_recall'])} | {_q(g('summary_retention', 'ngram5_recall'))} | — |",
         f"| search_similar_code share of tool calls | {_pct(sm['share'])} ({sm['calls']} calls, {sm['runs_using_it']} runs) | "
         f"{_pct(g('search_similar_code', 'share'))} | negligible if < {NEGLIGIBLE_SSC:.0%}: {sm['negligible']} |"]
    fe, fd = A.get("failed_edits"), g("failed_edits") or {}
    if fe:
        T.append(f"| failed edits; after the first compaction | {fe['failed']} of {fe['edits']}; {fe['failed_after_first_compaction']} | "
                 f"{fd.get('failed')} of {fd.get('edits')}; {fd.get('failed_after_first_compaction')} | — |")
    T += ["", "## How runs ended", "", "| ended | held-out | dev |", "|---|---|---|"]
    for e in a6.ENDS:
        T.append(f"| {e} | {A['ended'][e]} | {g('ended', e)} |")
    T += ["", "## Shared metrics (means per run)", "", "| metric | held-out | dev |", "|---|---|---|"]
    for k, v in A["common_metrics"].items():
        T.append(f"| {k} | {v} | {g('common_metrics', k)} |")
    T += ["", f"Tool mix: {json.dumps(A['tool_mix'])}", "", f"Context: {json.dumps(A['context'])}", ""]
    return "\n".join(T)


def _get(d, ks):
    for k in ks:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _q(q):
    return "—" if not q else f"{100 * q['median']:.0f}% (IQR {100 * q['q25']:.0f}–{100 * q['q75']:.0f}%, n={q['n']})"


def figures(A: dict, dev: dict | None, out: Path) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return []
    dev = dev or {}
    made = []
    fig, ax = plt.subplots(figsize=(7.5, 2.6))
    colors = {"resolved": "#54A24B", "context_crash": "#E45756", "time_budget": "#F58518", "tool_call_budget": "#EECA3B",
              "unresolved_other": "#BAB0AC"}
    for y, (lab, src) in enumerate((("held-out (D2)", A), ("dev (C06, O0)", dev))):
        e = src.get("ended") or {}
        tot = sum(e.values()) or 1
        left = 0.0
        for k in a6.ENDS:
            w = e.get(k, 0) / tot
            ax.barh(y, w, left=left, color=colors[k], edgecolor="white", label=k if y == 0 else None)
            if e.get(k):
                ax.text(left + w / 2, y, str(e[k]), ha="center", va="center", fontsize=8, color="white")
            left += w
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["held-out (D2)", "dev (C06, O0)"])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("share of runs")
    ax.legend(frameon=False, fontsize=7, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.35))
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "D2_fig1_how_runs_ended.png", dpi=150)
    plt.close(fig)
    made.append("D2_fig1_how_runs_ended.png")
    fig, ax = plt.subplots(figsize=(5.5, 3.2))
    data = [[p["ngram5_recall"] for p in (src.get("summary_points") or []) if p.get("ngram5_recall") is not None]
            for src in (A, dev)]
    for i, v in enumerate(data):
        if v:
            ax.scatter(np.full(len(v), i) + np.random.default_rng(i).uniform(-0.12, 0.12, len(v)), v, s=12, alpha=0.6,
                       color=["#4C78A8", "#9D755D"][i])
            ax.plot([i - 0.2, i + 0.2], [np.median(v)] * 2, color="black", lw=1.5)
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["held-out (D2)", "dev (C06, O0)"])
    ax.set_ylim(-0.02, 1)
    ax.set_ylabel("statement 5-grams kept per summary")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "D2_fig2_summary_retention.png", dpi=150)
    plt.close(fig)
    made.append("D2_fig2_summary_retention.png")
    return made


def main(d2_path: str, dev_path: str | None, out_dir: str = ".", failed_edits_path: str | None = None,
         summaries_glob: str | None = None) -> dict:
    run = json.loads(Path(d2_path).read_text())
    dev = json.loads(Path(dev_path).read_text()) if dev_path and Path(dev_path).exists() else None
    fe = json.loads(Path(failed_edits_path).read_text()) if failed_edits_path and Path(failed_edits_path).exists() else None
    A = analyze_rows(run, fe, summaries_glob)
    A.update({"plan": "docs/PLAN_D2_heldout_rollouts_12b.md", "notebook": run.get("notebook"), "plan_commit": run.get("plan_commit"),
              "task_ids": run.get("task_ids"), "selection": run.get("selection") or {}, "stopped": run.get("stopped"),
              "session_elapsed_h": run.get("session_elapsed_h"), "dev_reference": bool(dev)})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    A["figures"] = figures(A, dev, out)
    (out / "D2_analysis.json").write_text(json.dumps(A, indent=1))
    md = tables_md(A, dev)
    (out / "D2_tables.md").write_text(md)
    print(md)
    return A


def dev_reference(c06_path: str, failed_edits_path: str | None, out_path: str) -> dict:
    c06 = json.loads(Path(c06_path).read_text())
    fe = json.loads(Path(failed_edits_path).read_text()) if failed_edits_path and Path(failed_edits_path).exists() else None
    A = analyze_rows(c06, fe, None)
    A["source"] = "dev: results/C06_validation_fix_12b.json, no-hint runs (O0), 30 dev tasks; summary retention = per-run means"
    Path(out_path).write_text(json.dumps(A, indent=1))
    print(json.dumps({k: A[k] for k in ("solve_rate", "R6_claim2_compaction", "R7_claim4_crashes", "search_similar_code")}, indent=1))
    return A


if __name__ == "__main__":
    if sys.argv[1] == "--dev-reference":
        dev_reference(*sys.argv[2:5])
    else:
        main(*sys.argv[1:6])
