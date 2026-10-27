import numpy as np
import pandas as pd
import pytest

from macro import curves as cv

IDX = pd.bdate_range("2020-01-01", periods=60)


def test_spreads_formulas():
    y = pd.DataFrame({"3m": [5.0], "2y": [4.5], "5y": [4.2], "10y": [4.0], "30y": [4.3]})
    s = cv.us_spreads(y).iloc[0]
    assert s["3m10y"] == pytest.approx(-100)
    assert s["2s10s"] == pytest.approx(-50)
    assert s["5s30s"] == pytest.approx(10)
    assert s["2s5s10s fly"] == pytest.approx(-10)


@pytest.mark.parametrize(
    ("d2", "d10", "expected"),
    [
        (-0.30, -0.10, "bull steepener"),
        (0.10, 0.30, "bear steepener"),
        (-0.10, -0.30, "bull flattener"),
        (0.30, 0.10, "bear flattener"),
        (0.01, 0.01, "range-bound"),
    ],
)
def test_regime_classification(d2, d10, expected):
    y2 = pd.Series(np.linspace(3, 3 + d2, 60), index=IDX)
    y10 = pd.Series(np.linspace(4, 4 + d10, 60), index=IDX)
    assert cv.classify_regime(y2, y10, window=21)["regime"].iloc[-1] == expected


def test_sovereign_stress_flags_spike():
    g = np.random.default_rng(0)
    idx = pd.date_range("2000-01-01", periods=200, freq="MS")
    s = pd.DataFrame({"BTP-Bund": 150 + g.normal(0, 10, 200)}, index=idx)
    s.iloc[-1] = 400
    out = cv.sovereign_stress(s)
    assert bool(out["latest"].loc["BTP-Bund", "level flag"])
    assert not bool(out["flag"].iloc[100, 0])


def test_duration_factor_recovers_common_share():
    g = np.random.default_rng(1)
    n = 300
    f = g.normal(0, 1, n)
    d = pd.DataFrame(
        {c: f + g.normal(0, 0.3, n) for c in "ABCDE"}, index=pd.date_range("1990", periods=n, freq="MS")
    )
    r = cv.duration_factor(d.cumsum(), window=60)
    assert r.value > 0.85
    assert (r.extra["loadings"] > 0).all()


def test_ten_year_decomposition_identity():
    y10 = pd.Series([4.0, 4.1], index=IDX[:2])
    out = cv.ten_year_decompositions(
        y10, y10 - 2.0, pd.Series([2.0, 2.0], index=IDX[:2]), {"KW": y10 * 0 + 0.5}
    )
    assert np.allclose(out["real_be"]["residual"], 0)
    assert np.allclose(out["tp"]["KW"]["expected short rate"], [3.5, 3.6])
