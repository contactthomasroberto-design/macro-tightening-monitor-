"""Planted-parameter tests: each estimator recovers known parameters from simulated data."""

import numpy as np
import pandas as pd
import pytest

from macro import inflation as inf

IDX = pd.date_range("1980-01-01", periods=600, freq="MS")


def _ar(phis, n=600, sd=1.0, seed=1):
    g = np.random.default_rng(seed)
    y = np.zeros(n)
    for t in range(len(phis), n):
        y[t] = 0.5 + sum(p * y[t - 1 - j] for j, p in enumerate(phis)) + g.normal(0, sd)
    return pd.Series(y, index=IDX[:n])


def test_persistence_recovers_sum_of_ar_coefficients():
    r = inf.persistence(_ar([0.5, 0.3]), max_p=6, window=240)
    assert r.extra["p"] == 2
    assert r.lower < 0.8 < r.upper
    assert abs(r.value - 0.8) < 0.06


def test_half_life_ar1():
    assert inf.half_life(np.array([0.9])) == 7  # 0.9^7 = 0.478 < 0.5 <= 0.9^6


def test_energy_passthrough_recovers_cumulative_effect():
    g = np.random.default_rng(2)
    oil = pd.Series(100 * np.exp(np.cumsum(g.normal(0, 0.08, 600))), index=IDX)
    doil = inf.log_change(oil)
    gap = 0.02 * doil + 0.01 * doil.shift(1) + 0.005 * doil.shift(2) + g.normal(0, 0.05, 600)
    core = pd.Series(100 * np.exp(np.cumsum(np.full(600, 0.002))), index=IDX)
    headline = core * np.exp(gap.fillna(0).cumsum() / 100)
    r = inf.energy_passthrough(pd.DataFrame({"headline": headline, "core": core, "oil": oil}), lags=6)
    assert r.lower < 0.035 < r.upper
    assert r.extra["table"].loc["full", "n"] > 500


def test_local_projection_recovers_cumulative_response():
    g = np.random.default_rng(3)
    shock = pd.Series(g.normal(0, 1, 600), index=IDX)
    dly = 0.3 * shock + 0.2 * shock.shift(1).fillna(0) + g.normal(0, 0.2, 600)
    y = pd.Series(100 * np.exp(np.cumsum(dly) / 100), index=IDX)
    lp = inf.local_projection(y, shock, horizons=4, n_lags=2)
    assert lp.loc[0, "lower"] < 0.3 < lp.loc[0, "upper"]
    assert lp.loc[3, "lower"] < 0.5 < lp.loc[3, "upper"]


def test_expectations_factor_recovers_common_component():
    g = np.random.default_rng(4)
    f = np.cumsum(g.normal(0, 0.05, 300)) + 2.5
    idx = pd.date_range("2000-01-01", periods=300, freq="MS")
    exp = pd.DataFrame(
        {
            "SPF_CPI10": f + g.normal(0, 0.02, 300),
            "T5YIFR": 0.9 * f + 0.3 + g.normal(0, 0.05, 300),
            "MICH": 1.2 * f + g.normal(0, 0.1, 300),
            "T10YIE": f - 0.2 + g.normal(0, 0.05, 300),
        },
        index=idx,
    )
    r = inf.expectations_factor(exp, pd.Series(f, index=idx), window=60)
    assert np.corrcoef(r.value, f)[0, 1] > 0.97
    assert (r.extra["loadings"] > 0).all()
    assert r.extra["explained_share"] > 0.8


def test_momentum_annualisation():
    s = pd.Series(100 * 1.01 ** np.arange(24), index=pd.date_range("2020-01-01", periods=24, freq="MS"))
    m = inf.momentum(s).iloc[-1]
    assert m["1m ann."] == pytest.approx(100 * (1.01**12 - 1))
    assert m["yoy"] == pytest.approx(100 * (1.01**12 - 1))


def test_prob_exceed():
    assert inf.prob_exceed(2.0, 1.0, 2.0) == pytest.approx(0.5)
    assert inf.prob_exceed(3.0, 1.0, 2.0) == pytest.approx(0.8413, abs=1e-3)
    assert np.isnan(inf.prob_exceed(3.0, np.nan, 2.0))


def test_realtime_value_respects_release_lag():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2020-01-01", "2020-02-01"]))
    info = pd.DatetimeIndex(["2020-03-05", "2020-03-20"])
    v = inf.realtime_value(s, "M", 15, info)
    assert v.tolist() == [1.0, 2.0]  # Feb data published Mar 15
