"""Operational checks: fund benchmarks, liquidity, price anomalies (mocked HTTP), model health."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from macro import fund_checks as fc
from macro import portfolio as pf
from macro.data import sources
from macro.data.http import SourceError


class FakeResp:
    def __init__(self, text=""):
        self.text = text
        self.status_code = 200


def _weekly(n=200, seed=0, mu=0.001, sd=0.02, start="2015-01-02"):
    g = np.random.default_rng(seed)
    return pd.Series(g.normal(mu, sd, n), index=pd.date_range(start, periods=n, freq="W-FRI"))


# ---------------------------------------------------------------------------- liquidity
def test_liquidity_days_and_flags():
    w = pd.Series({"SPY": 0.30, "KMLM": 0.05, "XYZ": 0.02, "BIL": 0.0})
    adv = {"SPY": 3e10, "KMLM": 5e6}
    out = fc.liquidity(w, adv, notional_usd=1e8, participation=0.1, max_days=1.0, max_share_adv=0.01)
    assert "BIL" not in out.index  # zero weights are not positions
    # SPY: 30m against 30bn a day -> 0.1% of ADV, 0.01 day at 10% participation
    assert out.loc["SPY", "days to liquidate"] == pytest.approx(0.01)
    assert out.loc["SPY", "flag"] == ""
    # KMLM: 5m against 5m a day -> 100% of ADV, 10 days
    assert out.loc["KMLM", "days to liquidate"] == pytest.approx(10.0)
    assert "day to exit" in out.loc["KMLM", "flag"] and "of ADV" in out.loc["KMLM", "flag"]
    assert out.loc["XYZ", "flag"] == "no ADV estimate"


def test_liquidity_shorts_count_by_size():
    out = fc.liquidity(pd.Series({"FXF": -0.05}), {"FXF": 5e6}, 1e8)
    assert out.loc["FXF", "position (USD m)"] == pytest.approx(5.0)
    assert out.loc["FXF", "weight"] < 0


def test_every_universe_line_has_an_adv_estimate():
    cfg = pf.load_config()
    missing = [a for a in cfg["universe"] if a not in cfg["liquidity"]["adv_usd"]]
    assert not missing


# ---------------------------------------------------------------------------- anomalies
def _prices(n=400, seed=1):
    g = np.random.default_rng(seed)
    idx = pd.bdate_range("2025-01-01", periods=n)
    mkt = g.normal(0, 0.01, n)
    a = 100 * np.exp(np.cumsum(mkt + g.normal(0, 0.003, n)))
    b = 100 * np.exp(np.cumsum(mkt + g.normal(0, 0.003, n)))
    return pd.DataFrame({"A": a, "PROXY": b}, index=idx)


def test_jump_without_proxy_move_is_flagged():
    px = _prices()
    px.iloc[-2:, 0] *= 1.25  # a bad print on A two days ago, the proxy flat
    out = fc.price_jumps(px, {"A": "PROXY"}, k=6.0, last_days=5)
    assert list(out["asset"]) == ["A"]
    assert out.iloc[0]["date"] == px.index[-2]
    assert out.iloc[0]["move"] == pytest.approx(0.25, abs=0.05)


def test_jump_shared_by_proxy_is_a_market_move():
    px = _prices()
    px.iloc[-2:, :] *= 0.75  # both fall 25%: a crash, not a data error
    out = fc.price_jumps(px, {"A": "PROXY", "PROXY": "A"}, k=6.0, last_days=5)
    assert out.empty


def test_no_jump_on_ordinary_days():
    assert fc.price_jumps(_prices(), {"A": "PROXY"}).empty


def test_source_mismatch_same_day_only():
    d = pd.Timestamp("2026-11-16")
    prim = {"SPY": (d, 600.0), "TLT": (d, 90.0), "GLD": (d, 300.0)}
    sec = {"SPY": (d, 601.0), "TLT": (d, 95.0), "GLD": (d - pd.Timedelta(days=1), 250.0)}
    out = fc.source_mismatches(prim, sec, tol=0.02)
    assert list(out["asset"]) == ["TLT"]  # SPY within 2%; GLD's second close is from another day


def test_append_anomalies_dedupes(tmp_path):
    p = tmp_path / "an.csv"
    d = pd.Timestamp("2026-11-16")
    df = fc.source_mismatches({"TLT": (d, 90.0)}, {"TLT": (d, 95.0)})
    assert len(fc.append_anomalies(df, p)) == 1
    assert fc.append_anomalies(df, p).empty
    assert len(fc.read_anomalies(p)) == 1


def test_stooq_symbol():
    assert sources.stooq_symbol("SPY") == "spy.us"
    assert sources.stooq_symbol("000660.KS") is None
    assert sources.stooq_symbol("KRW=X") is None
    assert sources.stooq_symbol("^SOX") is None


def test_stooq_daily_parses_csv():
    csv = "Date,Open,High,Low,Close,Volume\n2026-11-13,598,602,597,600.5,1000\n2026-11-16,601,605,600,603.25,1200\n"
    with patch.object(sources, "get", return_value=FakeResp(csv)) as g:
        s = sources.stooq_daily("spy.us")
    assert g.call_args.args[1]["s"] == "spy.us"
    assert s.loc["2026-11-16"] == pytest.approx(603.25)


def test_stooq_bad_payload():
    with (
        patch.object(sources, "get", return_value=FakeResp("No data")),
        pytest.raises(SourceError),
    ):
        sources.stooq_daily("spy.us")


# ---------------------------------------------------------------------------- fund benchmarks
def test_fund_benchmarks_common_window():
    model, bench, cash = _weekly(300, 1), _weekly(300, 2), pd.Series(0.0005, index=_weekly(300).index)
    young = _weekly(120, 3, start=str(model.index[180].date()))
    tiny = _weekly(20, 4, start=str(model.index[280].date()))
    t = fc.fund_benchmarks(model, bench, cash, {"RPAR": young, "TINY": tiny}, pf.metrics)
    assert "TINY" not in t.columns  # under a year: left out rather than shortening the window
    assert t.loc["weeks", "our model"] == 120
    assert t.loc["first week", "RPAR"] == str(young.index[0].date())
    assert "beta to benchmark" in t.index


def test_fund_benchmarks_empty_without_funds():
    s = _weekly(100)
    assert fc.fund_benchmarks(s, s, s * 0, {}, pf.metrics).empty


# ---------------------------------------------------------------------------- model health
def test_weight_turnover_and_vol_ratio():
    idx = pd.date_range("2015-01-02", periods=300, freq="W-FRI")
    g = np.random.default_rng(5)
    r = pd.DataFrame({"X": g.normal(0, 0.02, 300), "Y": g.normal(0, 0.01, 300)}, index=idx)
    w = pd.DataFrame({"X": 0.5, "Y": 0.5}, index=idx)
    w.iloc[100:, 0], w.iloc[100:, 1] = 0.6, 0.4
    turn = fc.weight_turnover(w)
    assert turn.max() == pytest.approx(0.2) and (turn > 0).sum() == 1
    ret = (r * w.shift(1).bfill()).sum(axis=1)
    pvr = fc.predicted_vs_realised(w, r, ret)
    assert 0.7 < pvr["ratio"].median() < 1.4  # same process before and after: roughly calibrated


def test_binding_constraints_detects_caps():
    cfg = pf.load_config()
    w = pd.Series({"SPY": 0.5, "HYNIX": 0.075, "SAMSUNG": 0.075, "IEF": 0.35})
    risk = {"volatility": 0.12, "benchmark volatility": 0.10, "tracking error": 0.03}
    bc = fc.binding_constraints(w, cfg, risk).set_index("limit")
    assert bc.loc["semiconductors net max", "binding"]  # 15% = the cap
    assert bc.loc["volatility cap", "binding"]  # above the benchmark's volatility
    assert not bc.loc["tracking error", "binding"]


def test_paper_vs_backtest():
    idx = pd.date_range("2026-11-20", periods=6, freq="W-FRI")
    bt = pd.Series([0.01, -0.005, 0.002, 0.003, -0.001, 0.004], index=idx)
    nav = (1 + bt).cumprod()
    nav = pd.concat([pd.Series([1.0], index=[idx[0] - pd.Timedelta(days=7)]), nav])
    out = fc.paper_vs_backtest(nav, bt)
    assert out["weeks"] == 6
    assert out["tracking difference (annualised)"] == pytest.approx(0.0, abs=1e-12)
    assert fc.paper_vs_backtest(pd.Series(dtype=float), bt) == {}
