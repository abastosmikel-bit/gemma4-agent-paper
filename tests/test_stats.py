"""common/stats.py against independent implementations (statsmodels) and hand-computed values."""
import numpy as np
import pytest

from common import stats as cs


def test_holm_matches_hand_computation():
    adj = cs.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None})
    assert adj["a"] == pytest.approx(0.03) and adj["c"] == pytest.approx(0.06) and adj["b"] == pytest.approx(0.06)
    assert adj["d"] is None


def test_mcnemar_and_cochran_match_statsmodels():
    sm = pytest.importorskip("statsmodels.stats.contingency_tables")
    assert cs.mcnemar_exact(9, 1) == pytest.approx(sm.mcnemar([[5, 9], [1, 5]], exact=True).pvalue)
    rng = np.random.default_rng(1)
    x = (rng.random((27, 5)) < np.linspace(0.2, 0.8, 5)).astype(int)
    ref = sm.cochrans_q(x)
    got = cs.cochran_q(x)
    assert got["Q"] == pytest.approx(ref.statistic) and got["p"] == pytest.approx(ref.pvalue)


def test_page_trend_detects_order_and_bootstrap_brackets_median():
    rng = np.random.default_rng(2)
    rows = [[0 + rng.normal(), 1 + rng.normal(), 2 + rng.normal()] for _ in range(30)]
    assert cs.page_trend(rows)["p"] < 0.01
    assert cs.page_trend([r[::-1] for r in rows])["p"] > 0.5
    x = rng.normal(3, 1, 40)
    lo, hi = cs.bootstrap_ci(x, n=2000)
    assert lo < np.median(x) < hi
    assert cs.wilcoxon_p([0, 0, 0]) is None


def test_ratio_ci_and_auc():
    lo, hi = cs.bootstrap_ratio_ci([1, 2, 0, 1], [2, 2, 2, 2], n=2000)
    assert 0 <= lo <= 0.5 <= hi <= 1
    assert cs.auc([0.9, 0.8, 0.1], [1, 1, 0]) == 1.0
    assert cs.auc([0.5, 0.5], [1, 0]) == 0.5
