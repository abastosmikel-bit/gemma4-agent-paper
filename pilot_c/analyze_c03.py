"""Analysis of the probe run (`notebooks/C03_probe__L4x4.ipynb` -> results/C03_probe.json). CPU only.

Writes:
  results/C03_analysis.json   every number below
  results/C03_tables.md       tables (data only)
  results/figures/C03_fig*.png / .svg   draft figures (data only)

Pre-registered tests follow docs/PLAN.md §6-7 (H1-H5; H6 needs the 12b validation). Everything in the
sections marked "exploratory" is not pre-registered.
Usage: python -m pilot_c.analyze_c03 [results/C03_probe.json]
"""
from __future__ import annotations

import collections
import json
import math
import sys
from pathlib import Path

import numpy as np

from common import stats as cs

ROOT = Path(__file__).resolve().parents[1]
SIZE_ORDER = ["e2b", "e4b", "12b", "31b"]  # ascending size; the ordered factor of H2/H4
LADDER_D2 = ["L0", "L2", "L3", "L4", "L5"]  # S-use depth-2 ladder cells (L1 is not sampled, PLAN §4.6)
ALPHA = 0.05
NBOOT = 10_000


def _r(x, k=3):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), k)


class Data:
    def __init__(self, d: dict):
        self.raw = d
        self.sizes = [s for s in SIZE_ORDER if any(r["size"] == s for r in d["d1"])]
        self.lp: dict = collections.defaultdict(dict)        # (size, state, cond) -> {task: logp} (rep 1)
        self.lp_rep2: dict = collections.defaultdict(dict)   # (size, state) -> {task: logp} for L0 rep 2
        self.mode: dict = collections.defaultdict(collections.Counter)
        for r in d["d1"]:
            if not r.get("ok"):
                continue
            if r.get("rep", 1) == 2:
                self.lp_rep2[(r["size"], r["state"])][r["task"]] = r["logp"]
            else:
                self.lp[(r["size"], r["state"], r["cond"])][r["task"]] = r["logp"]
                self.mode[(r["size"], r["state"], r["cond"])][r.get("mode")] += 1
        self.d2: dict = collections.defaultdict(lambda: collections.defaultdict(list))  # (size,state,cond) -> task -> rows
        for r in d["d2"]:
            if r.get("ok"):
                self.d2[(r["size"], r["state"], r["cond"])][r["task"]].append(r)
        self.d2_sizes = [s for s in self.sizes if any(k[0] == s for k in self.d2)]

    def delta(self, size, state, a, b) -> dict[str, float]:
        A, B = self.lp.get((size, state, a), {}), self.lp.get((size, state, b), {})
        return {t: A[t] - B[t] for t in sorted(set(A) & set(B))}


def summ(delta: dict[str, float], seed=0) -> dict:
    v = list(delta.values())
    if not v:
        return {"n": 0}
    lo, hi = cs.bootstrap_ci(v, n=NBOOT, seed=seed)
    return {"n": len(v), "median": _r(np.median(v)), "ci": [_r(lo), _r(hi)], "mean": _r(np.mean(v)),
            "share_pos": _r(np.mean(np.asarray(v) > 0)), "p": _r(cs.wilcoxon_p(v), 6)}


# --------------------------------------------------------------------------- depth 1 tables

FIND_CONDS = ["L1", "L2", "T", "W", "G-json", "G-edges", "G-adj", "X-file", "X-func", "X-graph"]
USE_CONDS = ["L1", "L2", "L3", "L4", "L5", "T", "W", "G-json", "G-edges", "G-adj",
             "X-file", "X-func", "X-graph", "X-test", "X-words"]
MATCHED = {"X-file": "L1", "X-func": "L2", "X-graph": "G-json", "X-test": "L3", "X-words": "L4"}


def depth1_tables(D: Data) -> dict:
    out = {}
    for size in D.sizes:
        for state, conds in (("find", FIND_CONDS), ("use", USE_CONDS)):
            for c in conds:
                out[f"{size}/{state}/{c}-L0"] = summ(D.delta(size, state, c, "L0"))
                if c in MATCHED:
                    out[f"{size}/{state}/{c}-{MATCHED[c]}"] = summ(D.delta(size, state, c, MATCHED[c]))
            r1, r2 = D.lp.get((size, state, "L0"), {}), D.lp_rep2.get((size, state), {})
            diffs = [abs(r1[t] - r2[t]) for t in set(r1) & set(r2)]
            out[f"{size}/{state}/L0-rerun-absdiff"] = {"n": len(diffs), "median": _r(np.median(diffs)) if diffs else None,
                                                       "max": _r(max(diffs)) if diffs else None}
            out[f"{size}/{state}/L0-logp"] = {"n": len(r1), "median": _r(np.median(list(r1.values()))) if r1 else None}
            out[f"{size}/{state}/modes"] = {c: dict(D.mode[(size, state, c)]) for c in ["L0"] + conds if D.mode[(size, state, c)]}
    return out


# --------------------------------------------------------------------------- depth 2 helpers

def use_task_flags(D: Data, size, cond) -> dict[str, dict]:
    """Per task over its S-use samples: any on_target / any exact, and sample counts."""
    out = {}
    for t, rows in D.d2.get((size, "use", cond), {}).items():
        edits = [r for r in rows if r.get("tool") == "edit_file" and r.get("edit_gold_file")]
        out[t] = {"n": len(rows), "any_on_target": int(any(r["on_target"] for r in rows)),
                  "any_exact": int(any(r["exact"] for r in rows)),
                  "n_edit": len(edits), "n_on_target": sum(r["on_target"] for r in rows),
                  "n_exact": sum(r["exact"] for r in rows), "n_applies": sum(r["applies"] for r in rows),
                  "n_edit_on_target": sum(r["on_target"] for r in edits), "n_edit_exact": sum(r["exact"] for r in edits),
                  "tools": collections.Counter(("write_file(other)" if r.get("tool") == "write_file" and not r.get("edit_gold_file")
                                                else r.get("tool") or "none") for r in rows)}
    return out


def mcnemar_tasks(a: dict[str, int], b: dict[str, int]) -> dict:
    ts = sorted(set(a) & set(b))
    up = sum(1 for t in ts if a[t] == 0 and b[t] == 1)
    down = sum(1 for t in ts if a[t] == 1 and b[t] == 0)
    return {"n": len(ts), "b_0to1": up, "c_1to0": down, "p": _r(cs.mcnemar_exact(up, down), 6)}


def depth2_tables(D: Data) -> dict:
    out: dict = {"find": {}, "use": {}, "cochran": {}, "threshold": {}}
    for size in D.d2_sizes:
        conds_f = sorted({k[2] for k in D.d2 if k[0] == size and k[1] == "find"}, key=lambda c: (c[0] != "L", c))
        base = {t: rows[0] for t, rows in D.d2.get((size, "find", "L0"), {}).items()}
        for c in conds_f:
            rows = {t: rs[0] for t, rs in D.d2[(size, "find", c)].items()}
            ent = {"n": len(rows)}
            for m in ("tool_call", "hit_file", "hit_func", "followed_wrong"):
                v = [int(r.get(m, False)) for r in rows.values()]
                ent[m] = _r(np.mean(v))
                if c != "L0" and m in ("hit_file", "hit_func"):
                    ent[f"{m}_vs_L0"] = mcnemar_tasks({t: int(r.get(m, False)) for t, r in base.items()},
                                                       {t: int(r.get(m, False)) for t, r in rows.items()})
            ent["tools"] = dict(collections.Counter(r.get("tool") for r in rows.values()))
            out["find"][f"{size}/{c}"] = ent
        conds_u = sorted({k[2] for k in D.d2 if k[0] == size and k[1] == "use"}, key=lambda c: (c[0] != "L", c))
        flags = {c: use_task_flags(D, size, c) for c in conds_u}
        for c in conds_u:
            f = flags[c]
            ts = sorted(f)
            n_s = sum(f[t]["n"] for t in ts)
            n_edit = sum(f[t]["n_edit"] for t in ts)
            tools = collections.Counter()
            for t in ts:
                tools.update(f[t]["tools"])
            ent = {"n_tasks": len(ts), "n_samples": n_s,
                   "task_any_on_target": _r(np.mean([f[t]["any_on_target"] for t in ts])),
                   "task_any_exact": _r(np.mean([f[t]["any_exact"] for t in ts])),
                   "sample_on_target": _r(sum(f[t]["n_on_target"] for t in ts) / n_s),
                   "sample_exact": _r(sum(f[t]["n_exact"] for t in ts) / n_s),
                   "sample_applies": _r(sum(f[t]["n_applies"] for t in ts) / n_s),
                   "edit_rate": _r(n_edit / n_s),
                   "edit_rate_ci": [_r(x) for x in cs.bootstrap_ratio_ci([f[t]["n_edit"] for t in ts], [f[t]["n"] for t in ts], NBOOT)],
                   "n_edit": n_edit,
                   "on_target_given_edit": _r(sum(f[t]["n_edit_on_target"] for t in ts) / n_edit) if n_edit else None,
                   "on_target_given_edit_ci": [_r(x) for x in cs.bootstrap_ratio_ci([f[t]["n_edit_on_target"] for t in ts], [f[t]["n_edit"] for t in ts], NBOOT)] if n_edit else None,
                   "exact_given_edit": _r(sum(f[t]["n_edit_exact"] for t in ts) / n_edit) if n_edit else None,
                   "exact_given_edit_ci": [_r(x) for x in cs.bootstrap_ratio_ci([f[t]["n_edit_exact"] for t in ts], [f[t]["n_edit"] for t in ts], NBOOT)] if n_edit else None,
                   "tool_shares": {k: _r(v / n_s) for k, v in tools.most_common()}}
            if c != "L0":
                for m in ("any_on_target", "any_exact"):
                    ent[f"{m}_vs_L0"] = mcnemar_tasks({t: v[m] for t, v in flags["L0"].items()}, {t: v[m] for t, v in f.items()})
            out["use"][f"{size}/{c}"] = ent
        for m in ("any_on_target", "any_exact"):
            ts = sorted(set.intersection(*[set(flags[c]) for c in LADDER_D2 if c in flags]))
            mat = [[flags[c][t][m] for c in LADDER_D2] for t in ts]
            out["cochran"][f"{size}/{m}"] = {**cs.cochran_q(mat), "conds": LADDER_D2}
        # information threshold (PLAN §5), exact only: `solves` needs notebooks/C03v_test_verify__CPU.ipynb
        thr = collections.Counter()
        for t in sorted(flags["L0"]):
            lvl = None
            for c in LADDER_D2:
                if t in flags.get(c, {}) and flags[c][t]["any_exact"]:
                    lvl = c
                    break
            missing = any(t not in flags.get(c, {}) for c in LADDER_D2)
            thr[lvl or (">L5" if not missing else "none (L4/L5 missing)")] += 1
        out["threshold"][size] = dict(thr)
    return out


# --------------------------------------------------------------------------- pre-registered hypotheses

def hypotheses(D: Data, d2: dict) -> dict:
    H: dict = {}
    # H1: location at find vs use
    for size in D.sizes:
        df, du = D.delta(size, "find", "L2", "L0"), D.delta(size, "use", "L2", "L0")
        diff = {t: df[t] - du[t] for t in set(df) & set(du)}
        p = cs.holm({"find>0": cs.wilcoxon_p(list(df.values())), "find>use": cs.wilcoxon_p(list(diff.values()))})
        sf, su, sd = summ(df), summ(du), summ(diff)
        H[f"H1/{size}"] = {
            "d_find_L2-L0": sf, "d_use_L2-L0": su, "d_find-minus-d_use": sd,
            "p_holm": {k: _r(v, 6) for k, v in p.items()},
            "part1_supported": bool(sf["median"] > 0 and p["find>0"] is not None and p["find>0"] < ALPHA),
            "part2_supported": bool(su["median"] < sf["median"] and sd["median"] > 0 and p["find>use"] is not None and p["find>use"] < ALPHA)}
    # H2: words gain rises with size, diff gain falls with size (Page's L over the available sizes)
    fam = {}
    for name, (a, b), increasing in (("L4-L3", ("L4", "L3"), True), ("L5-L4", ("L5", "L4"), False)):
        per = {s: D.delta(s, "use", a, b) for s in D.sizes}
        ts = sorted(set.intersection(*[set(v) for v in per.values()]))
        cols = D.sizes if increasing else list(reversed(D.sizes))
        pg = cs.page_trend([[per[s][t] for s in cols] for t in ts])
        fam[name] = pg["p"]
        H[f"H2/{name}"] = {"predicted": "increases with size" if increasing else "decreases with size",
                           "sizes_used": D.sizes, "page": pg, "per_size": {s: summ(per[s]) for s in D.sizes}}
    for name, p in cs.holm(fam).items():
        pg = H[f"H2/{name}"]
        pg["p_holm"] = _r(p, 6)
        pg["supported"] = bool(p is not None and p < ALPHA)
    # H3: graph encodings
    for size in D.sizes:
        pair = {"G-edges-G-json": D.delta(size, "find", "G-edges", "G-json"),
                "G-adj-G-json": D.delta(size, "find", "G-adj", "G-json"),
                "G-adj-G-edges": D.delta(size, "find", "G-adj", "G-edges")}
        vsl2 = {g: D.delta(size, "find", g, "L2") for g in ("G-json", "G-edges", "G-adj")}
        small = size in ("e2b", "e4b")
        fam = {f"{g}<L2": cs.wilcoxon_p(list(v.values())) for g, v in vsl2.items()}
        if small:
            fam.update({"G-edges>G-json": cs.wilcoxon_p(list(pair["G-edges-G-json"].values())),
                        "G-adj>G-json": cs.wilcoxon_p(list(pair["G-adj-G-json"].values()))})
        ph = cs.holm(fam)
        ent = {"pairs": {k: summ(v) for k, v in pair.items()}, "vs_L2": {g: summ(v) for g, v in vsl2.items()},
               "p_holm": {k: _r(v, 6) for k, v in ph.items()},
               "graph_below_L2_supported": all(summ(v)["median"] < 0 and ph[f"{g}<L2"] is not None and ph[f"{g}<L2"] < ALPHA for g, v in vsl2.items()),
               "scoring_modes": {c: dict(D.mode[(size, "find", c)]) for c in ("L0", "L2", "G-json")}}
        if small:
            ent["edges_adj_beat_json_supported"] = all(
                summ(pair[k])["median"] > 0 and ph[h] is not None and ph[h] < ALPHA
                for k, h in (("G-edges-G-json", "G-edges>G-json"), ("G-adj-G-json", "G-adj>G-json")))
        if size == "31b":
            ent["encodings_within_0.3_supported"] = all(abs(summ(v)["median"]) < 0.3 for v in pair.values())
        if size == "12b":
            ent["note"] = "encoding comparison is not pre-registered for 12b (exploratory)"
        H[f"H3/{size}"] = ent
    # H4: wrong hints at find
    for size in D.sizes:
        dd = {x: D.delta(size, "find", x, "L0") for x in ("X-file", "X-func", "X-graph")}
        ph = cs.holm({x: cs.wilcoxon_p(list(v.values())) for x, v in dd.items()})
        H[f"H4/{size}"] = {"vs_L0": {x: summ(v) for x, v in dd.items()},
                           "vs_matched": {x: summ(D.delta(size, "find", x, MATCHED[x])) for x in dd},
                           "p_holm": {k: _r(v, 6) for k, v in ph.items()},
                           "supported": {x: bool(summ(v)["median"] < 0 and ph[x] is not None and ph[x] < ALPHA) for x, v in dd.items()}}
    fam, pages = {}, {}
    for x in ("X-file", "X-func", "X-graph"):
        per = {s: D.delta(s, "find", x, "L0") for s in D.sizes}
        ts = sorted(set.intersection(*[set(v) for v in per.values()]))
        pages[x] = cs.page_trend([[per[s][t] for s in D.sizes] for t in ts])  # predicted: harm shrinks with size
        fam[x] = pages[x]["p"]
    ph = cs.holm(fam)
    H["H4/trend"] = {"predicted": "Δ(X−L0) increases with size (less harm for larger sizes)", "sizes_used": D.sizes,
                     "page": pages, "p_holm": {k: _r(v, 6) for k, v in ph.items()},
                     "trend_in_predicted_direction": {x: bool(ph[x] is not None and ph[x] < ALPHA) for x in pages},
                     "harm_at_every_size": {x: all(summ(D.delta(s, "find", x, "L0"))["median"] < 0 for s in D.sizes) for x in pages}}
    H["H4/trend"]["supported"] = {x: H["H4/trend"]["trend_in_predicted_direction"][x] and H["H4/trend"]["harm_at_every_size"][x]
                                  for x in pages}
    # H5: e4b on_target at S-use, L5 vs L2
    for size in D.d2_sizes:
        u = d2["use"]
        l5, l2 = u.get(f"{size}/L5"), u.get(f"{size}/L2")
        if not (l5 and l2):
            continue
        f5, f2 = use_task_flags(D, size, "L5"), use_task_flags(D, size, "L2")
        ent = {"task_any_on_target": {"L2": l2["task_any_on_target"], "L5": l5["task_any_on_target"]},
               "sample_on_target": {"L2": l2["sample_on_target"], "L5": l5["sample_on_target"]},
               "task_any_exact": {"L2": l2["task_any_exact"], "L5": l5["task_any_exact"]},
               "mcnemar_on_target_L2_vs_L5": mcnemar_tasks({t: v["any_on_target"] for t, v in f2.items()},
                                                           {t: v["any_on_target"] for t, v in f5.items()}),
               "mcnemar_exact_L2_vs_L5": mcnemar_tasks({t: v["any_exact"] for t, v in f2.items()},
                                                       {t: v["any_exact"] for t, v in f5.items()}),
               "primary_unit": "task (at least 1 of 2 samples), as in the PLAN §5 threshold rule; samples also shown"}
        ent["L5_ge_50"] = bool(l5["task_any_on_target"] >= 0.5)
        ent["L2_le_20"] = bool(l2["task_any_on_target"] <= 0.2)
        ent["supported"] = ent["L5_ge_50"] and ent["L2_le_20"]
        ent["pre_registered"] = size == "e4b"
        H[f"H5/{size}"] = ent
    H["H6"] = {"status": "not testable: needs the 12b rollout validation (PLAN §8), not run"}
    return H


# --------------------------------------------------------------------------- exploratory checks (coordinator's questions)

def graph_check(D: Data, d2: dict) -> dict:
    out = {}
    comps = [("L1-L0", "L1", "L0"), ("L2-L1", "L2", "L1"), ("X-func-L0", "X-func", "L0"), ("L2-X-func", "L2", "X-func"),
             ("G-json-L0", "G-json", "L0"), ("X-graph-L0", "X-graph", "L0"), ("G-json-X-graph", "G-json", "X-graph"),
             ("X-graph-L1", "X-graph", "L1"), ("G-json-L2", "G-json", "L2")]
    for size in D.sizes:
        for state in ("find", "use"):
            ent = {name: summ(D.delta(size, state, a, b)) for name, a, b in comps}
            ent["modes"] = {c: dict(D.mode[(size, state, c)]) for c in ("L0", "L1", "L2", "G-json", "X-graph")}
            out[f"{size}/{state}"] = ent
    out["depth2_find"] = {k: {m: v.get(m) for m in ("n", "hit_file", "hit_func")} for k, v in d2["find"].items()}
    return out


def edit_check(d2: dict) -> dict:
    return {k: {m: v.get(m) for m in ("n_samples", "edit_rate", "edit_rate_ci", "n_edit", "on_target_given_edit",
                                       "on_target_given_edit_ci", "exact_given_edit", "exact_given_edit_ci",
                                       "sample_on_target", "task_any_on_target", "tool_shares")}
            for k, v in d2["use"].items()}


# --------------------------------------------------------------------------- tables (markdown)

def _ci(s):
    if not s or not s.get("n"):
        return "—"
    return f"{s['median']:+.1f} [{s['ci'][0]:+.1f}, {s['ci'][1]:+.1f}]"


def _p(p):
    return "—" if p is None else ("<0.001" if p < 0.001 else f"{p:.3f}")


def _pct(x):
    return "—" if x is None else f"{100 * x:.0f}%"


def tables_md(D: Data, A: dict) -> str:
    T, d1, d2, H = [], A["depth1"], A["depth2"], A["hypotheses"]
    S = D.sizes
    T.append("# C03 probe — tables (data only)\n")
    T.append(f"Source: `results/C03_probe.json` (`notebooks/C03_probe__L4x4.ipynb`, plan {D.raw['plan_commit'][:7]}). "
             "Produced by `pilot_c/analyze_c03.py`. Single run. Δ in nats, median over tasks [95% bootstrap CI, 10,000 resamples]. "
             "p: two-sided Wilcoxon signed-rank (unadjusted unless marked Holm).\n")
    # coverage
    T.append("## T0. Coverage\n")
    T.append("| Size | depth-1 cells ok | depth-2 samples ok | skipped | server start (s) | depth 1 (min) | depth 2 (min) | L0 rerun |Δ| find median / max | use median / max |")
    T.append("|---|---|---|---|---|---|---|---|---|")
    for s in D.raw["sizes"]:
        size = s.get("size") or s["model"].split("-")[2]
        n1 = sum(1 for r in D.raw["d1"] if r["size"] == size and r["ok"])
        n2 = sum(1 for r in D.raw["d2"] if r["size"] == size and r["ok"])
        rf, ru = d1.get(f"{size}/find/L0-rerun-absdiff", {}), d1.get(f"{size}/use/L0-rerun-absdiff", {})
        T.append(f"| {size} | {n1} | {n2} | {s.get('skipped') or '—'} | {s.get('startup_s', '—')} | {s.get('d1_minutes', '—')} | "
                 f"{s.get('d2_minutes', '—')} | {rf.get('median', '—')} / {rf.get('max', '—')} | {ru.get('median', '—')} / {ru.get('max', '—')} |")
    T.append(f"\nSession: {D.raw['session_elapsed_h']} h; freezes: {len(D.raw['freezes'])}; tasks: {len(D.raw['task_ids'])}; "
             f"excluded before probing: {len(D.raw['excluded'])}.\n")
    # depth 1
    for state, conds in (("find", FIND_CONDS), ("use", USE_CONDS)):
        T.append(f"## T1-{state}. Depth 1, S-{state}: Δ vs L0 (and X vs its matched correct rung)\n")
        T.append("| Condition | " + " | ".join(f"{s} Δ [CI]" for s in S) + " | " + " | ".join(f"{s} n, p" for s in S) + " |")
        T.append("|---|" + "---|" * (2 * len(S)))
        rows = [(f"{c} − L0", f"{c}-L0") for c in conds] + [(f"{x} − {m}", f"{x}-{m}") for x, m in MATCHED.items() if x in conds]
        for label, key in rows:
            cells = [d1.get(f"{s}/{state}/{key}") for s in S]
            T.append(f"| {label} | " + " | ".join(_ci(c) for c in cells) + " | " +
                     " | ".join("—" if not c or not c.get("n") else f"{c['n']}, {_p(c['p'])}" for c in cells) + " |")
        T.append("")
        T.append("Scoring mode per condition (PLAN §11 dev. 8): " + "; ".join(
            f"{s}: " + ", ".join(f"{c}={'/'.join(m)}" for c, m in d1[f"{s}/{state}/modes"].items())
            for s in S if s in ("31b", "12b")) + "\n")
    # hypotheses
    T.append("## T2. Pre-registered hypotheses (PLAN §6), per size\n")
    T.append("| Hypothesis | Size | Statistic | Value | p (Holm) | Verdict |")
    T.append("|---|---|---|---|---|---|")
    for s in S:
        h = H[f"H1/{s}"]
        T.append(f"| H1 location helps find | {s} | Δ_find(L2−L0) | {_ci(h['d_find_L2-L0'])} | {_p(h['p_holm']['find>0'])} | {'supported' if h['part1_supported'] else 'not supported'} |")
        T.append(f"| H1 find > use | {s} | Δ_use(L2−L0); Δ_find−Δ_use | {_ci(h['d_use_L2-L0'])}; {_ci(h['d_find-minus-d_use'])} | {_p(h['p_holm']['find>use'])} | {'supported' if h['part2_supported'] else 'not supported'} |")
    for k in ("L4-L3", "L5-L4"):
        h = H[f"H2/{k}"]
        T.append(f"| H2 Δ_use({k.replace('-', '−')}) {h['predicted']} | {', '.join(h['sizes_used'])} (e2b missing) | Page L (n={h['page']['n']}); medians " +
                 ", ".join(f"{s} {h['per_size'][s]['median']:+.1f}" for s in S) + f" | L={_r(h['page']['L'], 1)} | {_p(h['p_holm'])} | {'supported' if h['supported'] else 'not supported'} |")
    for s in S:
        h = H[f"H3/{s}"]
        for g in ("G-json", "G-edges", "G-adj"):
            T.append(f"| H3 graph < L2 (find) | {s} | {g} − L2 | {_ci(h['vs_L2'][g])} | {_p(h['p_holm'][g + '<L2'])} | " +
                     ("—" if g != "G-adj" else ("supported (all three)" if h["graph_below_L2_supported"] else "not supported")) + " |")
        for k in ("G-edges-G-json", "G-adj-G-json", "G-adj-G-edges"):
            hk = {"G-edges-G-json": "G-edges>G-json", "G-adj-G-json": "G-adj>G-json"}.get(k)
            verdict = "—"
            if s in ("e2b", "e4b") and k == "G-adj-G-json":
                verdict = "supported" if h.get("edges_adj_beat_json_supported") else "not supported"
            if s == "31b" and k == "G-adj-G-edges":
                verdict = "supported (|median| < 0.3 for all pairs)" if h.get("encodings_within_0.3_supported") else "not supported (some |median| ≥ 0.3)"
            if s == "12b":
                verdict = "exploratory"
            T.append(f"| H3 encodings (find) | {s} | {k.replace('-G', ' − G')} | {_ci(h['pairs'][k])} | {_p(h['p_holm'].get(hk)) if hk and hk in h['p_holm'] else _p(h['pairs'][k]['p']) + ' (unadj.)'} | {verdict} |")
    for s in S:
        h = H[f"H4/{s}"]
        for x in ("X-file", "X-func", "X-graph"):
            T.append(f"| H4 wrong hint harms (find) | {s} | {x} − L0 | {_ci(h['vs_L0'][x])} | {_p(h['p_holm'][x])} | {'supported' if h['supported'][x] else 'not supported'} |")
    h = H["H4/trend"]
    for x in ("X-file", "X-func", "X-graph"):
        v = ("supported" if h["supported"][x] else
             "not supported (trend in predicted direction, but Δ > 0 at some size: no harm to shrink)" if h["trend_in_predicted_direction"][x]
             else "not supported")
        T.append(f"| H4 harm shrinks with size | {', '.join(h['sizes_used'])} | Page L (n={h['page'][x]['n']}), {x} − L0 | L={_r(h['page'][x]['L'], 1)} | {_p(h['p_holm'][x])} | {v} |")
    for s in D.d2_sizes:
        h = H.get(f"H5/{s}")
        if not h:
            continue
        tag = "" if h["pre_registered"] else " (exploratory: H5 is about e4b)"
        T.append(f"| H5 on_target L5 ≥ 50%, L2 ≤ 20%{tag} | {s} | tasks with ≥1 of 2 on_target: L2, L5 (samples: L2, L5) | "
                 f"{_pct(h['task_any_on_target']['L2'])}, {_pct(h['task_any_on_target']['L5'])} ({_pct(h['sample_on_target']['L2'])}, {_pct(h['sample_on_target']['L5'])}) | "
                 f"McNemar {_p(h['mcnemar_on_target_L2_vs_L5']['p'])} | {'supported' if h['supported'] else 'not supported'} (L5≥50%: {h['L5_ge_50']}, L2≤20%: {h['L2_le_20']}) |")
    T.append("| H6 probe predicts rollout flips | 12b | AUC | — | — | not testable (validation not run) |")
    T.append("")
    # depth 2 find
    T.append("## T3. Depth 2, S-find (1 sample per task): share of tasks\n")
    T.append("| Size | Condition | n | hit_file | hit_func | McNemar vs L0 (file; func) | tools |")
    T.append("|---|---|---|---|---|---|---|")
    for k, v in d2["find"].items():
        s, c = k.split("/")
        mc = "—" if c == "L0" else f"{_p(v['hit_file_vs_L0']['p'])}; {_p(v['hit_func_vs_L0']['p'])}"
        T.append(f"| {s} | {c} | {v['n']} | {_pct(v['hit_file'])} | {_pct(v['hit_func'])} | {mc} | " +
                 ", ".join(f"{t} {n}" for t, n in v["tools"].items()) + " |")
    T.append("")
    # depth 2 use
    T.append("## T4. Depth 2, S-use (2 samples per task)\n")
    T.append("| Size | Condition | tasks / samples | tasks ≥1 on_target | tasks ≥1 exact | McNemar vs L0 (on_target; exact) | samples: edit_file on gold file [CI] | on_target given edit [CI] | exact given edit [CI] |")
    T.append("|---|---|---|---|---|---|---|---|---|")
    for k, v in d2["use"].items():
        s, c = k.split("/")
        mc = "—" if c == "L0" else f"{_p(v['any_on_target_vs_L0']['p'])}; {_p(v['any_exact_vs_L0']['p'])}"
        ci = lambda x: "—" if not x else f"[{_pct(x[0])}, {_pct(x[1])}]"  # noqa: E731
        T.append(f"| {s} | {c} | {v['n_tasks']} / {v['n_samples']} | {_pct(v['task_any_on_target'])} | {_pct(v['task_any_exact'])} | {mc} | "
                 f"{_pct(v['edit_rate'])} {ci(v['edit_rate_ci'])} | {_pct(v['on_target_given_edit'])} {ci(v['on_target_given_edit_ci'])} (n={v['n_edit']}) | "
                 f"{_pct(v['exact_given_edit'])} {ci(v['exact_given_edit_ci'])} |")
    T.append("")
    T.append("Cochran's Q across " + ", ".join(LADDER_D2) + " (tasks with all five cells): " + "; ".join(
        f"{k}: Q={_r(v['Q'], 1)}, p={_p(v['p'])}, n={v['n']}" for k, v in d2["cochran"].items()) + "\n")
    T.append("## T5. Information threshold per task (lowest S-use rung with ≥1 of 2 samples `exact`; `solves` pending `notebooks/C03v_test_verify__CPU.ipynb`)\n")
    T.append("| Size | " + " | ".join(LADDER_D2 + [">L5", "none (L4/L5 missing)"]) + " |")
    T.append("|---|" + "---|" * (len(LADDER_D2) + 2))
    for s, thr in d2["threshold"].items():
        T.append(f"| {s} | " + " | ".join(str(thr.get(c, 0)) for c in LADDER_D2 + [">L5", "none (L4/L5 missing)"]) + " |")
    T.append("")
    # exploratory
    T.append("## T6. Exploratory: graph rung vs text location (coordinator's question a)\n")
    G = A["exploratory"]["graph"]
    names = ["L1-L0", "L2-L1", "X-func-L0", "L2-X-func", "G-json-L0", "X-graph-L0", "G-json-X-graph", "X-graph-L1", "G-json-L2"]
    T.append("| Size / state | " + " | ".join(n.replace("-", " − ").replace("G − json", "G-json").replace("X − graph", "X-graph").replace("X − func", "X-func") for n in names) + " | scoring mode L0 / G-json |")
    T.append("|---|" + "---|" * (len(names) + 1))
    for k, v in G.items():
        if k == "depth2_find":
            continue
        md = v["modes"]
        T.append(f"| {k} | " + " | ".join(_ci(v[n]) for n in names) + f" | {'/'.join(md.get('L0', {}))} / {'/'.join(md.get('G-json', {}))} |")
    T.append("")
    T.append("## T7. Exploratory: first action at S-use (coordinator's question b), share of samples\n")
    E = A["exploratory"]["edit"]
    tools = ["edit_file", "read_file", "run_command", "write_file(other)", "get_code_neighbors", "search_similar_code"]
    T.append("| Size | Condition | n | " + " | ".join(tools) + " |")
    T.append("|---|---|---|" + "---|" * len(tools))
    for k, v in E.items():
        s, c = k.split("/")
        T.append(f"| {s} | {c} | {v['n_samples']} | " + " | ".join(_pct(v["tool_shares"].get(t, 0.0)) for t in tools) + " |")
    T.append("")
    return "\n".join(T)


# --------------------------------------------------------------------------- figures (data only)

COLORS = {"e4b": "#2a78d6", "12b": "#eb6834", "31b": "#1baf7a", "e2b": "#eda100"}  # fixed per size (slot 4 = e2b, later)
MARKERS = {"e4b": "o", "12b": "s", "31b": "D", "e2b": "^"}
INK, INK2, GRID, SURF = "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
MIN_EDITS_FOR_RATE = 5


def _style(ax):
    ax.set_facecolor(SURF)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(INK2)
    ax.tick_params(colors=INK2, labelsize=8, length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


def _dotrows(ax, rows, sizes, getter, xlabel, zero=True):
    k = len(sizes)
    off = {s: (i - (k - 1) / 2) * 0.22 for i, s in enumerate(sizes)}
    for yi, label in enumerate(rows):
        for s in sizes:
            v = getter(s, label)
            if not v:
                continue
            m, lo, hi = v
            y = yi + off[s]
            ax.plot([lo, hi], [y, y], color=COLORS[s], linewidth=1.2, solid_capstyle="round")
            ax.plot([m], [y], marker=MARKERS[s], color=COLORS[s], markersize=4.5, markeredgecolor=SURF, markeredgewidth=0.8, linestyle="none")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows)
    if not ax.yaxis_inverted():  # shared y axes: invert once
        ax.invert_yaxis()
    if zero:
        ax.axvline(0, color=INK2, linewidth=0.8)
    ax.set_xlabel(xlabel, color=INK2, fontsize=8)
    _style(ax)


def _legend(fig, sizes):
    import matplotlib.lines as ml
    h = [ml.Line2D([], [], color=COLORS[s], marker=MARKERS[s], linestyle="-", linewidth=1.2, markersize=4.5, label=s) for s in sizes]
    fig.legend(handles=h, loc="upper right", bbox_to_anchor=(1.0, 1.0), ncol=len(sizes), frameon=False, fontsize=8, labelcolor=INK)


def figures(D: Data, A: dict, outdir: Path, stem: str = "C03") -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    outdir.mkdir(parents=True, exist_ok=True)
    d1, made = A["depth1"], []

    def g1(state):
        def f(s, c):
            v = d1.get(f"{s}/{state}/{c}-L0")
            return (v["median"], *v["ci"]) if v and v.get("n") else None
        return f

    fig, axes = plt.subplots(1, 2, figsize=(9, 5.2), gridspec_kw={"width_ratios": [1, 1.25]}, facecolor=SURF)
    _dotrows(axes[0], FIND_CONDS, D.sizes, g1("find"), "Δ log p(target) vs L0, nats (median, 95% CI)")
    axes[0].set_title("S-find", color=INK, fontsize=10, loc="left")
    _dotrows(axes[1], USE_CONDS, D.sizes, g1("use"), "Δ log p(target) vs L0, nats (median, 95% CI)")
    axes[1].set_title("S-use", color=INK, fontsize=10, loc="left")
    fig.suptitle("Depth 1: gain in target log-likelihood over L0, per condition and size", color=INK, fontsize=10, x=0.01, y=0.985, ha="left")
    _legend(fig, D.sizes)
    fig.tight_layout(rect=(0, 0, 1, 0.955))
    for ext in ("png", "svg"):
        p = outdir / f"{stem}_fig1_depth1_deltas.{ext}"
        fig.savefig(p, dpi=200, facecolor=SURF)
        made.append(p.name)
    plt.close(fig)

    u = A["depth2"]["use"]
    conds = [c for c in ("L0", "L2", "L3", "L4", "L5", "T", "W", "G-json", "X-func", "X-test") if any(f"{s}/{c}" in u for s in D.d2_sizes)]
    panels = [("edit_rate", "edit_rate_ci", "edit_file on the gold file, share of samples"),
              ("on_target_given_edit", "on_target_given_edit_ci", "on_target among those edits"),
              ("exact_given_edit", "exact_given_edit_ci", "exact among those edits")]  # shown only with >= 5 edits
    fig, axes = plt.subplots(1, 3, figsize=(10, 4.2), sharey=True, facecolor=SURF)
    for ax, (m, mci, lab) in zip(axes, panels):
        def g(s, c, m=m, mci=mci):
            v = u.get(f"{s}/{c}")
            if m != "edit_rate" and v and (v.get("n_edit") or 0) < MIN_EDITS_FOR_RATE:
                return None  # conditional rate on fewer than MIN_EDITS_FOR_RATE edits: not shown (n in T4)
            return (v[m], *v[mci]) if v and v.get(m) is not None and v.get(mci) else None
        _dotrows(ax, conds, D.d2_sizes, g, lab + " (95% CI)", zero=False)
        ax.set_xlim(-0.03, 1.03)
    fig.suptitle("Depth 2, S-use: does the model edit now, and how good is the edit when it does", color=INK, fontsize=10, x=0.01, y=0.985, ha="left")
    _legend(fig, D.d2_sizes)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    for ext in ("png", "svg"):
        p = outdir / f"{stem}_fig2_depth2_use_edit.{ext}"
        fig.savefig(p, dpi=200, facecolor=SURF)
        made.append(p.name)
    plt.close(fig)

    G = A["exploratory"]["graph"]
    comps = [("L1-L0", "text: file (L1 − L0)"), ("X-func-L0", "text: file + wrong function (X-func − L0)"),
             ("L2-X-func", "text: right vs wrong function (L2 − X-func)"), ("X-graph-L0", "graph: wrong focus, same file (X-graph − L0)"),
             ("G-json-X-graph", "graph: right vs wrong focus (G-json − X-graph)"), ("X-graph-L1", "graph wrong focus vs text file (X-graph − L1)")]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), sharey=True, facecolor=SURF)
    for ax, state in zip(axes, ("find", "use")):
        def g(s, lab, state=state):
            key = dict((b, a) for a, b in comps)[lab]
            v = G.get(f"{s}/{state}", {}).get(key)
            return (v["median"], *v["ci"]) if v and v.get("n") else None
        _dotrows(ax, [b for _, b in comps], D.sizes, g, "Δ log p(target), nats (median, 95% CI)")
        ax.set_title(f"S-{state}", color=INK, fontsize=10, loc="left")
    fig.suptitle("Location as text vs as graph-tool output (exploratory decomposition)", color=INK, fontsize=10, x=0.01, y=0.985, ha="left")
    _legend(fig, D.sizes)
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    for ext in ("png", "svg"):
        p = outdir / f"{stem}_fig3_graph_vs_text.{ext}"
        fig.savefig(p, dpi=200, facecolor=SURF)
        made.append(p.name)
    plt.close(fig)
    return made


def analyze_all(d: dict, source: str, out_dir: Path, fig_dir: Path, stem: str = "C03") -> dict:
    """Every table and figure of this module for a probe result dict `d` (C03's, or C03 merged with C04's design
    cells); writes <stem>_analysis.json, <stem>_tables.md and <stem>_fig*.png/svg."""
    D = Data(d)
    A = {"source": source, "plan_commit": d["plan_commit"], "sizes_with_depth1": D.sizes, "sizes_with_depth2": D.d2_sizes,
         "depth1": depth1_tables(D)}
    A["depth2"] = depth2_tables(D)
    A["hypotheses"] = hypotheses(D, A["depth2"])
    A["exploratory"] = {"graph": graph_check(D, A["depth2"]), "edit": edit_check(A["depth2"])}
    try:
        A["figures"] = figures(D, A, fig_dir, stem)
    except ImportError as e:   # matplotlib missing: tables still written
        A["figures"] = [f"skipped: {e}"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{stem}_analysis.json").write_text(json.dumps(A, indent=1, ensure_ascii=False, default=str))
    (out_dir / f"{stem}_tables.md").write_text(tables_md(D, A).replace("Source: `results/C03_probe.json`", f"Source: `{source}`"))
    print(f"wrote {out_dir}/{stem}_analysis.json, {stem}_tables.md,", ", ".join(A["figures"]))
    return A


def main(path: str = "results/C03_probe.json") -> None:
    analyze_all(json.load(open(ROOT / path)), path, ROOT / "results", ROOT / "results" / "figures", "C03")


if __name__ == "__main__":
    main(*sys.argv[1:])
