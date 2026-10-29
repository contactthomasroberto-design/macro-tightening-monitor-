"""Recession signal suite (macro.leading) and cross-asset stress testing (macro.stress_test)."""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from macro import leading as ld
from macro import stress_test as stt

MONTHS = pd.date_range("1970-01-01", "2025-12-01", freq="MS")


# ------------------------------------------------------------------ leading
def test_near_term_forward_spread_formula():
    idx = pd.bdate_range("2024-01-01", "2024-03-29")
    c = lambda v: pd.Series(v, index=idx)  # noqa: E731
    X = ld.features(c(4.0), c(5.0), c(4.5), c(4.8), pd.Series([0.1], index=[idx[0]]))
    assert X["spread"].iloc[0] == pytest.approx(-1.0)
    assert X["ntfs"].iloc[0] == pytest.approx(2 * 4.5 - 4.8 - 5.0)  # 1y forward 1y ahead minus 3M


def test_target_is_a_recession_in_the_next_12_months_and_unknown_at_the_end():
    rec = pd.Series(0.0, index=MONTHS[:60])
    rec.iloc[30] = 1.0
    y = ld.target_within(rec)
    assert y.iloc[18] == 1.0 and y.iloc[17] == 0.0 and y.iloc[29] == 1.0 and y.iloc[30] == 0.0
    assert y.iloc[-12:].isna().all()


def _planted(seed=0, a=-1.0, b=-0.8):
    g = np.random.default_rng(seed)
    x = pd.Series(np.cumsum(g.normal(0, 0.3, len(MONTHS))) * 0.3 + 1.0, index=MONTHS)
    x = x - x.mean() + 1.0
    y = pd.Series((g.random(len(MONTHS)) < norm.cdf(a + b * x.to_numpy())).astype(float), index=MONTHS)
    return pd.DataFrame({"spread": x}), y


def test_pseudo_oos_uses_only_known_outcomes():
    X, y = _planted()
    base = ld.pseudo_oos(X, y, ["spread"], start="2000-01-01")
    t = base.index[50]
    y2 = y.copy()
    y2.loc[t - pd.DateOffset(months=11) :] = 1 - y2.loc[t - pd.DateOffset(months=11) :]  # unknown at t
    alt = ld.pseudo_oos(X, y2, ["spread"], start="2000-01-01")
    assert alt.loc[t, "p"] == pytest.approx(base.loc[t, "p"])


def test_suite_recovers_planted_probit_and_beats_the_base_rate():
    X, y = _planted()
    X["ntfs"] = X["spread"]
    X["ebp"] = np.random.default_rng(1).normal(0, 1, len(X))  # pure noise
    r = ld.suite(X, y, start="1990-01-01")
    tab = r["table"]
    assert tab.loc["10Y-3M spread", "AUC"] > 0.6
    assert tab.loc["10Y-3M spread", "Brier skill vs base rate"] > 0
    assert tab.loc["Excess bond premium", "AUC"] < tab.loc["10Y-3M spread", "AUC"]
    fit = r["fits"]["10Y-3M spread"]
    assert fit.params["spread"] == pytest.approx(-0.8, abs=0.2)
    assert fit.params["const"] == pytest.approx(-1.0, abs=0.25)


def test_scores_on_perfect_and_base_rate_forecasts():
    y = np.array([0, 0, 1, 1, 0, 1], float)
    s = ld.scores(y.copy(), y, np.full(6, 0.5))
    assert s["AUC"] == 1.0 and s["Brier"] == 0.0 and s["Brier skill vs base rate"] == 1.0
    s2 = ld.scores(np.full(6, 0.5), y, np.full(6, 0.5))
    assert s2["Brier skill vs base rate"] == pytest.approx(0.0)


# ------------------------------------------------------------------ stress testing
def _cov(r=0.6, sx=2.0, ss=1.0):
    return pd.DataFrame([[sx**2, r * sx * ss], [r * sx * ss, ss**2]], index=["X", "S"], columns=["X", "S"])


def test_conditional_normal_recovers_the_textbook_formula():
    cd = stt.conditional(_cov(), {"S": 1.5}, h_weeks=4)
    mean = 0.6 * 2.0 / 1.0 * 1.5  # rho * sx / ss * s (scaling cancels in the mean)
    sd = 2.0 * np.sqrt(4) * np.sqrt(1 - 0.36)
    assert cd.loc["X", "expected move"] == pytest.approx(mean)
    assert cd.loc["X", "68% high"] - cd.loc["X", "expected move"] == pytest.approx(sd)
    assert cd.loc["X", "share of risk explained"] == pytest.approx(0.36)


def test_nearest_psd_repairs_an_invalid_matrix():
    bad = pd.DataFrame(
        [[1, 0.9, -0.9], [0.9, 1, 0.9], [-0.9, 0.9, 1]], index=list("abc"), columns=list("abc")
    )
    assert np.linalg.eigvalsh(bad.to_numpy()).min() < 0
    assert np.linalg.eigvalsh(stt.nearest_psd(bad).to_numpy()).min() >= 0


def _weekly(n=900, seed=3):
    g = np.random.default_rng(seed)
    f = g.normal(0, 1, n)
    idx = pd.date_range("2005-01-07", periods=n, freq="W-FRI")
    load = {"SPX": 2.0, "DGS10": -5.0, "A": 1.0, "B": -0.5, "C": 0.0}
    return pd.DataFrame({k: lo * f + g.normal(0, 1, n) for k, lo in load.items()}, index=idx)


def test_coverage_is_calibrated_when_the_model_is_true():
    cov = stt.coverage_backtest(_weekly(), start="2008-01-01")
    p = cov["pooled"]
    assert 0.63 < p["inside ±1 s.d."] < 0.73
    assert 0.92 < p["inside ±1.96 s.d."] < 0.98


def test_pca_finds_the_planted_common_factor():
    f = stt.pca_factors(_weekly(n=520), years=9)
    load = f["loadings"]["Factor 1"]
    assert load["SPX"] > 0 and load["DGS10"] < 0 and abs(load["C"]) < 0.2
    assert f["explained"].iloc[0] > 0.4 and f["stability"].iloc[0] > 0.95


def test_episode_moves_and_analog_similarity():
    idx = pd.bdate_range("2019-01-01", "2021-12-31")
    up = pd.Series(np.linspace(100, 200, len(idx)), index=idx)
    y = pd.Series(np.linspace(2, 1, len(idx)), index=idx)
    ep = [("test", "2020-01-02", "2020-06-30", "planted")]
    mv = stt.episode_moves({"P": up, "Y": y}, {"P": "price", "Y": "yield"}, ep)
    assert mv.loc["P", "test"] > 0 and mv.loc["Y", "test"] < 0
    W = pd.DataFrame(
        {
            k: np.r_[np.random.default_rng(0).normal(0, 1, 100), np.full(13, s)]
            for k, s in (("a", 1.0), ("b", -1.0), ("c", 0.5), ("d", -0.5))
        },
        index=pd.date_range("2018-01-05", periods=113, freq="W-FRI"),
    )
    moves = pd.DataFrame({"same": W.iloc[-13:].sum()})
    an = stt.analogs(W, moves, [("same", "2020-01-03", "2020-04-03", "x")], min_assets=4)
    assert an.loc["same", "similarity (correlation)"] == pytest.approx(1.0)
