import numpy as np
import pandas as pd
import pytest

from macro import fincond as fc


def _sim(n=200, seed=5):
    g = np.random.default_rng(seed)
    idx = pd.date_range("1975-01-01", periods=n, freq="QS")
    lv = pd.DataFrame(
        {
            "policy_rate": 4 + np.cumsum(g.normal(0, 0.4, n)),
            "y10": 5 + np.cumsum(g.normal(0, 0.3, n)),
            "equity": 100 * np.exp(np.cumsum(g.normal(0.015, 0.07, n))),
            "dollar": 100 * np.exp(np.cumsum(g.normal(0, 0.03, n))),
        },
        index=idx,
    )
    dx = fc.changes(lv, 4)
    true = pd.Series({"policy_rate": -0.4, "y10": -0.6, "equity": 0.03, "dollar": -0.05})
    impulse = (dx * true).sum(axis=1)
    fwd = impulse + g.normal(0, 0.3, n) + 2.0
    lg = np.zeros(n)
    # build log GDP so that the 4-quarter-ahead growth equals fwd
    for t in range(n - 4):
        lg[t + 4] = lg[t] + fwd.iloc[t] if not np.isnan(fwd.iloc[t]) else lg[t] + 2.0
    gdp = pd.Series(np.exp(lg / 100) * 1000, index=idx)
    return lv, gdp, true


def test_fci_lite_recovers_sign_and_scale():
    lv, gdp, true = _sim()
    r = fc.fci_lite(lv, gdp, lookback=4, n_boot=200, seed=1)
    b = r.extra["betas"]["beta"]
    assert (np.sign(b) == np.sign(true)).all()
    assert np.corrcoef(b, true)[0, 1] > 0.9
    # decomposition adds up and positive = headwind
    contrib = r.extra["contributions"]
    assert np.allclose(contrib.sum(axis=1), r.value)
    assert r.lower <= r.value.iloc[-1] <= r.upper


def test_gap_and_equivalences():
    g = fc.gap_to_neutral(fci_now=0.2, output_gap=1.6, horizon_q=8)
    assert g["fci_target"] == pytest.approx(0.8)
    assert g["gap"] == pytest.approx(0.6)
    draws = pd.DataFrame(
        {"y10": np.full(100, -0.6), "equity": np.full(100, 0.03), "dollar": np.full(100, -0.05)}
    )
    eq = fc.equivalences(0.6, draws)
    assert eq.loc["10Y Treasury yield", "central"] == pytest.approx(100)  # +100bp
    assert eq.loc["Equity prices (S&P 500)", "central"] == pytest.approx(-20)
    assert eq.loc["Broad dollar", "central"] == pytest.approx(12)
    assert eq["reliable"].all()


def test_projection_decays_with_unchanged_levels():
    lv, gdp, _ = _sim()
    betas = pd.Series({"policy_rate": -0.4, "y10": -0.6, "equity": 0.03, "dollar": -0.05})
    p = fc.project_fci(lv, betas, {})
    assert p.index.is_unique
    assert abs(p.iloc[-1]) < 1e-9  # all 4-quarter changes are zero after a year


def test_index_comparison_percentiles():
    s = pd.Series(np.arange(100.0), index=pd.date_range("2000", periods=100, freq="MS"))
    t = fc.index_comparison({"a": s})
    assert t.loc["a", "percentile"] == pytest.approx(99)
    assert t.loc["a", "verdict"] == "tighter than usual"
