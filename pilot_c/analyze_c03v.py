"""Final analysis of the CPU test verification (notebooks/C03v_test_verify__CPU.ipynb) of the probe's sampled S-use edits.
Standalone (numpy + math; matplotlib optional): runs as C03v's last cell on Kaggle and offline; tested on synthetic data.

Inputs : C03v_test_verify.json (rows: task, size, cond, sample, solves, source), C03_probe.json and, if present,
         C04_probe_followup.json (their depth-2 S-use rows give every sample, edited or not, and its `exact` flag).
Outputs: C03v_analysis.json, C03v_tables.md, C03v_fig_solves.png (numbers only).
  V1 per size x condition: samples, share that pass the required tests (`solves`; a sample without an applied edit of the
     gold file cannot pass), tasks with >= 1 passing sample, agreement of `exact` and `solves`
  V2 information threshold per task and size (docs/PLAN.md §5): lowest of L0, L2, L3, L4, L5 where >= 1 of 2 samples is
     `exact` or `solves`; otherwise ">L5"
  V3 H5 with `solves` in place of `on_target` (exploratory): tasks with >= 1 passing sample at L2 and at L5
Usage: python -m pilot_c.analyze_c03v <C03v_test_verify.json> <C03_probe.json> [<C04_probe_followup.json>] <out_dir>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

LADDER = ("L0", "L2", "L3", "L4", "L5")
SIZES = ("e2b", "e4b", "12b", "31b")


def samples(probe_files: list[str]) -> dict[tuple[str, str, str, int], dict]:
    out = {}
    for f in probe_files:
        if f and Path(f).exists():
            for r in json.loads(Path(f).read_text())["d2"]:
                if r.get("ok") and r.get("state") == "use":
                    out[(r["size"], r["cond"], r["task"], r["sample"])] = r
    return out


def ratio_ci(num: list[int], den: list[int], n: int = 10_000, seed: int = 0) -> list[float] | None:
    a, b = np.asarray(num, float), np.asarray(den, float)
    if not len(a) or b.sum() == 0:
        return None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), (n, len(a)))
    d = b[idx].sum(1)
    v = a[idx].sum(1)[d > 0] / d[d > 0]
    return [round(float(np.quantile(v, 0.025)), 4), round(float(np.quantile(v, 0.975)), 4)]


def analyze(verify: dict, probe_files: list[str]) -> dict:
    S = samples(probe_files)
    solved = {(r["size"], r["cond"], r["task"], r["sample"]): bool(r["solves"]) for r in verify["rows"]}
    A: dict = {"samples_known": len(S), "verified_rows": len(verify["rows"]),
               "verified_without_sample_row": sum(1 for k in solved if k not in S), "V1": {}, "V2": {}, "V3": {}}
    sizes = [s for s in SIZES if any(k[0] == s for k in S)]
    for size in sizes:
        for cond in sorted({k[1] for k in S if k[0] == size}):
            keys = [k for k in S if k[0] == size and k[1] == cond]
            tasks = sorted({k[2] for k in keys})
            per_t = {t: [k for k in keys if k[2] == t] for t in tasks}
            sol = {t: sum(solved.get(k, False) for k in per_t[t]) for t in tasks}
            ex = {t: sum(bool(S[k].get("exact")) for k in per_t[t]) for t in tasks}
            A["V1"][f"{size}/{cond}"] = {
                "samples": len(keys), "solves": sum(sol.values()), "solves_rate": round(sum(sol.values()) / len(keys), 4),
                "solves_rate_ci": ratio_ci([sol[t] for t in tasks], [len(per_t[t]) for t in tasks]),
                "tasks": len(tasks), "tasks_any_solves": sum(1 for t in tasks if sol[t]),
                "exact": sum(ex.values()),
                "exact_not_solves": sum(1 for k in keys if S[k].get("exact") and not solved.get(k, False)),
                "solves_not_exact": sum(1 for k in keys if solved.get(k, False) and not S[k].get("exact"))}
        thr: dict[str, int] = {}
        tasks = sorted({k[2] for k in S if k[0] == size})
        for t in tasks:
            lvl = None
            for c in LADDER:
                ks = [k for k in S if k[0] == size and k[1] == c and k[2] == t]
                if any(S[k].get("exact") or solved.get(k, False) for k in ks):
                    lvl = c
                    break
            missing = any(not [k for k in S if k[0] == size and k[1] == c and k[2] == t] for c in LADDER)
            key = lvl or ("none (a ladder cell missing)" if missing else ">L5")
            thr[key] = thr.get(key, 0) + 1
        A["V2"][size] = thr
        any_sol = lambda c: {t for t in tasks if any(solved.get(k, False) for k in S if k[0] == size and k[1] == c and k[2] == t)}  # noqa: E731
        A["V3"][size] = {"tasks": len(tasks), "L2_any_solves": len(any_sol("L2")), "L5_any_solves": len(any_sol("L5")),
                         "label": "exploratory (H5 with solves instead of on_target)" if size != "e4b" else "exploratory variant of H5 (e4b)"}
    return A


def tables_md(A: dict) -> str:
    L = ["# C03v — test verification of the probe's sampled edits (data only)", "",
         f"Samples known from the probe files: {A['samples_known']}; verified edits: {A['verified_rows']} "
         f"(without a matching sample row: {A['verified_without_sample_row']}).", "",
         "## V1. Share of S-use samples whose edit passes the required tests", "",
         "| Size / condition | samples | pass rate [95% CI] | tasks with ≥ 1 pass | exact | exact but fails | passes but not exact |",
         "|---|---|---|---|---|---|---|"]
    for k, v in A["V1"].items():
        ci = v["solves_rate_ci"]
        L.append(f"| {k} | {v['samples']} | {v['solves_rate']:.0%} " + (f"[{ci[0]:.0%}, {ci[1]:.0%}]" if ci else "") +
                 f" | {v['tasks_any_solves']}/{v['tasks']} | {v['exact']} | {v['exact_not_solves']} | {v['solves_not_exact']} |")
    keys = list(LADDER) + [">L5", "none (a ladder cell missing)"]
    L += ["", "## V2. Information threshold (lowest rung with ≥ 1 of 2 samples exact or passing)", "",
          "| Size | " + " | ".join(keys) + " |", "|---|" + "---|" * len(keys)]
    for s, thr in A["V2"].items():
        L.append(f"| {s} | " + " | ".join(str(thr.get(k, 0)) for k in keys) + " |")
    L += ["", "## V3. Tasks with ≥ 1 passing sample at L2 and at L5 (exploratory)", "", "| Size | tasks | L2 | L5 |", "|---|---|---|---|"]
    for s, v in A["V3"].items():
        L.append(f"| {s} | {v['tasks']} | {v['L2_any_solves']} | {v['L5_any_solves']} |")
    return "\n".join(L) + "\n"


def figure(A: dict, out: Path) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # noqa: BLE001
        return [f"skipped: {type(e).__name__}"]
    colors = {"e4b": "#2a78d6", "12b": "#eb6834", "31b": "#1baf7a", "e2b": "#eda100"}
    markers = {"e4b": "o", "12b": "s", "31b": "D", "e2b": "^"}
    sizes = [s for s in SIZES if any(k.startswith(s + "/") for k in A["V1"])]
    conds = [c for c in ("L0", "L2", "L3", "L4", "L5", "T", "W", "G-json", "X-func", "X-test") if any(f"{s}/{c}" in A["V1"] for s in sizes)]
    fig, ax = plt.subplots(figsize=(7, 4.2), facecolor="#fcfcfb")
    for i, s in enumerate(sizes):
        dy = (i - (len(sizes) - 1) / 2) * 0.22
        for yi, c in enumerate(conds):
            v = A["V1"].get(f"{s}/{c}")
            if not v:
                continue
            if v["solves_rate_ci"]:
                ax.plot(v["solves_rate_ci"], [yi + dy] * 2, color=colors[s], linewidth=1.2)
            ax.plot([v["solves_rate"]], [yi + dy], marker=markers[s], color=colors[s], markersize=4.5, markeredgecolor="#fcfcfb",
                    linestyle="none", label=s if yi == 0 else None)
    ax.set_yticks(range(len(conds)))
    ax.set_yticklabels(conds)
    ax.invert_yaxis()
    ax.set_xlim(-0.02, 1.02)
    ax.set_xlabel("share of S-use samples whose edit passes the required tests (95% CI)", color="#52514e", fontsize=8)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.grid(axis="x", color="#e6e5e0", linewidth=0.6)
    ax.tick_params(colors="#52514e", labelsize=8, length=0)
    fig.legend(loc="upper right", ncol=len(sizes), frameon=False, fontsize=8)
    fig.suptitle("Depth 2, S-use: edits that pass the tests", color="#0b0b0b", fontsize=10, x=0.01, y=0.985, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    p = out / "C03v_fig_solves.png"
    fig.savefig(p, dpi=200, facecolor="#fcfcfb")
    plt.close(fig)
    return [p.name]


def main(verify_path: str, c03_path: str, *rest: str) -> dict:
    *probe_more, out_dir = rest if rest else (".",)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    A = analyze(json.loads(Path(verify_path).read_text()), [c03_path, *probe_more])
    A["figures"] = figure(A, out)
    (out / "C03v_analysis.json").write_text(json.dumps(A, indent=1))
    md = tables_md(A)
    (out / "C03v_tables.md").write_text(md)
    print(md)
    return A


if __name__ == "__main__":
    main(*sys.argv[1:])
