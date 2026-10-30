"""Backtests against the market, the forecast book, signposts, carry and Student-t scenarios."""

import numpy as np
import pandas as pd
import pytest

from macro import backtest as bt
from macro import forecast_book as fb
from macro import markets as mk
from macro import signposts as sp
from macro import stress_test as stt

IDX = pd.date_range("1980-01-01", periods=480, freq="MS")


# ------------------------------------------------------------------ backtest
def test_encompassing_detects_information_and_its_absence():
    g = np.random.default_rng(0)
    truth = pd.Series(g.normal(0, 1, 400))
    bench = truth + g.normal(0, 1, 400)
    informed = truth + g.normal(0, 1, 400)  # independent errors: carries information
    noise = bench + g.normal(0, 1, 400)  # benchmark plus noise: carries none
    e1 = bt.encompassing(truth, informed, bench, h=1)
    e2 = bt.encompassing(truth, noise, bench, h=1)
    assert e1["slope b"] == pytest.approx(0.5, abs=0.12) and e1["p (b > 0)"] < 0.01
    assert abs(e2["slope b"]) < 0.15 and e2["p (b > 0)"] > 0.05


def test_dm_test_sign_and_equal_forecasts():
    g = np.random.default_rng(1)
    small, large = g.normal(0, 1, 300), g.normal(0, 2, 300)
    st, p = bt.dm_test(small, large, h=1)
    assert st > 0 and p < 0.01
    assert np.isnan(bt.dm_test(small, small, h=1)[0])


def test_rule_forecasts_recover_a_planted_rule_without_look_ahead():
    g = np.random.default_rng(2)
    pi = pd.Series(2 + np.cumsum(g.normal(0, 0.1, len(IDX))), index=IDX)
    y = pd.Series(np.sin(np.arange(len(IDX)) / 20), index=IDX)
    i = [3.0]
    for t in range(1, len(IDX)):
        i.append(0.2 + 0.9 * i[-1] + 0.15 * pi.iloc[t] + 0.05 * y.iloc[t] + g.normal(0, 0.05))
    pan = pd.DataFrame({"i": i, "pi": pi, "y": y, "mkt": i}, index=IDX)
    rf = bt.rule_forecasts(pan, start="1995-01-01")
    assert rf["rho"].iloc[-1] == pytest.approx(0.9, abs=0.05)
    pan2 = pan.copy()
    t = rf.index[20]
    pan2.loc[t + pd.DateOffset(months=1) :, "i"] += 5  # the future changes, past forecasts must not
    rf2 = bt.rule_forecasts(pan2, start="1995-01-01")
    assert rf2.loc[t, "rule"] == pytest.approx(rf.loc[t, "rule"])


def test_disagreement_hit_rate():
    r = pd.Series([1.0, -1.0, 1.0, 0.0])
    m = pd.Series([1.0, -1.0, -1.0, 0.1])
    b = pd.Series([0.0, 0.0, 0.0, 0.0])
    h = bt.disagreement_hit_rate(r, m, b, threshold=0.5)
    assert h["cases"] == 3 and h["model side"] == pytest.approx(2 / 3)


# ------------------------------------------------------------------ forecast book
def test_forecast_book_finds_planted_momentum_and_not_noise():
    g = np.random.default_rng(3)
    w = pd.date_range("1995-01-06", periods=1500, freq="W-FRI")
    drift = np.repeat(g.choice([-1.0, 1.0], 1500 // 60 + 1), 60)[:1500] * 0.3  # persistent trends
    trend = pd.Series(100 * np.exp(np.cumsum(drift + g.normal(0, 1, 1500)) / 100), index=w)
    noise = pd.Series(100 * np.exp(np.cumsum(g.normal(0, 1, 1500)) / 100), index=w)
    res = {}
    for name, lv in (("trend", trend), ("noise", noise)):
        sig = fb.signals(lv, "price", None).dropna()
        o = fb.pseudo_oos(sig, fb.target_up(lv), start="2002-01-01").dropna(subset=["y"])
        from macro.leading import scores

        res[name] = scores(o["p"].to_numpy(), o["y"].to_numpy(), o["base rate"].to_numpy())
    assert res["trend"]["Brier skill vs base rate"] > 0.05
    assert res["noise"]["Brier skill vs base rate"] < 0.03


def test_target_and_archive_scoring(tmp_path):
    w = pd.date_range("2025-01-03", periods=30, freq="W-FRI")
    lv = pd.Series(np.arange(30, dtype=float), index=w)
    y = fb.target_up(lv)
    assert y.iloc[0] == 1.0 and y.iloc[-13:].isna().all()
    tab = pd.DataFrame({"id": ["X"], "P(higher in 13 weeks)": [0.8]}, index=["x"])
    rows = fb.archive_rows(tab, {"X": lv.iloc[:10]})
    path = tmp_path / "book.csv"
    assert fb.append_archive(path, rows) == 1 and fb.append_archive(path, rows) == 0  # once per week
    sc = fb.score_archive(pd.read_csv(path), {"X": lv})
    assert sc["outcome up"].iloc[0] == 1.0 and sc["brier"].iloc[0] == pytest.approx(0.04)


# ------------------------------------------------------------------ signposts
def test_signposts_cross_and_alert_once():
    s = pd.Series([100.0, 101.0, 103.0], index=pd.date_range("2026-01-01", periods=3, freq="MS"))
    items = [
        {
            "id": "x",
            "label": "X",
            "series": "X",
            "transform": "level",
            "op": "above",
            "threshold": 102.0,
            "unit": "",
            "meaning": "m",
        }
    ]
    ev = sp.evaluate(lambda sid: s, items)
    assert ev.loc["x", "crossed"] and ev.loc["x", "distance"] == pytest.approx(-1.0)
    assert sp.newly_crossed(ev, {}) == ["x"] and sp.newly_crossed(ev, {"x": True}) == []


def test_sahm_skips_an_unpublished_month():
    idx = pd.date_range("2024-01-01", "2026-09-01", freq="MS").drop(pd.Timestamp("2025-10-01"))
    u = pd.Series(4.0, index=idx)
    out = sp.sahm(u)
    assert out.index[-1] == pd.Timestamp("2026-09-01") and out.iloc[-1] == pytest.approx(0.0)


# ------------------------------------------------------------------ carry and Student-t
def test_carry_and_rolldown_on_a_flat_and_a_steep_curve():
    flat = mk.rates_carry_roll({0.25: 4.0, 2.0: 4.0, 10.0: 4.0}, {2.0: 80.0, 10.0: 80.0})
    assert flat["breakeven (bp)"].abs().max() < 1e-9
    steep = mk.rates_carry_roll({0.25: 3.0, 2.0: 4.0, 10.0: 5.0}, {2.0: 80.0, 10.0: 80.0})
    assert (steep["carry (bp)"] > 0).all() and (steep["roll-down (bp)"] > 0).all()
    assert steep.loc[2.0, "roll-down (bp)"] == pytest.approx(
        (4.0 - (3.0 + (4.0 - 3.0) * (1.75 - 0.25) / 1.75)) * 100
    )


def test_student_t_bands_are_wider_for_large_shocks():
    cov = pd.DataFrame([[4.0, 1.2], [1.2, 1.0]], index=["X", "S"], columns=["X", "S"])
    n_small = stt.conditional(cov, {"S": 0.1})
    t_small = stt.conditional(cov, {"S": 0.1}, nu=5)
    t_large = stt.conditional(cov, {"S": 5.0}, nu=5)
    w = lambda d: float(d.loc["X", "95% high"] - d.loc["X", "95% low"])  # noqa: E731
    assert t_small.loc["X", "expected move"] == pytest.approx(n_small.loc["X", "expected move"])
    assert w(t_large) > w(t_small)
    assert stt.tail_dof(pd.DataFrame({"a": np.random.default_rng(4).standard_t(6, 20000)})) == pytest.approx(
        6, abs=1.5
    )


def test_realtime_rule_uses_only_published_vintages():
    g = np.random.default_rng(5)
    idx = pd.date_range("1980-01-01", periods=480, freq="MS")
    pce = pd.Series(100 * np.exp(np.cumsum(g.normal(0.002, 0.001, 480))), index=idx)
    gdp = pd.Series(100 * np.exp(np.cumsum(g.normal(0.002, 0.003, 480))), index=idx).resample("QS").last()
    pot = gdp.rolling(8, min_periods=1).mean()
    dff = pd.Series(3 + np.cumsum(g.normal(0, 0.1, 480)), index=idx).clip(lower=0)
    seen: list = []

    def vintage_of(sid, date):  # a vintage dated `date` ends a month (prices) or a quarter (GDP) earlier
        s = {"PCEPILFE": pce, "GDPC1": gdp, "GDPPOT": pot}[sid]
        lag = pd.DateOffset(months=1 if sid == "PCEPILFE" else 4)
        out = s.loc[: date - lag]
        seen.append((date, out.index[-1]))
        return out

    rt = bt.rule_forecasts_realtime(dff, dff, vintage_of, start="2000-01-01")
    assert len(rt) > 200 and all(last < d for d, last in seen)
    revised = bt.rule_forecasts(bt.fed_panel(dff, pce, gdp, pot, dff), start="2000-01-01")
    common = rt.index.intersection(revised.index)
    assert np.corrcoef(rt.loc[common, "rule"], revised.loc[common, "rule"])[0, 1] > 0.9


def test_note_calls_open_right_wrong_and_early_fail():
    from macro import note_calls as nc

    idx = pd.date_range("2026-01-01", "2027-12-01", freq="MS")
    s = pd.Series(range(len(idx)), index=idx, dtype=float)
    base = {"note": "x", "statement": "s", "series": "S", "transform": "level", "made": "2026-01-01"}
    calls = [
        base | {"id": "open", "stat": "at", "op": "above", "threshold": 5, "matures": "2027-06-30"},
        base | {"id": "right", "stat": "at", "op": "above", "threshold": 5, "matures": "2026-12-31"},
        base | {"id": "wrong", "stat": "at", "op": "between", "threshold": [0, 3], "matures": "2026-12-31"},
        base
        | {
            "id": "early",
            "stat": "max",
            "op": "below",
            "threshold": 2,
            "matures": "2027-06-30",
            "withdrawn": "w",
        },
    ]
    ev = nc.evaluate(lambda sid: s, calls, today="2027-02-15")
    assert ev["status"].to_dict() == {"open": "open", "right": "right", "wrong": "wrong", "early": "wrong"}
    assert ev.loc["early", "withdrawn"] and ev.loc["right", "value"] == 11.0
    assert set(nc.evaluate(lambda sid: None, calls[:1])["status"]) == {"no data"}
