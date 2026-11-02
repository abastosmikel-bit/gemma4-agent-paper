"""Final analysis of the probe follow-up (notebooks/C04_probe_followup__L4x4.ipynb) together with C03. Standalone: it runs
as C04's last cell on Kaggle and offline, and is tested on synthetic data (tests/test_analyze_c04.py).
Needs numpy, scipy (common/stats.py) and, for figures, matplotlib (all preinstalled on Kaggle; the wheelhouse ships none).

Outputs in out_dir (numbers only):
  C03C04_analysis.json, C03C04_tables.md, C03C04_fig1-3.png/svg  the pre-registered tables and figures (docs/PLAN.md §6-7)
        recomputed with C04's design cells merged in (12b depth 1 complete, 12b depth 2); supersede C03's for 12b
  C04_analysis.json, C04_tables.md, C04_fig4_graph_control.png, C04_fig5_action_args.png   exploratory additions
        (docs/PLAN.md §11 items 11-14): G-null control, X-graph at depth 2, action/arguments split, re-score agreement
Usage: python -m pilot_c.analyze_c04 <C03_probe.json> <C04_probe_followup.json> <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from pilot_c import analyze_c03 as a3
from pilot_c import probe as pb

DESIGN_D2 = {("find", c) for c in pb.D2_FIND} | {("use", c) for c in pb.D2_USE}
SPLIT_CONDS = {"find": ("L1", "L2", "G-json", "X-graph", "G-null"), "use": ("L2", "L5", "W", "G-null")}
GRAPH_ROWS = [("G-json-L0", "G-json", "L0"), ("G-null-L0", "G-null", "L0"), ("G-json-G-null", "G-json", "G-null"),
              ("X-graph-G-null", "X-graph", "G-null"), ("X-file-L0", "X-file", "L0"), ("L1-L0", "L1", "L0")]


def merge_design(c03: dict, c04: dict) -> dict:
    """C03 plus C04's pre-registered design cells (PLAN §11 item 10). Controls and re-scores are left out."""
    done = {r["size"] for r in c04["d1"] if r.get("purpose") == "design" and r.get("ok")}
    sizes = [dict(e, skipped=("completed by C04" if (e.get("size") in done and e.get("skipped")) else e.get("skipped")))
             for e in c03["sizes"]]
    return {**{k: c03.get(k) for k in ("plan_commit", "task_ids", "excluded", "controls", "outside_edits", "freezes")},
            "sizes": sizes, "session_elapsed_h": round((c03.get("session_elapsed_h") or 0) + (c04.get("session_elapsed_h") or 0), 3),
            "d1": c03["d1"] + [r for r in c04["d1"] if r.get("purpose") == "design"],
            "d2": c03["d2"] + [r for r in c04["d2"] if (r.get("state"), r.get("cond")) in DESIGN_D2]}


def with_controls(merged: dict, c04: dict) -> dict:
    return {**merged, "d1": merged["d1"] + [r for r in c04["d1"] if r.get("purpose") == "control"],
            "d2": merged["d2"] + [r for r in c04["d2"] if (r.get("state"), r.get("cond")) not in DESIGN_D2]}


def graph_control(D: a3.Data) -> dict:
    out = {}
    for size in D.sizes:
        for state in ("find", "use"):
            out[f"{size}/{state}"] = {name: a3.summ(D.delta(size, state, a, b)) for name, a, b in GRAPH_ROWS}
    d2 = {}
    for size in D.d2_sizes:
        base = {t: rs[0] for t, rs in D.d2.get((size, "find", "L0"), {}).items()}
        for c in ("L0", "G-json", "X-graph", "G-null"):
            rows = {t: rs[0] for t, rs in D.d2.get((size, "find", c), {}).items()}
            if not rows:
                continue
            ent = {"n": len(rows), **{m: a3._r(np.mean([bool(r.get(m)) for r in rows.values()])) for m in ("hit_file", "hit_func", "followed_wrong")}}
            if c != "L0":
                ent["hit_file_vs_L0"] = a3.mcnemar_tasks({t: int(bool(r.get("hit_file"))) for t, r in base.items()},
                                                         {t: int(bool(r.get("hit_file"))) for t, r in rows.items()})
            d2[f"{size}/{c}"] = ent
    out["depth2_find"] = d2
    return out


def split_rows(c04: dict) -> dict:
    """(size, state, cond) -> {task: (logp_action, logp_args)} from every C04 cell that carries the split."""
    out: dict = {}
    for r in c04["d1"]:
        if r.get("ok") and r.get("n_tok_action") is not None and r.get("rep", 1) == 1:
            out.setdefault((r["size"], r["state"], r["cond"]), {})[r["task"]] = (r["logp_action"], r["logp_args"])
    return out


def action_args(c04: dict) -> dict:
    S = split_rows(c04)
    sizes = [s for s in a3.SIZE_ORDER if any(k[0] == s for k in S)]
    out: dict = {}
    for size in sizes:
        for state, conds in SPLIT_CONDS.items():
            base = S.get((size, state, "L0"), {})
            if base:
                out[f"{size}/{state}/L0-level"] = {"action": a3.summ({t: v[0] for t, v in base.items()}),
                                                   "args": a3.summ({t: v[1] for t, v in base.items()})}
            for c in conds:
                cur = S.get((size, state, c), {})
                ts = sorted(set(cur) & set(base))
                if ts:
                    out[f"{size}/{state}/{c}-L0"] = {"d_action": a3.summ({t: cur[t][0] - base[t][0] for t in ts}),
                                                     "d_args": a3.summ({t: cur[t][1] - base[t][1] for t in ts})}
    return out


def reproducibility(c03: dict, c04: dict) -> dict:
    ref = {(r["size"], r["state"], r["cond"], r["task"]): r["logp"] for r in c03["d1"] if r.get("ok") and r.get("rep", 1) == 1}
    by: dict = {}
    for r in c04["d1"]:
        if r.get("ok") and r.get("purpose") == "rescore":
            k = (r["size"], r["state"], r["cond"], r["task"])
            if k in ref:
                by.setdefault(r["size"], []).append(r["logp"] - ref[k])
    return {s: {"n": len(v), "median_diff": a3._r(np.median(v)), "median_abs_diff": a3._r(np.median(np.abs(v))),
                "max_abs_diff": a3._r(np.max(np.abs(v)))} for s, v in by.items()}


def null_controls(c04: dict) -> dict:
    nc = c04.get("null_controls") or {}
    r = [v["len_ratio"] for v in nc.values() if v.get("len_ratio") is not None]
    return {"tasks": len(nc), "within_15pct": sum(bool(v.get("within_tol")) for v in nc.values()),
            "len_ratio_median": a3._r(np.median(r)) if r else None, "len_ratio_min": a3._r(min(r)) if r else None,
            "len_ratio_max": a3._r(max(r)) if r else None}


def tables_md(A: dict) -> str:
    L = ["# C04 probe follow-up — exploratory tables (data only)", "",
         "Source: `C03_probe.json` + `C04_probe_followup.json`, `pilot_c/analyze_c04.py`. Single runs. Δ in nats, median over "
         "tasks [95% bootstrap CI]. Exploratory (docs/PLAN.md §11 items 11–14). The pre-registered tables with C04's design "
         "cells merged in are in `C03C04_tables.md`.", "",
         f"G-null donors: {A['null_controls']}", "", "## E1. Graph control (depth 1)", "",
         "| Size / state | " + " | ".join(n.replace("-", " − ", 1) for n, _, _ in GRAPH_ROWS) + " |", "|---|" + "---|" * len(GRAPH_ROWS)]
    for k, v in A["graph_control"].items():
        if k != "depth2_find":
            L.append(f"| {k} | " + " | ".join(a3._ci(v[n]) for n, _, _ in GRAPH_ROWS) + " |")
    L += ["", "## E2. Depth 2 at S-find (1 sample per task): share of tasks", "", "| Size / condition | n | hit_file | hit_func | followed_wrong (X-graph: wrong focus; G-null: donor's file) | McNemar hit_file vs L0 |",
          "|---|---|---|---|---|---|"]
    for k, v in A["graph_control"]["depth2_find"].items():
        L.append(f"| {k} | {v['n']} | {a3._pct(v['hit_file'])} | {a3._pct(v['hit_func'])} | {a3._pct(v['followed_wrong'])} | "
                 + (a3._p(v["hit_file_vs_L0"]["p"]) if "hit_file_vs_L0" in v else "—") + " |")
    L += ["", "## E3. Action vs arguments: Δ vs L0 split into the call header (`<|tool_call>call:<tool>`) and the arguments", "",
          "| Size / state / condition | Δ action [CI] | Δ arguments [CI] | n |", "|---|---|---|---|"]
    for k, v in A["action_args"].items():
        if k.endswith("L0-level"):
            L.append(f"| {k} (level, not Δ) | {a3._ci(v['action'])} | {a3._ci(v['args'])} | {v['action'].get('n')} |")
        else:
            L.append(f"| {k} | {a3._ci(v['d_action'])} | {a3._ci(v['d_args'])} | {v['d_action'].get('n')} |")
    L += ["", "## E4. Re-score agreement with C03 (same cells, new session): logp(C04) − logp(C03)", "",
          "| Size | n | median diff | median |diff| | max |diff| |", "|---|---|---|---|---|"]
    for s, v in A["reproducibility"].items():
        L.append(f"| {s} | {v['n']} | {v['median_diff']} | {v['median_abs_diff']} | {v['max_abs_diff']} |")
    return "\n".join(L) + "\n"


def figures(A: dict, out_dir: Path) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # noqa: BLE001
        return [f"skipped: {type(e).__name__}"]
    made = []
    G = A["graph_control"]
    sizes = [s for s in a3.SIZE_ORDER if any(k.startswith(s + "/") for k in G)]
    labels = {"G-json-L0": "graph, right focus (G-json − L0)", "G-null-L0": "graph, unrelated file (G-null − L0)",
              "G-json-G-null": "location via graph (G-json − G-null)", "X-graph-G-null": "graph, wrong focus same file (X-graph − G-null)",
              "X-file-L0": "text, wrong file (X-file − L0)", "L1-L0": "text, right file (L1 − L0)"}
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True, facecolor=a3.SURF)
    for ax, state in zip(axes, ("find", "use")):
        def g(s, lab, state=state):
            key = next(k for k, v in labels.items() if v == lab)
            v = G.get(f"{s}/{state}", {}).get(key)
            return (v["median"], *v["ci"]) if v and v.get("n") else None
        a3._dotrows(ax, list(labels.values()), sizes, g, "Δ log p(target), nats (median, 95% CI)")
        ax.set_title(f"S-{state}", color=a3.INK, fontsize=10, loc="left")
    fig.suptitle("Graph control: same context ending (a tool response), unrelated file", color=a3.INK, fontsize=10, x=0.01, y=0.985, ha="left")
    a3._legend(fig, sizes)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    p = out_dir / "C04_fig4_graph_control.png"
    fig.savefig(p, dpi=200, facecolor=a3.SURF)
    plt.close(fig)
    made.append(p.name)

    AA = A["action_args"]
    sz = [s for s in a3.SIZE_ORDER if any(k.startswith(s + "/") for k in AA)]
    if sz:
        rows = [f"{st}/{c}" for st, cs in SPLIT_CONDS.items() for c in cs]
        fig, axes = plt.subplots(1, len(sz), figsize=(3.6 * len(sz) + 1.5, 4.2), sharey=True, facecolor=a3.SURF, squeeze=False)
        for ax, s in zip(axes[0], sz):
            for yi, r in enumerate(rows):
                v = AA.get(f"{s}/{r}-L0")
                if not v:
                    continue
                for comp, color, dy, mk in (("d_action", "#2a78d6", -0.15, "o"), ("d_args", "#eb6834", 0.15, "D")):
                    m = v[comp]
                    if m.get("n"):
                        ax.plot(m["ci"], [yi + dy] * 2, color=color, linewidth=1.2)
                        ax.plot([m["median"]], [yi + dy], marker=mk, color=color, markersize=4.5, markeredgecolor=a3.SURF, linestyle="none")
            ax.set_yticks(range(len(rows)))
            ax.set_yticklabels([r.replace("find/", "S-find ").replace("use/", "S-use ") for r in rows])
            if not ax.yaxis_inverted():
                ax.invert_yaxis()
            ax.axvline(0, color=a3.INK2, linewidth=0.8)
            ax.set_title(s, color=a3.INK, fontsize=10, loc="left")
            ax.set_xlabel("Δ vs L0, nats (median, 95% CI)", color=a3.INK2, fontsize=8)
            a3._style(ax)
        import matplotlib.lines as ml
        fig.legend(handles=[ml.Line2D([], [], color="#2a78d6", marker="o", label="action (call this tool now)"),
                            ml.Line2D([], [], color="#eb6834", marker="D", label="arguments")],
                   loc="upper right", ncol=2, frameon=False, fontsize=8)
        fig.suptitle("Where the gain sits: the call header vs the arguments", color=a3.INK, fontsize=10, x=0.01, y=0.985, ha="left")
        fig.tight_layout(rect=(0, 0, 1, 0.92))
        p = out_dir / "C04_fig5_action_args.png"
        fig.savefig(p, dpi=200, facecolor=a3.SURF)
        plt.close(fig)
        made.append(p.name)
    return made


def main(c03_path: str, c04_path: str, out_dir: str = ".") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    c03, c04 = json.loads(Path(c03_path).read_text()), json.loads(Path(c04_path).read_text())
    merged = merge_design(c03, c04)
    a3.analyze_all(merged, "C03_probe.json + C04 design cells", out, out, "C03C04")
    D = a3.Data(with_controls(merged, c04))
    A = {"sources": [c03_path, c04_path], "c04_sizes": [{k: e.get(k) for k in ("size", "planned", "error", "skipped", "d1_minutes", "d2_minutes")}
                                                         for e in c04.get("sizes", [])],
         "null_controls": null_controls(c04), "graph_control": graph_control(D), "action_args": action_args(c04),
         "reproducibility": reproducibility(c03, c04)}
    A["figures"] = figures(A, out)
    (out / "C04_analysis.json").write_text(json.dumps(A, indent=1, default=str))
    md = tables_md(A)
    (out / "C04_tables.md").write_text(md)
    print(md[:4000])
    return A


if __name__ == "__main__":
    main(*sys.argv[1:])
