"""Paper figures and the number sheet, rebuilt from committed result JSONs only.

Dev results are read from pilot/c-bottleneck at a pinned commit (no copies of result files on this branch).
Held-out results (D1, D1v, D2) are overlaid as hollow markers / an extra bar when their analysis files exist in
--heldout (default: results/ on this branch). Nothing here contains task text or competition data.

Usage (from the repo root):
    python paper/make_figures.py                      # dev from git, held-out from results/ if present
    python paper/make_figures.py --dev-dir DIR        # dev from a checkout's results/ instead of git

Outputs: paper/figures/fig1_where_vs_what.png, fig2_hesitation.png, fig3_runs_ended.png, paper/numbers.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

DEV_REF = "14e9d004461d3a2f2342911890e02279e74c1333"  # origin/pilot/c-bottleneck HEAD on 2026-11-04
SIZES = ["e4b", "12b", "31b"]
# Reference palette, first three categorical slots (validated all-pairs, light mode); marker shape is the
# secondary encoding required because aqua is below 3:1 contrast on the surface.
COLOR = {"e4b": "#2a78d6", "12b": "#eb6834", "31b": "#1baf7a"}
MARKER = {"e4b": "o", "12b": "s", "31b": "D"}
LABEL = {"e4b": "Gemma 4 E4B", "12b": "Gemma 4 12B", "31b": "Gemma 4 31B"}
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": INK2, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK,
    "text.color": INK, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
})


def load(name: str, dev_dir: Path | None) -> dict:
    if dev_dir is not None:
        return json.loads((dev_dir / name).read_text())
    blob = subprocess.run(["git", "show", f"{DEV_REF}:results/{name}"], check=True, capture_output=True, text=True)
    return json.loads(blob.stdout)


def load_opt(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


# ---------------------------------------------------------------- Figure 1: where vs what, find vs use (claims 1, 3)
ROWS = [
    ("Location: file + function", "L2-L0"),
    ("The change, in words", "W-L0"),
    ("The exact fix (diff)", "L5-L0"),
    ("Graph content:\nright file − unrelated file", "G-json-G-null"),
]


def cell(ref: dict, size: str, state: str, key: str) -> dict | None:
    if key == "G-json-G-null":
        block = ref["R3_claim3_graph_find" if state == "find" else "R4_claim3_graph_use"].get(size, {})
        return block.get(f"d_{state}_G-json-G-null")
    return ref["depth1"].get(f"{size}/{state}/{key}")


def fig1(dev: dict, held: dict | None, out: Path) -> list[tuple]:
    rows = []
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4), sharey=True)
    for ax, state, title in zip(axes, ["find", "use"], ["Before reading the code (find)", "After reading the code (use)"]):
        ax.axvline(0, color=INK2, lw=1)
        ax.grid(axis="x", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for i, (label, key) in enumerate(ROWS):
            y0 = len(ROWS) - 1 - i
            if state == "find" and key == "L5-L0":
                ax.text(0.8, y0, "not probed (the diff names the file)", va="center", fontsize=8.5, color=INK2)
                continue
            for j, size in enumerate(SIZES):
                y = y0 + (1 - j) * 0.22
                for src, ref, filled in (("dev", dev, True), ("held-out", held, False)):
                    if ref is None:
                        continue
                    c = cell(ref, size, state, key)
                    if not c:
                        continue
                    yy = y if filled else y - 0.09
                    lo, hi = c["ci"]
                    ax.plot([lo, hi], [yy, yy], color=COLOR[size], lw=2, solid_capstyle="round")
                    ax.plot(c["median"], yy, MARKER[size], ms=7, mec=COLOR[size], mew=1.6,
                            mfc=COLOR[size] if filled else SURFACE)
                    rows.append((src, size, state, key, c["n"], c["median"], lo, hi))
        ax.set_title(title, loc="left", fontsize=11)
        ax.set_xlabel("gain in log-likelihood of the right next action vs no hint (nats)")
        ax.set_xlim(-10, 58)
    axes[0].set_yticks(range(len(ROWS)))
    axes[0].set_yticklabels([r[0] for r in ROWS][::-1])
    handles = [plt.Line2D([], [], marker=MARKER[s], color=COLOR[s], lw=2, ms=7, label=LABEL[s]) for s in SIZES]
    if held is not None:
        handles.append(plt.Line2D([], [], marker="o", color=INK2, mfc=SURFACE, lw=0, label="held-out (hollow)"))
    fig.legend(handles=handles, loc="upper center", ncol=len(handles), frameon=False, bbox_to_anchor=(0.55, 1.02))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return rows


# ---------------------------------------------------------------- Figure 2: does it edit, and is the edit right?
RUNGS = [("L0", "no hint"), ("L2", "location"), ("W", "change in words"), ("L5", "exact fix")]
MIN_EDITS = 5


def fig2(k1: dict, held_v: dict | None, out: Path) -> list[tuple]:
    rows = []
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharex=True)
    x = range(len(RUNGS))
    for j, size in enumerate(SIZES):
        dx = (j - 1) * 0.18
        for r_i, (rung, _) in enumerate(RUNGS):
            c = k1.get(f"{size}/{rung}")
            if not c:
                continue
            er, (elo, ehi) = c["edit_rate"], c["edit_rate_ci"]
            axes[0].plot([r_i + dx] * 2, [elo * 100, ehi * 100], color=COLOR[size], lw=2)
            axes[0].plot(r_i + dx, er * 100, MARKER[size], ms=7, color=COLOR[size])
            rows.append(("dev", size, rung, "edit_rate", c["samples"], c["edits_gold_file"], er))
            if c["edits_gold_file"] >= MIN_EDITS:
                pg, (plo, phi) = c["solve_given_edit"], c["solve_given_edit_ci"]
                axes[1].plot([r_i + dx] * 2, [plo * 100, phi * 100], color=COLOR[size], lw=2)
                axes[1].plot(r_i + dx, pg * 100, MARKER[size], ms=7, color=COLOR[size])
                rows.append(("dev", size, rung, "pass_given_edit", c["edits_gold_file"], c["solves"], pg))
            if held_v is not None:
                h = held_v.get("V", {}).get(f"{size}/{rung}")
                if h:
                    axes[0].plot(r_i + dx + 0.07, h["edit_rate"] * 100, MARKER[size], ms=7, mec=COLOR[size],
                                 mfc=SURFACE, mew=1.6)
                    rows.append(("held-out", size, rung, "edit_rate", h["samples"], h["edits"], h["edit_rate"]))
                    if h["edits"] >= MIN_EDITS and h.get("solves_given_edit") is not None:
                        axes[1].plot(r_i + dx + 0.07, h["solves_given_edit"] * 100, MARKER[size], ms=7,
                                     mec=COLOR[size], mfc=SURFACE, mew=1.6)
                        rows.append(("held-out", size, rung, "pass_given_edit", h["edits"], None,
                                     h["solves_given_edit"]))
    for ax, t in zip(axes, ["First action edits the right file (%)",
                            f"…and that edit passes the tests (%; shown if ≥ {MIN_EDITS} edits)"]):
        ax.set_title(t, loc="left", fontsize=11)
        ax.set_ylim(-3, 103)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        ax.set_xticks(list(x))
        ax.set_xticklabels([f"{r}\n{n}" for r, n in RUNGS])
    handles = [plt.Line2D([], [], marker=MARKER[s], color=COLOR[s], lw=2, ms=7, label=LABEL[s]) for s in SIZES]
    if held_v is not None:
        handles.append(plt.Line2D([], [], marker="o", color=INK2, mfc=SURFACE, lw=0, label="held-out (hollow)"))
    fig.legend(handles=handles, loc="upper center", ncol=len(handles), frameon=False, bbox_to_anchor=(0.5, 1.03))
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return rows


# ---------------------------------------------------------------- Figure 3: how 12b runs ended
ENDS = [("resolved", "solved", "#2a78d6", "white"), ("context_crash", "context crash", "#eb6834", INK),
        ("time_budget", "time budget", "#1baf7a", INK), ("tool_call_budget", "tool-call budget", "#eda100", INK),
        ("unresolved_other", "other failure", "#e87ba4", INK)]


def fig3(c06: dict, held_d2: dict | None, out: Path) -> list[tuple]:
    bars = [("no hint, output limit 16,384 (C05)", c06["A1_crashes"]["O0"]["ended_C05"]),
            ("no hint, output limit 8,192 (C06)", c06["A1_crashes"]["O0"]["ended_C06"]),
            ("location hint, 16,384 (C05)", c06["A1_crashes"]["O-all"]["ended_C05"]),
            ("location hint, 8,192 (C06)", c06["A1_crashes"]["O-all"]["ended_C06"])]
    if held_d2 is not None:
        bars.append(("held-out, no hint, 8,192 (D2)", held_d2["ended"]))
    fig, ax = plt.subplots(figsize=(10, 0.65 * len(bars) + 1.3))
    rows = []
    for i, (name, ended) in enumerate(bars):
        y = len(bars) - 1 - i
        left = 0
        for key, _, col, ink in ENDS:
            v = ended.get(key, 0)
            if v:
                ax.barh(y, v, left=left, color=col, edgecolor=SURFACE, linewidth=2, height=0.62)
                ax.text(left + v / 2, y, str(v), ha="center", va="center", fontsize=9, color=ink)
            left += v
            rows.append((name, key, v))
    ax.set_yticks(range(len(bars)))
    ax.set_yticklabels([b[0] for b in bars][::-1])
    ax.set_xlabel("runs (Gemma 4 12B, one run per task)")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c, _ in ENDS]
    ax.legend(handles, [lab for _, lab, _, _ in ENDS], loc="upper center", ncol=5, frameon=False,
              bbox_to_anchor=(0.45, 1.22))
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev-dir", type=Path, default=None)
    ap.add_argument("--heldout", type=Path, default=Path("results"))
    ap.add_argument("--out", type=Path, default=Path("paper"))
    a = ap.parse_args()
    (a.out / "figures").mkdir(parents=True, exist_ok=True)

    d1_dev = load("D1_dev_reference.json", a.dev_dir)  # C03 + C04 through the frozen D1 analysis code
    k1 = load("C03v_checks.json", a.dev_dir)["K1"]
    c06 = load("C06_analysis.json", a.dev_dir)
    held_d1 = load_opt(a.heldout / "D1_analysis.json")
    held_d1v = load_opt(a.heldout / "D1v_analysis.json")
    held_d2 = load_opt(a.heldout / "D2_analysis.json")

    r1 = fig1(d1_dev, held_d1, a.out / "figures" / "fig1_where_vs_what.png")
    r2 = fig2(k1, held_d1v, a.out / "figures" / "fig2_hesitation.png")
    r3 = fig3(c06, held_d2, a.out / "figures" / "fig3_runs_ended.png")

    lines = ["# Numbers plotted in the paper figures (generated by paper/make_figures.py; do not edit)", "",
             f"Dev source: pilot/c-bottleneck @ {DEV_REF[:7]}. Held-out files found: "
             f"D1={held_d1 is not None}, D1v={held_d1v is not None}, D2={held_d2 is not None}.", "",
             "## Figure 1 (median Δ log p, nats, [95% CI])", "", "| set | size | state | contrast | n | median | CI |",
             "|---|---|---|---|---|---|---|"]
    lines += [f"| {s} | {z} | {st} | {k} | {n} | {m:+.1f} | [{lo:+.1f}, {hi:+.1f}] |" for s, z, st, k, n, m, lo, hi in r1]
    lines += ["", "## Figure 2 (first sampled action at the use step)", "",
              "| set | size | rung | metric | denominator | count | rate |", "|---|---|---|---|---|---|---|"]
    lines += [f"| {s} | {z} | {r} | {m} | {d} | {c if c is not None else '—'} | {v:.0%} |" for s, z, r, m, d, c, v in r2]
    lines += ["", "## Figure 3 (how runs ended)", "", "| condition | ending | runs |", "|---|---|---|"]
    lines += [f"| {n} | {k} | {v} |" for n, k, v in r3]
    (a.out / "numbers.md").write_text("\n".join(lines) + "\n")
    print("wrote", a.out / "figures", a.out / "numbers.md")


if __name__ == "__main__":
    main()
