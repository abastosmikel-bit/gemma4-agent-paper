"""Paired statistics shared across pilots (no pilot-specific logic).

All functions take plain sequences and return plain floats/dicts so results can go straight into JSON.
Conventions: Wilcoxon and McNemar are two-sided; Page's L is one-sided by construction (it tests a
predicted order); bootstrap CIs are percentile intervals over the units given (usually tasks).
Requires numpy and scipy.
"""
from __future__ import annotations

import math
from typing import Callable, Iterable, Sequence

import numpy as np
from scipy import stats as _st


def _arr(x: Iterable[float]) -> np.ndarray:
    return np.asarray([v for v in x if v is not None and not (isinstance(v, float) and math.isnan(v))], dtype=float)


def bootstrap_ci(x: Sequence[float], stat: Callable = np.median, n: int = 10_000, seed: int = 0,
                 alpha: float = 0.05) -> tuple[float, float]:
    """Percentile CI of `stat` over resampled units. `stat` must accept axis=1."""
    a = _arr(x)
    if len(a) == 0:
        return (math.nan, math.nan)
    rng = np.random.default_rng(seed)
    vals = stat(a[rng.integers(0, len(a), size=(n, len(a)))], axis=1)
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return (float(lo), float(hi))


def bootstrap_ratio_ci(num: Sequence[float], den: Sequence[float], n: int = 10_000, seed: int = 0,
                       alpha: float = 0.05) -> tuple[float, float]:
    """CI of sum(num)/sum(den) with units (e.g. tasks) resampled together (cluster bootstrap)."""
    a, b = np.asarray(num, float), np.asarray(den, float)
    if len(a) == 0 or b.sum() == 0:
        return (math.nan, math.nan)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(n, len(a)))
    s_den = b[idx].sum(axis=1)
    ok = s_den > 0
    vals = a[idx].sum(axis=1)[ok] / s_den[ok]
    lo, hi = np.quantile(vals, [alpha / 2, 1 - alpha / 2])
    return (float(lo), float(hi))


def wilcoxon_p(x: Sequence[float]) -> float | None:
    """Two-sided Wilcoxon signed-rank p for paired differences (zeros dropped). None if not computable."""
    a = _arr(x)
    a = a[a != 0]
    if len(a) < 1:
        return None
    return float(_st.wilcoxon(a, zero_method="wilcox", alternative="two-sided").pvalue)


def mcnemar_exact(b: int, c: int) -> float | None:
    """Exact two-sided McNemar p from the discordant counts b (0->1) and c (1->0)."""
    if b + c == 0:
        return None
    return float(_st.binomtest(min(b, c), b + c, 0.5, alternative="two-sided").pvalue)


def holm(pvals: dict[str, float | None]) -> dict[str, float | None]:
    """Holm-adjusted p-values within one family. None entries stay None and are not counted."""
    items = sorted(((k, p) for k, p in pvals.items() if p is not None), key=lambda kv: kv[1])
    m, out, run = len(items), {k: None for k in pvals}, 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p))
        out[k] = run
    return out


def page_trend(blocks: Sequence[Sequence[float]]) -> dict:
    """Page's L test. Rows = blocks (e.g. tasks), columns = treatments in the PREDICTED increasing order."""
    a = np.asarray(blocks, float)
    if a.ndim != 2 or a.shape[0] < 2 or a.shape[1] < 3:
        return {"L": None, "p": None, "n": int(a.shape[0]) if a.ndim == 2 else 0}
    r = _st.page_trend_test(a)
    return {"L": float(r.statistic), "p": float(r.pvalue), "n": int(a.shape[0]), "k": int(a.shape[1])}


def cochran_q(binary: Sequence[Sequence[int]]) -> dict:
    """Cochran's Q for k related binary outcomes. Rows = blocks, columns = conditions."""
    x = np.asarray(binary, float)
    if x.ndim != 2 or x.shape[0] < 2 or x.shape[1] < 2:
        return {"Q": None, "p": None, "n": 0}
    k = x.shape[1]
    col, row, tot = x.sum(axis=0), x.sum(axis=1), x.sum()
    den = k * tot - (row ** 2).sum()
    if den == 0:
        return {"Q": 0.0, "p": 1.0, "n": int(x.shape[0]), "k": k}
    q = (k - 1) * (k * (col ** 2).sum() - tot ** 2) / den
    return {"Q": float(q), "p": float(_st.chi2.sf(q, k - 1)), "n": int(x.shape[0]), "k": k}


def spearman(x: Sequence[float], y: Sequence[float]) -> dict:
    a, b = np.asarray(x, float), np.asarray(y, float)
    if len(a) < 3:
        return {"rho": None, "p": None, "n": len(a)}
    r = _st.spearmanr(a, b)
    return {"rho": float(r.statistic), "p": float(r.pvalue), "n": len(a)}


def auc(scores: Sequence[float], labels: Sequence[int]) -> float | None:
    """ROC AUC (probability a positive outscores a negative; ties count 1/2)."""
    s, y = np.asarray(scores, float), np.asarray(labels, int)
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))
