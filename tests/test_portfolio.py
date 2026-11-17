"""Systematic portfolio: risk model, Black-Litterman, constraints, overlay, backtest hygiene."""

import copy

import numpy as np
import pandas as pd
import pytest

from macro import portfolio as pf

CFG = pf.load_config()
W = pd.date_range("2000-01-07", periods=900, freq="W-FRI")


def _returns(seed=0, n=900):
    g = np.random.default_rng(seed)
    f_eq, f_dur = g.normal(0.0015, 0.022, n), g.normal(0.0005, 0.008, n)
    cols = {}
    for a, c in CFG["universe"].items():
        b_eq = {"equity": 1.0, "semis": 1.4, "bond": -0.1, "real": 0.3, "cash": 0.0}[c["sleeve"]]
        b_d = {"bond": 1.0, "cash": 0.0}.get(c["sleeve"], 0.0)
        sd = {"cash": 0.0002, "bond": 0.003}.get(c["sleeve"], 0.012)
        cols[a] = b_eq * f_eq + b_d * f_dur + g.normal(0, sd, n)
    for a in ("ACWI", "EFA"):
        cols[a] = f_eq + g.normal(0, 0.003, n)
    return pd.DataFrame(cols, index=W)


def test_ledoit_wolf_shrinks_noise_towards_identity():
    g = np.random.default_rng(1)
    x = g.normal(size=(60, 30))  # true correlation = identity, few observations
    c, delta = pf.ledoit_wolf_corr(x)
    sample = np.corrcoef(x.T)
    off = ~np.eye(30, dtype=bool)
    assert 0 < delta <= 1 and np.abs(c[off]).mean() < np.abs(sample[off]).mean()
    assert np.allclose(np.diag(c), 1) and np.all(np.linalg.eigvalsh(c) > 0)


def test_black_litterman_without_views_returns_equilibrium():
    r = _returns()
    cov = pf.covariance(r[list(CFG["universe"])], 156, 52)
    w_eq = pf.equilibrium_weights(list(cov.index), CFG)
    mu, pi = pf.black_litterman(cov, w_eq, {}, CFG)
    assert np.allclose(mu, pi)
    # unconstrained mean-variance on π gives back the equilibrium weights
    w = np.linalg.solve(CFG["model"]["risk_aversion"] * cov.to_numpy(), pi.to_numpy())
    assert np.allclose(w, w_eq.to_numpy(), atol=1e-8)


def test_a_positive_view_raises_that_asset_only_in_its_direction():
    r = _returns()
    cov = pf.covariance(r[list(CFG["universe"])], 156, 52)
    w_eq = pf.equilibrium_weights(list(cov.index), CFG)
    mu, pi = pf.black_litterman(cov, w_eq, {"trend": pd.Series({"GLD": 1.0})}, CFG)
    assert mu["GLD"] > pi["GLD"]
    w0, _ = pf.optimise(pi, cov, w_eq, CFG)
    w1, _ = pf.optimise(mu, cov, w_eq, CFG)
    assert w1["GLD"] > w0["GLD"]


def test_optimiser_respects_every_constraint():
    r = _returns(2)
    cov = pf.covariance(r[list(CFG["universe"])], 156, 52)
    w_eq = pf.equilibrium_weights(list(cov.index), CFG)
    bull = pd.Series(0.5, index=cov.index)  # absurdly high expected returns everywhere
    w, status = pf.optimise(bull, cov, w_eq, CFG)
    uni = CFG["universe"]
    semis = sum(w[a] for a in w.index if uni[a]["sleeve"] == "semis")
    eq = sum(w[a] for a in w.index if uni[a]["sleeve"] in ("equity", "semis"))
    vol = float(np.sqrt(w @ cov @ w))
    vol_b = float(np.sqrt(w_eq @ cov @ w_eq))
    assert status == "optimal" and w.sum() == pytest.approx(1)
    assert all(w[a] <= uni[a]["max"] + 1e-6 and w[a] >= uni[a].get("min", 0) - 1e-6 for a in w.index)
    assert 0.05 - 1e-6 <= semis <= 0.15 + 1e-6 and abs(eq - 0.6) <= 0.15 + 1e-6
    assert vol <= vol_b * (1 + 1e-4)


def test_overlay_engages_and_releases_with_hysteresis():
    s = 0
    s = pf.overlay_scale(0.09, s, CFG)
    assert s == 1 and pf.scale_of(s, CFG) == 0.75
    s = pf.overlay_scale(0.16, s, CFG)
    assert s == 2
    s = pf.overlay_scale(0.06, s, CFG)  # below half of 15%: release level 2, not level 1
    assert s == 1
    assert pf.overlay_scale(0.03, s, CFG) == 0


def test_band_skips_small_trades_and_keeps_full_investment():
    tgt = pd.Series({"SPY": 0.502, "AGG": 0.40, "BIL": 0.098})
    cur = pd.Series({"SPY": 0.50, "AGG": 0.38, "BIL": 0.12})
    out = pf.apply_band(tgt, cur, 0.005)
    assert out["SPY"] == pytest.approx(cur["SPY"], abs=1e-3) and out["AGG"] > cur["AGG"]
    assert out.sum() == pytest.approx(1)


def test_target_uses_no_future_data():
    r = _returns(3)
    inp = pf.Inputs(r=r, macro=pd.DataFrame())
    t = r.index[400]
    a = pf.target_at(inp, t, CFG)["weights"]
    r2 = r.copy()
    r2.loc[r.index[401] :] += 0.05  # change the future
    b = pf.target_at(pf.Inputs(r=r2, macro=pd.DataFrame()), t, CFG)["weights"]
    pd.testing.assert_series_equal(a, b)


def test_backtest_runs_and_costs_reduce_returns():
    r = _returns(4)
    inp = pf.Inputs(r=r, macro=pd.DataFrame())
    bt = pf.backtest(inp, CFG, start=str(r.index[200].date()))
    free = copy.deepcopy(CFG)
    for a in free["universe"].values():
        a["cost_bp"] = 0
    bt0 = pf.backtest(inp, free, start=str(r.index[200].date()))
    assert len(bt["returns"]) == len(r) - 201 and (bt["log"]["status"] != "fallback: equilibrium").all()
    assert (1 + bt["returns"]).prod() < (1 + bt0["returns"]).prod()
    assert bt["weights"].sum(axis=1).round(6).eq(1).all()


def test_memory_cycle_turns_with_revenue_acceleration():
    q = pd.date_range("2015-03-31", periods=16, freq="QE")
    rev = pd.Series([100.0] * 8 + [100, 110, 125, 145, 170, 200, 235, 275], index=q)
    m = pf.memory_cycle(rev)
    assert m.iloc[-1] > 0 and m.iloc[0] == 0


def test_macro_factors_are_lagged_for_publication():
    idx = pd.date_range("2000-01-01", periods=120, freq="MS")
    ebp = pd.Series(
        np.r_[np.random.default_rng(7).normal(0, 0.1, 119), 5.0], index=idx
    )  # spike in the last month
    f = pf.macro_factors(ebp, None, None)
    last_obs = idx[-1]
    assert f.loc[: last_obs + pd.DateOffset(months=1) - pd.Timedelta(days=2), "recession"].iloc[-1] < 0.5
    assert f["recession"].iloc[-1] > 0.5


def test_deflated_sharpe_penalises_many_trials():
    g = np.random.default_rng(5)
    r = pd.Series(g.normal(0.002, 0.02, 800))
    few = pf.deflated_sharpe(r, [0.05, 0.06])
    many = pf.deflated_sharpe(r, list(g.normal(0.05, 0.05, 200)))
    assert few > many
    assert pf.deflated_sharpe(pd.Series(g.normal(0, 0.02, 800)), list(g.normal(0, 0.05, 50))) < 0.5


def test_information_coefficient_detects_signal():
    g = np.random.default_rng(6)
    s = pd.Series(g.normal(size=200))
    ic = pf.information_coefficient(s, 0.5 * s + g.normal(size=200))
    assert ic["IC"] > 0.3 and ic["t"] > 4


# ------------------------------------------------------------------ paper book
def test_paper_book_nav_trades_and_monitor(tmp_path):
    from macro import portfolio_live as pl

    d = pd.bdate_range("2026-11-20", periods=30)
    px = pd.DataFrame({"SPY": np.linspace(100, 110, 30), "AGG": np.linspace(100, 100, 30)}, index=d)
    path = tmp_path / "book.csv"
    w = pd.Series({"SPY": 0.5, "AGG": 0.5})
    assert pl.append_book(path, d[0], w, "optimal", 0, "first paper rebalance", "0.1.0") == 2
    assert pl.append_book(path, d[0], w, "optimal", 0, "x", "0.1.0") == 0  # once per date
    book = pl.read_book(path)
    nav, drifted = pl.paper_nav(book, px)
    assert nav.iloc[-1] == pytest.approx(0.5 * 1.1 + 0.5) and drifted["SPY"] > 0.5
    tr = pl.trades(w, drifted, 0.005)
    assert tr.loc["SPY", "action"] == "sell" and tr.loc["AGG", "action"] == "buy"
    st = pl.monitor(book, px, {"SPY": 110 * 0.9, "AGG": 100.0}, CFG)  # SPY −10% today
    assert st["status"] == "breach" and st["day"] < -0.03
    assert pl.monitor(book, px, {"SPY": 110.0, "AGG": 100.0}, CFG)["status"] == "ok"


def test_rebalance_rules_and_kill_switch():
    from macro import portfolio_live as pl

    book = pd.DataFrame(
        {
            "date": [pd.Timestamp("2026-12-01")],
            "asset": ["SPY"],
            "weight": [1.0],
            "status": ["optimal"],
            "overlay": [0],
            "reason": ["x"],
            "version": ["0.1.0"],
        }
    )
    assert pl.rebalance_due(book, pd.Timestamp("2026-12-15"), 0, CFG) is None
    assert pl.rebalance_due(book, pd.Timestamp("2026-12-15"), 1, CFG) == "drawdown overlay changed"
    assert pl.rebalance_due(book, pd.Timestamp("2027-01-04"), 0, CFG) == "monthly rebalance"
    assert pl.rebalance_due(book.iloc[:0], pd.Timestamp("2026-11-10"), 0, CFG) is None  # before live start
    off = copy.deepcopy(CFG)
    off["live"]["trading_enabled"] = False
    assert pl.rebalance_due(book, pd.Timestamp("2027-01-04"), 0, off) is None


def test_stale_prices_freeze_trading():
    from macro import portfolio_live as pl

    px = pd.DataFrame({"A": [1.0, 1.0]}, index=pd.to_datetime(["2026-11-02", "2026-11-03"]))
    assert pl.stale_assets(px, ["A", "B"], pd.Timestamp("2026-11-05"), 5) == ["B"]
    assert pl.stale_assets(px, ["A"], pd.Timestamp("2026-11-20"), 5) == ["A"]


def test_news_parse_and_tag():
    from macro import news

    rss = """<rss><channel>
      <item><title>SK Hynix lifts HBM output as memory chip prices rise</title><link>https://x/1</link>
      <pubDate>Tue, 17 Nov 2026 08:00:00 GMT</pubDate></item>
      <item><title>Fed's Powell signals patience on inflation</title><link>https://x/2</link>
      <pubDate>Tue, 17 Nov 2026 09:00:00 GMT</pubDate></item></channel></rss>"""
    df = news.parse_rss(rss, "Test")
    tags = news.tag(df["title"], news.load()["tags"])
    assert "SK Hynix" in tags[0] and "Memory chips" in tags[0] and "Fed" in tags[1] and "Inflation" in tags[1]
    assert "Fed" not in tags[0] and df["published"].iloc[0] == pd.Timestamp("2026-11-17 08:00", tz="UTC")
