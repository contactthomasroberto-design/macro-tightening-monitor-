"""Cross-asset analytics recover planted values (src/macro/markets.py)."""

import numpy as np
import pandas as pd
import pytest

from macro import markets as mk

IDX = pd.bdate_range("2010-01-01", "2025-12-31")


def _walk(sd, seed, start=100.0, log=True):
    e = np.random.default_rng(seed).normal(0, sd, len(IDX))
    return pd.Series(start * np.exp(np.cumsum(e)) if log else start + np.cumsum(e), index=IDX)


def test_units_of_moves():
    s = pd.Series([4.00, 4.10], index=IDX[:2])
    assert mk.change(s, "yield", 1).iloc[-1] == pytest.approx(10.0)
    assert mk.change(s, "spread", 1).iloc[-1] == pytest.approx(10.0)
    assert mk.change(pd.Series([100.0, 110.0]), "price", 1).iloc[-1] == pytest.approx(100 * np.log(1.1))
    assert mk.change(pd.Series([15.0, 18.0]), "vol", 1).iloc[-1] == pytest.approx(3.0)
    with pytest.raises(ValueError):
        mk.change(s, "other")


def test_business_daily_fills_holidays_but_not_beyond_the_end():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2025-01-02", "2025-01-06"]))
    bd = mk.business_daily(s)
    assert bd.index[-1] == pd.Timestamp("2025-01-06") and bd.loc["2025-01-03"] == 1.0


def test_move_zscore_and_realised_vol_recover_the_planted_volatility():
    sd = 0.01  # 1% daily
    s = _walk(sd, 1)
    assert mk.realized_vol(s, "price", 252 * 5).iloc[-1] == pytest.approx(100 * sd * np.sqrt(252), rel=0.05)
    # plant a final 21-day move of exactly 2 standard deviations of 21-day moves
    move = 2 * sd * np.sqrt(21)
    s2 = s.copy()
    s2.iloc[-21:] = s.iloc[-22] * np.exp(np.linspace(move / 21, move, 21))
    assert mk.move_zscore(s2, "price", 21) == pytest.approx(2.0, rel=0.12)


def test_percentile_of_last():
    s = pd.Series(np.arange(100.0), index=pd.date_range("2016-01-01", periods=100, freq="MS"))
    assert mk.percentile_of_last(s, 30) == 100.0
    assert mk.percentile_of_last(s.iloc[::-1].set_axis(s.index), 30) == pytest.approx(1.0)


def test_stress_index_is_the_average_z_and_carries_late_components():
    a = _walk(0.5, 2, 20, log=False)
    st = mk.stress_index({"A": a, "B": a.copy()}, window=500, min_days=250)
    z = mk.rolling_z(a, 500, 250).dropna()
    assert st.value.loc[z.index[-1]] == pytest.approx(z.iloc[-1])
    late = {"A": a, "B": a.iloc[:-2]}  # B published two days later
    st2 = mk.stress_index(late, window=500, min_days=250)
    assert st2.value.index[-1] == a.index[-1] and st2.extra["contributions"].notna().all()


def test_benchmark_correlation_of_a_series_with_itself():
    s = _walk(0.5, 3, 0, log=False)
    tab = mk.benchmark_correlations(s, {"same": s})
    assert tab.loc["same", "corr (levels)"] == pytest.approx(1.0)


def test_quadrant_regimes_and_spells():
    eq = pd.Series(np.exp(np.linspace(0, 1, len(IDX))), index=IDX)  # always up
    y_down = pd.Series(np.linspace(5, 1, len(IDX)), index=IDX)
    y_up = pd.Series(np.linspace(1, 5, len(IDX)), index=IDX)
    assert set(mk.quadrant_regimes(eq, y_down)) == {"Goldilocks"}
    assert set(mk.quadrant_regimes(eq, y_up)) == {"Reflation"}
    assert set(mk.quadrant_regimes(eq.iloc[::-1].set_axis(IDX), y_up)) == {"Rates shock"}
    sp = mk.regime_spells(mk.quadrant_regimes(eq, y_up))
    assert sp["current"] == "Reflation" and sp["share"]["Reflation"] == 1.0


def test_forward_moves_use_effective_sample_size():
    eq = _walk(0.01, 4)
    y = _walk(0.05, 5, 3, log=False)
    reg = mk.quadrant_regimes(eq, y)
    fwd = mk.regime_forward_moves(reg, {"eq": (eq, "price")})
    r = fwd.iloc[0]
    assert r["independent windows"] == pytest.approx(r["days"] / 21, rel=0.01)
    assert abs(fwd["t-stat"]).max() < 4  # a random walk has no regime premium


def test_stock_bond_sign_convention():
    eq = _walk(0.01, 6)
    y = pd.Series(3 - 0.5 * np.log(eq.values / 100.0), index=IDX)  # yields fall when equities rise
    c = mk.rolling_correlation(eq, "price", y, "yield", 63, 1, -1)  # bond return = -dy
    assert c.iloc[-1] == pytest.approx(1.0, abs=1e-6)  # stocks and bonds rise together


def test_change_beta_recovers_a_planted_weekly_sensitivity():
    rng = np.random.default_rng(7)
    x = pd.Series(3 + np.cumsum(rng.normal(0, 0.03, len(IDX))), index=IDX)  # yield, %
    beta = 0.02  # % per bp
    noise = rng.normal(0, 0.15, len(IDX))
    y = pd.Series(100 * np.exp((beta * x * 100 + np.cumsum(noise) * 0.1) / 100), index=IDX)
    r = mk.change_beta(y, "price", x, "yield", window=520)
    assert r.value == pytest.approx(beta, rel=0.15)
    assert r.lower < beta < r.upper
    e = r.extra
    assert e["explained"] + e["residual"] == pytest.approx(e["actual"])


def test_curve_probit_recovers_planted_coefficients():
    rng = np.random.default_rng(8)
    months = pd.date_range("1960-01-01", "2025-12-01", freq="MS")
    spread = pd.Series(1.0 + np.cumsum(rng.normal(0, 0.3, len(months))) * 0.2, index=months)
    spread = spread - spread.mean() + 1.0
    from scipy.stats import norm

    p = norm.cdf(-1.0 - 0.6 * spread.to_numpy())
    rec = pd.Series((rng.random(len(months)) < p).astype(float), index=months).shift(12)  # outcome 12m later
    r = mk.curve_recession_probit(spread, rec.dropna())
    assert r.extra["b"] == pytest.approx(-0.6, abs=0.2)
    assert r.extra["a"] == pytest.approx(-1.0, abs=0.25)
    assert 0.5 < r.extra["auc"] <= 1.0
    assert r.extra["target_month"] == months[-1] + pd.DateOffset(months=12)


def test_dashboard_rows_and_staleness():
    a = mk.Asset("Y", "Yield", "Rates", "yield", 0)
    p = mk.Asset("P", "Price", "Equities", "price", -1)
    y = pd.Series(np.linspace(3, 4, len(IDX)), index=IDX)
    px = _walk(0.01, 9).iloc[:-5]  # five business days behind
    d = mk.dashboard({"Y": y, "P": px}, [a, p])
    assert d.loc["Yield", "last"] == pytest.approx(4.0) and d.loc["Yield", "unit"] == "bp"
    assert d.loc["Price", "stale_bdays"] == 5 and d.loc["Yield", "stale_bdays"] == 0
    ytd = (4.0 - y.loc[:"2024-12-31"].iloc[-1]) * 100
    assert d.loc["Yield", "YTD"] == pytest.approx(ytd)
