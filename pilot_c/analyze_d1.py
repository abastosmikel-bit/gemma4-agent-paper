"""Frozen analysis of notebooks/D1_heldout_probe__L4x4.ipynb, as pre-registered in docs/PLAN_D1_heldout_probe.md §5.
Standalone: it runs as D1's last cell on Kaggle and offline, and is tested on synthetic data (tests/test_analyze_d1.py).
Needs numpy, scipy (common/stats.py) and, for figures, matplotlib (all preinstalled on Kaggle).

The same functions run on the dev probe (C03 + C04, merged as in pilot_c/analyze_c04.py) to give the dev column of every
table: results/D1_dev_reference.json, built offline by `python -m pilot_c.analyze_d1 --dev-reference`.

Inputs : D1_heldout_probe.json (the notebook's output; rows d1 / d2 in C03's format), D1_dev_reference.json.
Outputs: D1_analysis.json, D1_tables.md, D1_fig1_criteria.png, D1_fig2_depth2.png (numbers only; no task text).
Usage  : python -m pilot_c.analyze_d1 <D1_heldout_probe.json> <D1_dev_reference.json> <out_dir>
         python -m pilot_c.analyze_d1 --dev-reference <C03_probe.json> <C04_probe_followup.json> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from common import stats as cs
from pilot_c import analyze_c03 as a3

SIZES = ("e4b", "12b", "31b")
FIND = ("L0", "L1", "L2", "W", "G-json", "G-null", "X-func", "X-graph")     # depth 1, S-find (PLAN_D1 §2)
USE = ("L0", "L2", "W", "T", "L5", "G-json", "G-null")                      # depth 1, S-use
D2_FIND = ("L0", "L2", "G-json", "X-graph", "G-null")                       # depth 2, 1 sample each
D2_USE = ("L0", "L2", "L5")                                                 # depth 2, 2 samples each
ALPHA = 0.05
GAP_NATS = 2.0          # R4 tolerance
MIN_TASKS = 12          # a size is evaluable for a criterion only with >= 12 tasks having every cell it needs
# Depth-1 contrasts shown in the descriptive table (state, a, b)
CONTRASTS = [("find", c, "L0") for c in FIND[1:]] + [("find", "X-func", "L2"), ("find", "X-graph", "G-json"),
             ("find", "G-json", "G-null"), ("find", "L2", "X-func"), ("find", "G-json", "X-graph")] + \
            [("use", c, "L0") for c in USE[1:]] + [("use", "L5", "W"), ("use", "G-json", "G-null")]


def _r(x, k=3):
    return a3._r(x, k)


def _ok(s: dict) -> bool:
    return s.get("n", 0) >= MIN_TASKS


# --------------------------------------------------------------------------- criteria R1-R4 (PLAN_D1 §4)

def r1(D: a3.Data, size: str) -> dict:
    """Claim 1 / H1, the dev test unchanged: Holm within size over {find>0, find>use}, two-sided Wilcoxon."""
    df, du = D.delta(size, "find", "L2", "L0"), D.delta(size, "use", "L2", "L0")
    diff = {t: df[t] - du[t] for t in set(df) & set(du)}
    p = cs.holm({"find>0": cs.wilcoxon_p(list(df.values())), "find>use": cs.wilcoxon_p(list(diff.values()))})
    sf, su, sd = a3.summ(df), a3.summ(du), a3.summ(diff)
    ev = _ok(sd)
    part1 = ev and sf["median"] > 0 and p["find>0"] is not None and p["find>0"] < ALPHA
    part2 = ev and su["median"] < sf["median"] and sd["median"] > 0 and p["find>use"] is not None and p["find>use"] < ALPHA
    return {"d_find_L2-L0": sf, "d_use_L2-L0": su, "d_find-minus-d_use": sd, "p_holm": {k: _r(v, 6) for k, v in p.items()},
            "part1_location_helps_find": bool(part1) if ev else None, "holds": bool(part2) if ev else None}


def r2(D: a3.Data, size: str) -> dict:
    """Claim 1: words help the edit, the full diff helps more: median Δ_use(W−L0) > 0 and median Δ_use(L5−L0) >
    median Δ_use(W−L0), on the tasks with all three cells."""
    common = set(D.lp.get((size, "use", "L0"), {})) & set(D.lp.get((size, "use", "W"), {})) & set(D.lp.get((size, "use", "L5"), {}))
    sub = lambda d: {t: v for t, v in d.items() if t in common}  # noqa: E731
    w, l5, l5w = (a3.summ(sub(D.delta(size, "use", a, b))) for a, b in (("W", "L0"), ("L5", "L0"), ("L5", "W")))
    ev = len(common) >= MIN_TASKS
    holds = ev and w["median"] > 0 and l5["median"] > w["median"]
    return {"n_tasks": len(common), "d_use_W-L0": w, "d_use_L5-L0": l5, "d_use_L5-W": l5w, "holds": bool(holds) if ev else None}


def r3(D: a3.Data, size: str) -> dict:
    """Claim 3, find: graph content helps (median Δ_find(G-json−G-null) > 0) and which symbol the graph is about matters
    less than which location is named: |median Δ_find(G-json−X-graph)| < median Δ_find(L2−X-func)."""
    gn, gx, lx = (a3.summ(D.delta(size, "find", a, b)) for a, b in (("G-json", "G-null"), ("G-json", "X-graph"), ("L2", "X-func")))
    ev = _ok(gn) and _ok(gx) and _ok(lx)
    holds = ev and gn["median"] > 0 and abs(gx["median"]) < lx["median"]
    return {"d_find_G-json-G-null": gn, "d_find_G-json-X-graph": gx, "d_find_L2-X-func": lx, "holds": bool(holds) if ev else None}


def r4(D: a3.Data, size: str) -> dict:
    """Claim 3, use: graph content adds nothing at the edit: median Δ_use(G-null−L0) >= median Δ_use(G-json−L0) − 2."""
    a, b, c = (a3.summ(D.delta(size, "use", x, y)) for x, y in (("G-null", "L0"), ("G-json", "L0"), ("G-json", "G-null")))
    ev = _ok(a) and _ok(b)
    holds = ev and a["median"] >= b["median"] - GAP_NATS
    return {"d_use_G-null-L0": a, "d_use_G-json-L0": b, "d_use_G-json-G-null": c, "holds": bool(holds) if ev else None}


def verdict(per_size: dict) -> str:
    v = [per_size.get(s, {}).get("holds") for s in SIZES]
    if all(x is True for x in v):
        return "replicated"
    if any(x is False for x in v):
        return f"not replicated ({sum(x is True for x in v)} of 3 sizes hold)"
    return f"incomplete ({sum(x is True for x in v)} of 3 sizes hold, {sum(x is None for x in v)} not evaluable)"


# --------------------------------------------------------------------------- depth 2 (R5, descriptive)

def depth2(D: a3.Data) -> dict:
    out: dict = {"find": {}, "use": {}}
    for size in SIZES:
        base = {t: rs[0] for t, rs in D.d2.get((size, "find", "L0"), {}).items()}
        for c in D2_FIND:
            rows = {t: rs[0] for t, rs in D.d2.get((size, "find", c), {}).items()}
            if not rows:
                continue
            e = {"tasks": len(rows), **{m: _r(np.mean([bool(r.get(m)) for r in rows.values()])) for m in
                                        ("tool_call", "hit_file", "hit_func", "followed_wrong")}}
            if c != "L0":
                for m in ("hit_file", "hit_func"):
                    e[f"{m}_vs_L0"] = a3.mcnemar_tasks({t: int(bool(r.get(m))) for t, r in base.items()},
                                                       {t: int(bool(r.get(m))) for t, r in rows.items()})
            out["find"][f"{size}/{c}"] = e
        for c in D2_USE:
            per = D.d2.get((size, "use", c), {})
            rows = [r for rs in per.values() for r in rs]
            if not rows:
                continue
            mean = lambda k, rr=rows: _r(np.mean([bool(r.get(k)) for r in rr]))  # noqa: E731
            edits = [r for r in rows if r.get("edit_gold_file")]
            out["use"][f"{size}/{c}"] = {
                "tasks": len(per), "samples": len(rows), "tool_call": mean("tool_call"),
                "edit_now": mean("edit_gold_file"), "applies": mean("applies"), "on_target": mean("on_target"),
                "exact": mean("exact"), "exact_given_edit": _r(np.mean([bool(r.get("exact")) for r in edits])) if edits else None,
                "tasks_any_exact": _r(np.mean([any(r.get("exact") for r in rs) for rs in per.values()])),
                "first_tools": dict(sorted(__import__("collections").Counter(r.get("tool") or "none" for r in rows).items()))}
    return out


def depth1_table(D: a3.Data) -> dict:
    return {f"{s}/{st}/{a}-{b}": a3.summ(D.delta(s, st, a, b)) for s in SIZES for (st, a, b) in CONTRASTS}


def health(d: dict) -> dict:
    import collections
    out = {}
    for key in ("d1", "d2"):
        c = collections.Counter((r.get("size"), "ok" if r.get("ok") else (r.get("why") or "?").split(":")[0]) for r in d.get(key, []))
        out[key] = {f"{s}/{w}": n for (s, w), n in sorted(c.items(), key=str)}
    out["score_modes"] = dict(collections.Counter(r.get("mode") for r in d.get("d1", []) if r.get("ok")))
    return out


def analyze_rows(d: dict) -> dict:
    D = a3.Data(d)
    A = {"R1_claim1_find_vs_use": {s: r1(D, s) for s in SIZES}, "R2_claim1_words_and_diff": {s: r2(D, s) for s in SIZES},
         "R3_claim3_graph_find": {s: r3(D, s) for s in SIZES}, "R4_claim3_graph_use": {s: r4(D, s) for s in SIZES}}
    A["verdicts"] = {k.split("_")[0]: verdict(v) for k, v in A.items()}
    A["R5_depth2"] = depth2(D)
    A["depth1"] = depth1_table(D)
    A["sizes_with_depth1"] = D.sizes
    A["sizes_with_depth2"] = D.d2_sizes
    A["health"] = health(d)
    return A


# --------------------------------------------------------------------------- tables and figures

def _ci(s: dict | None) -> str:
    if not s or not s.get("n"):
        return "—"
    return f"{s['median']:+.1f} [{s['ci'][0]:+.1f}, {s['ci'][1]:+.1f}] (n={s['n']})"


def _p(p):
    return "—" if p is None else ("<0.001" if p < 0.001 else f"{p:.3f}")


def _yn(x):
    return {True: "holds", False: "fails", None: "not evaluable"}[x]


def _pct(x):
    return "—" if x is None else f"{100 * x:.0f}%"


def tables_md(A: dict, dev: dict | None, meta: dict) -> str:
    dev = dev or {}
    g = lambda k, s, f: (dev.get(k, {}).get(s) or {}).get(f)  # noqa: E731
    T = ["# D1 held-out probe: frozen criteria (docs/PLAN_D1_heldout_probe.md)", "",
         f"Tasks: {meta.get('n_tasks')} held-out ({meta.get('by_repo')}); sizes with depth 1: {A['sizes_with_depth1']}; "
         f"with depth 2: {A['sizes_with_depth2']}. Medians in nats with 95% bootstrap CI over tasks. Dev = C03 + C04 "
         "(30 dev tasks), same code.", "",
         "## Verdicts", "", "| criterion | held-out verdict | dev |", "|---|---|---|"]
    for k, v in A["verdicts"].items():
        T.append(f"| {k} | {v} | {dev.get('verdicts', {}).get(k, '—')} |")
    T += ["", "## R1 — claim 1 / H1: location helps find more than use (Holm within size, Wilcoxon)", "",
          "| size | Δ_find(L2−L0) | Δ_use(L2−L0) | Δ_find − Δ_use | Holm p (find>use) | held-out | dev Δ_find − Δ_use |", "|---|---|---|---|---|---|---|"]
    for s in SIZES:
        h = A["R1_claim1_find_vs_use"][s]
        T.append(f"| {s} | {_ci(h['d_find_L2-L0'])} | {_ci(h['d_use_L2-L0'])} | {_ci(h['d_find-minus-d_use'])} | "
                 f"{_p(h['p_holm']['find>use'])} | {_yn(h['holds'])} | {_ci(g('R1_claim1_find_vs_use', s, 'd_find-minus-d_use'))} |")
    T += ["", "## R2 — claim 1: words help the edit, the diff helps more (tasks with L0, W and L5)", "",
          "| size | Δ_use(W−L0) | Δ_use(L5−L0) | Δ_use(L5−W) | held-out | dev W−L0 / L5−L0 |", "|---|---|---|---|---|---|"]
    for s in SIZES:
        h = A["R2_claim1_words_and_diff"][s]
        T.append(f"| {s} | {_ci(h['d_use_W-L0'])} | {_ci(h['d_use_L5-L0'])} | {_ci(h['d_use_L5-W'])} | {_yn(h['holds'])} | "
                 f"{_ci(g('R2_claim1_words_and_diff', s, 'd_use_W-L0'))} / {_ci(g('R2_claim1_words_and_diff', s, 'd_use_L5-L0'))} |")
    T += ["", "## R3 — claim 3 at find: graph content helps; the symbol matters less than the named location", "",
          "| size | Δ_find(G-json−G-null) | Δ_find(G-json−X-graph) | Δ_find(L2−X-func) | held-out | dev G-json−G-null |", "|---|---|---|---|---|---|"]
    for s in SIZES:
        h = A["R3_claim3_graph_find"][s]
        T.append(f"| {s} | {_ci(h['d_find_G-json-G-null'])} | {_ci(h['d_find_G-json-X-graph'])} | {_ci(h['d_find_L2-X-func'])} | "
                 f"{_yn(h['holds'])} | {_ci(g('R3_claim3_graph_find', s, 'd_find_G-json-G-null'))} |")
    T += ["", f"## R4 — claim 3 at use: graph content adds nothing (G-null within {GAP_NATS:.0f} nats of G-json)", "",
          "| size | Δ_use(G-null−L0) | Δ_use(G-json−L0) | Δ_use(G-json−G-null) | held-out | dev G-json−G-null |", "|---|---|---|---|---|---|"]
    for s in SIZES:
        h = A["R4_claim3_graph_use"][s]
        T.append(f"| {s} | {_ci(h['d_use_G-null-L0'])} | {_ci(h['d_use_G-json-L0'])} | {_ci(h['d_use_G-json-G-null'])} | "
                 f"{_yn(h['holds'])} | {_ci(g('R4_claim3_graph_use', s, 'd_use_G-json-G-null'))} |")
    T += ["", "## R5 — depth 2 (sampled first action), descriptive", "",
          "S-find, share of tasks (1 sample each); McNemar vs L0 on the same tasks.", "",
          "| size | cond | reads gold file | reads gold function | follows wrong | dev gold file / function |", "|---|---|---|---|---|---|"]
    df, du = dev.get("R5_depth2", {}).get("find", {}), dev.get("R5_depth2", {}).get("use", {})
    for k, e in A["R5_depth2"]["find"].items():
        mc = e.get("hit_file_vs_L0", {})
        T.append(f"| {k.split('/')[0]} | {k.split('/')[1]} | {_pct(e['hit_file'])}" + (f" (p {_p(mc.get('p'))})" if mc else "")
                 + f" | {_pct(e['hit_func'])} | {_pct(e['followed_wrong'])} | {_pct((df.get(k) or {}).get('hit_file'))} / {_pct((df.get(k) or {}).get('hit_func'))} |")
    T += ["", "S-use, share of samples (2 per task).", "",
          "| size | cond | edits gold file now | applies | on target | exact | exact given edit | tasks with an exact edit | dev edit now / exact |",
          "|---|---|---|---|---|---|---|---|---|"]
    for k, e in A["R5_depth2"]["use"].items():
        T.append(f"| {k.split('/')[0]} | {k.split('/')[1]} | {_pct(e['edit_now'])} | {_pct(e['applies'])} | {_pct(e['on_target'])} | "
                 f"{_pct(e['exact'])} | {_pct(e['exact_given_edit'])} | {_pct(e['tasks_any_exact'])} | "
                 f"{_pct((du.get(k) or {}).get('edit_now'))} / {_pct((du.get(k) or {}).get('exact'))} |")
    T += ["", "## Depth 1, every contrast (descriptive)", "", "| contrast | " + " | ".join(SIZES) + " | dev " + " | dev ".join(SIZES) + " |",
          "|---|" + "---|" * (2 * len(SIZES))]
    for (st, a, b) in CONTRASTS:
        k = f"{st}/{a}-{b}"
        T.append(f"| {st} {a}−{b} | " + " | ".join(_ci(A["depth1"].get(f"{s}/{k}")) for s in SIZES) + " | "
                 + " | ".join(_ci(dev.get("depth1", {}).get(f"{s}/{k}")) for s in SIZES) + " |")
    T += ["", f"Cell health: {json.dumps(A['health'])}", ""]
    return "\n".join(T)


def figures(A: dict, dev: dict | None, out: Path) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return []
    dev = dev or {}
    rows = [("R1", "R1_claim1_find_vs_use", "d_find-minus-d_use", "Δ_find(L2−L0) − Δ_use(L2−L0)"),
            ("R2", "R2_claim1_words_and_diff", "d_use_W-L0", "Δ_use(W−L0)"),
            ("R2", "R2_claim1_words_and_diff", "d_use_L5-L0", "Δ_use(L5−L0)"),
            ("R3", "R3_claim3_graph_find", "d_find_G-json-G-null", "Δ_find(G-json−G-null)"),
            ("R3", "R3_claim3_graph_find", "d_find_L2-X-func", "Δ_find(L2−X-func)"),
            ("R4", "R4_claim3_graph_use", "d_use_G-json-G-null", "Δ_use(G-json−G-null)")]
    colors = {"e4b": "#4C78A8", "12b": "#F58518", "31b": "#54A24B"}
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    for i, (_, key, field, label) in enumerate(rows):
        for j, s in enumerate(SIZES):
            for src, mk, off in ((A, "o", -0.12), (dev, "s", 0.12)):
                e = ((src.get(key) or {}).get(s) or {}).get(field) or {}
                if not e.get("n"):
                    continue
                y = i + (j - 1) * 0.25 + off / 2
                ax.errorbar(e["median"], y, xerr=[[e["median"] - e["ci"][0]], [e["ci"][1] - e["median"]]], fmt=mk,
                            color=colors[s], mfc=colors[s] if src is A else "white", ms=5, capsize=2, lw=1)
    ax.axvline(0, color="#888", lw=0.8)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{r[0]}  {r[3]}" for r in rows])
    ax.invert_yaxis()
    ax.set_xlabel("median Δ log p (nats), 95% bootstrap CI")
    ax.set_title("D1 held-out (filled) vs dev (open), per size")
    for s, c in colors.items():
        ax.plot([], [], "o", color=c, label=s)
    ax.legend(frameon=False, loc="lower right")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(out / "D1_fig1_criteria.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    for ax, (state, metric, conds, title) in zip(axes, (("find", "hit_file", D2_FIND, "S-find: reads the gold file"),
                                                         ("use", "exact", D2_USE, "S-use: exact edit (share of samples)"))):
        w = 0.13
        for j, s in enumerate(SIZES):
            for k, (src, hatch) in enumerate(((A, None), (dev, "//"))):
                vals = [((src.get("R5_depth2") or {}).get(state, {}).get(f"{s}/{c}") or {}).get(metric) for c in conds]
                xs = np.arange(len(conds)) + (2 * j + k - 2.5) * w
                ax.bar(xs, [v if v is not None else 0 for v in vals], w, color=colors[s], alpha=1.0 if k == 0 else 0.45,
                       hatch=hatch, edgecolor="white", label=f"{s} {'held-out' if k == 0 else 'dev'}")
        ax.set_xticks(range(len(conds)))
        ax.set_xticklabels(conds)
        ax.set_ylim(0, 1)
        ax.set_title(title, fontsize=10)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[1].legend(frameon=False, fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(out / "D1_fig2_depth2.png", dpi=150)
    plt.close(fig)
    return ["D1_fig1_criteria.png", "D1_fig2_depth2.png"]


def main(d1_path: str, dev_path: str | None, out_dir: str = ".") -> dict:
    d = json.loads(Path(d1_path).read_text())
    dev = json.loads(Path(dev_path).read_text()) if dev_path and Path(dev_path).exists() else None
    A = analyze_rows(d)
    sel = d.get("selection") or {}
    meta = {"n_tasks": len(d.get("task_ids", [])), "by_repo": sel.get("selected_by_repo")}
    A.update({"plan": "docs/PLAN_D1_heldout_probe.md", "notebook": d.get("notebook"), "plan_commit": d.get("plan_commit"),
              "task_ids": d.get("task_ids"), "selection": sel, "session_elapsed_h": d.get("session_elapsed_h"),
              "stopped": d.get("stopped"), "depth2_run": d.get("depth2"), "dev_reference": bool(dev)})
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    A["figures"] = figures(A, dev, out)
    (out / "D1_analysis.json").write_text(json.dumps(A, indent=1))
    (out / "D1_tables.md").write_text(tables_md(A, dev, meta))
    print("D1 verdicts:", json.dumps(A["verdicts"], indent=1))
    return A


def dev_reference(c03_path: str, c04_path: str, out_path: str) -> dict:
    from pilot_c import analyze_c04 as a4
    c03, c04 = json.loads(Path(c03_path).read_text()), json.loads(Path(c04_path).read_text())
    d = a4.with_controls(a4.merge_design(c03, c04), c04)
    A = analyze_rows(d)
    A.pop("health", None)
    A.update({"source": "dev: results/C03_probe.json + results/C04_probe_followup.json (merged as analyze_c04)",
              "n_tasks": len(c03["task_ids"])})
    Path(out_path).write_text(json.dumps(A, indent=1))
    print("dev verdicts:", json.dumps(A["verdicts"], indent=1))
    return A


if __name__ == "__main__":
    if sys.argv[1] == "--dev-reference":
        dev_reference(*sys.argv[2:5])
    else:
        main(*sys.argv[1:4])
