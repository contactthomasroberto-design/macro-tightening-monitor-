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
        b_eq = {"equity": 1.0, "style": 0.9, "sector": 1.0, "semis": 1.4, "bond": -0.1, "credit": 0.3}.get(
            c["sleeve"], {"real": 0.3, "alt": 0.0, "fx": -0.1, "cash": 0.0}.get(c["sleeve"], 0.0)
        )
        b_d = {"bond": 1.0, "credit": 0.5, "cash": 0.0}.get(c["sleeve"], 0.0)
        sd = {"cash": 0.0002, "bond": 0.003, "credit": 0.004, "fx": 0.006}.get(c["sleeve"], 0.012)
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
    g = np.random.default_rng(10)
    mu = pd.Series(g.normal(0, 0.3, len(cov)), index=cov.index)  # strong, mixed views: invites shorts
    w, status = pf.optimise(mu, cov, w_eq, CFG)
    uni, sl = CFG["universe"], CFG["sleeves"]
    pick = lambda *s_: sum(w[a] for a in w.index if uni[a]["sleeve"] in s_)  # noqa: E731
    vol = float(np.sqrt(w @ cov @ w))
    vol_b = float(np.sqrt(w_eq @ cov @ w_eq))
    te = float(np.sqrt((w - w_eq) @ cov @ (w - w_eq)))
    assert status == "optimal" and w.sum() == pytest.approx(1)
    assert all(uni[a].get("min", 0) - 1e-5 <= w[a] <= uni[a]["max"] + 1e-5 for a in w.index)
    assert (w < -1e-4).any()  # shorts are used
    assert w.abs().sum() <= sl["gross_max"] + 1e-4
    assert sl["semis"]["min"] - 1e-5 <= pick("semis") <= sl["semis"]["max"] + 1e-5
    assert sl["equity_net"]["min"] - 1e-5 <= pick(*pf.EQUITY_SLEEVES) <= sl["equity_net"]["max"] + 1e-5
    assert (
        pick("alt") <= sl["alt_max"] + 1e-5
        and w[["UUP", "FXY", "FXE", "FXF"]].abs().sum() <= sl["fx_gross_max"] + 1e-4
    )
    assert w["HYNIX"] >= 0.015 - 1e-5 and w["SAMSUNG"] >= 0.015 - 1e-5  # Korean names: long only
    assert vol <= vol_b * (1 + 1e-3) and te <= CFG["model"]["tracking_error_max"] + 1e-4
    lo, _ = pf.optimise(mu, cov, w_eq, CFG, long_only=True)
    assert (lo >= -1e-6).all()


def test_turnover_cost_keeps_weights_near_the_current_book():
    r = _returns(3)
    cov = pf.covariance(r[list(CFG["universe"])], 156, 52)
    w_eq = pf.equilibrium_weights(list(cov.index), CFG)
    mu, _ = pf.black_litterman(cov, w_eq, {}, CFG)
    w0, _ = pf.optimise(mu, cov, w_eq, CFG)
    nudged = mu + 0.0005 * np.random.default_rng(1).normal(size=len(mu))  # tiny change in views
    w1, _ = pf.optimise(nudged, cov, w_eq, CFG, w_prev=w0)
    assert (w1 - w0).abs().sum() < 0.02  # costs make small view changes not worth trading


def test_tail_hedge_put_pricing_and_ratio():
    p = pf.bs_put(1.0, 0.95, 4 / 52, 0.04, 0.20 * 1.15)
    assert 0.002 < p < 0.02
    assert pf.bs_put(1.0, 0.95, 4 / 52, 0.04, 0.40) > p
    assert pf.hedge_ratio(-1.0, -0.5, CFG) == 1.0 and pf.hedge_ratio(1.0, 0.5, CFG) == 0.25


def test_regime_value_carry_and_house_views():
    idx = pd.date_range("1990-01-01", periods=400, freq="MS")
    ip = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(2).normal(0.002, 0.01, 400))), index=idx)
    cpi = pd.Series(100 * np.exp(np.cumsum(np.random.default_rng(3).normal(0.002, 0.002, 400))), index=idx)
    reg = pf.regime_series(ip, cpi)
    assert set(reg.dropna().unique()) <= {
        f"growth {g}, inflation {i}" for g in ("up", "down") for i in ("up", "down")
    }
    r = _returns(4)
    vs = pf.value_scores(r, CFG)
    assert vs.between(-1, 1).all() and "SPY" in vs.index  # region group
    views = [
        {"date": "2026-11-16", "stances": {"SPY": 1, "VGK": -1}},
        {"date": "2026-01-01", "stances": {"SPY": -1}},
    ]
    hs = pf.house_scores(views, "2026-11-17", ["SPY", "VGK"])
    assert hs["SPY"] == 1 and hs["VGK"] == -1  # the January view is older than six months
    assert pf.house_scores(views, "2026-11-10", ["SPY"]).empty  # not yet published


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
    assert bt["log"]["cost"].sum() > 0 and bt0["log"]["cost"].sum() == 0
    assert bt["log"]["turnover"].sum() < bt0["log"]["turnover"].sum()  # costs discourage trading
    assert np.allclose(bt["weights"].sum(axis=1), 1, atol=1e-4)


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
            "version": ["0.3.0"],
        }
    )
    assert pl.rebalance_due(book, pd.Timestamp("2026-12-03"), 0, CFG) is None  # same week
    assert pl.rebalance_due(book, pd.Timestamp("2026-12-03"), 1, CFG) == "drawdown overlay changed"
    assert pl.rebalance_due(book, pd.Timestamp("2026-12-08"), 0, CFG) == "weekly rebalance"
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


# ------------------------------------------------------------------ news scoring
def test_news_novelty_flags_repeats():
    from macro import news_scoring as ns

    t = pd.to_datetime(["2026-11-17 08:00", "2026-11-17 09:00", "2026-11-17 10:00"], utc=True)
    titles = [
        "Samsung and Apple near long-term DRAM supply agreement - Investing.com",
        "Samsung and Apple near long-term DRAM supply agreement By Investing.com - Investing.com Canada",
        "Fed holds rates steady",
    ]
    n = ns.novelty(titles, list(t), 0.5)
    assert n[0] == 1 and n[1] == 0.5 and n[2] == 1


def test_news_asset_scores_weight_relevance_freshness_and_credibility(tmp_path):
    from macro import news
    from macro import news_scoring as ns

    cfg = news.load()
    now = pd.Timestamp("2026-11-17 12:00", tz="UTC")
    df = pd.DataFrame(
        {
            "title": ["SK Hynix record HBM orders", "Chip stocks slump", "Old Hynix story"],
            "link": ["a", "b", "c"],
            "published": pd.to_datetime(
                ["2026-11-17 11:00", "2026-11-17 11:00", "2026-11-10 11:00"], utc=True
            ),
            "source": ["Reuters (via Google News)", "BBC Business", "BBC Business"],
            "tags": [["SK Hynix", "Memory chips"], ["Semiconductors"], ["SK Hynix"]],
        }
    )
    sc = ns.score(df, lambda ts: np.array([0.9, -0.8, -0.9]), cfg)
    a = ns.asset_scores(sc, cfg, now=now)
    assert a.loc["HYNIX", "news score"] > 0.5  # direct, fresh, credible beats sector-level and stale news
    assert a.loc["NVDA", "news score"] == pytest.approx(-0.8)
    path = tmp_path / "n.csv"
    assert ns.append_archive(sc, path, now=now) == 3 and ns.append_archive(sc, path, now=now) == 0
    back = ns.read_archive(path)
    assert back["tags"].iloc[0] == ["SK Hynix", "Memory chips"]
    idx = ns.daily_index(back, cfg)
    assert idx.loc[pd.Timestamp("2026-11-17"), "HYNIX"] > 0


def test_news_gate_opens_only_on_a_real_signal():
    g = np.random.default_rng(8)
    d = pd.date_range("2017-01-01", periods=7 * 520, freq="D")
    w = pd.date_range("2017-01-06", periods=520, freq="W-FRI")
    r = pd.DataFrame({"SOX": g.normal(0, 0.02, 520)}, index=w)
    tone_good, tone_noise = {}, {}
    for a, tid in pf.NEWS_TONE_OF.items():
        daily = pd.Series(g.normal(0, 1, len(d)), index=d)
        sig = pf.tone_signal(daily).reindex(w).fillna(0)
        fut = sig.shift(1).fillna(0)  # tone today predicts next weeks' relative return
        r[a] = r["SOX"] + 0.01 * fut + g.normal(0, 0.01, 520)
        tone_good[tid] = daily
        tone_noise[tid] = pd.Series(g.normal(0, 1, len(d)), index=d)
    good = pf.news_test(r, tone_good)
    assert good["t"] > 2 and pf.news_confidence(good) == 0.10
    assert pf.news_confidence(pf.news_test(r, tone_noise)) == 0.0


def test_alternative_constructions():
    r = _returns(9)
    cov = pf.covariance(r[list(CFG["universe"])], 156, 52)
    erc = pf.equal_risk_contribution(cov)
    rc = erc * (cov.to_numpy() @ erc.to_numpy())
    assert np.allclose(rc / rc.sum(), 1 / len(cov), atol=1e-4)  # equal risk contributions
    for fn in pf.ALTERNATIVES.values():
        w = fn(cov)
        assert w.sum() == pytest.approx(1) and (w >= -1e-9).all()
    mv = pf.min_variance(cov)
    assert float(mv @ cov @ mv) <= float(erc @ cov @ erc) + 1e-12
    hrp = pf.hierarchical_risk_parity(cov)
    assert hrp["BIL"] > hrp["HYNIX"]  # the lowest-variance asset gets more than a volatile stock


def test_research_tracker_stances_are_explicit_only():
    from macro import research_tracker as rt

    assets = rt.load()["assets"]
    assert rt.stances("Goldman upgrades Japanese stocks to overweight", assets) == {"EWJ": 1}
    assert rt.stances("Morgan Stanley turns bearish on the dollar, favours gold", assets) == {
        "UUP": -1,
        "GLD": 1,
    }
    assert rt.stances("BlackRock says markets face uncertainty", assets) == {}
    assert rt.stances("UBS upgrades and downgrades European stocks", assets) == {}  # ambiguous


def test_team_roster_matches_agent_files(tmp_path):
    from macro import team

    r = team.roster()
    assert r["defined"].all(), r[~r["defined"]]["agent"].tolist()  # every listed member has an agent file
    assert r["agent"].is_unique and len(r) >= 25
    path = tmp_path / "log.csv"
    team.append_log(
        [
            {
                "date": "2026-11-17",
                "agent": "macro-strategist",
                "status": "terminé",
                "task": "t1",
                "summary": "s",
                "link": "",
            },
            {
                "date": "2026-11-18",
                "agent": "macro-strategist",
                "status": "en cours",
                "task": "t2",
                "summary": "",
                "link": "",
            },
        ],
        path,
    )
    cur, past = team.current_and_past(team.read_log(path), "macro-strategist")
    assert cur["task"] == "t2" and past["task"].tolist() == ["t1"]


def test_risk_budget_shares_sum_to_one_by_source():
    r = _returns(11)
    cov = pf.covariance(r[list(CFG["universe"])], 156, 52)
    w_eq = pf.equilibrium_weights(list(cov.index), CFG)
    mu, _ = pf.black_litterman(cov, w_eq, {}, CFG)
    w, _ = pf.optimise(mu, cov, w_eq, CFG)
    rb = pf.risk_budget(w, cov, r, CFG)
    assert rb["ex-ante share"].sum() == pytest.approx(1, abs=1e-8)
    assert rb["realised share (3y)"].sum() == pytest.approx(1, abs=1e-8)
    assert rb["net weight"].sum() == pytest.approx(1, abs=1e-6)
    assert pf.risk_source("TIP", CFG) == "inflation" and pf.risk_source("SOXX", CFG) == "semis"
    assert pf.risk_source("HYG", CFG) == "credit" and pf.risk_source("IEF", CFG) == "rates (duration)"


def test_style_regression_recovers_planted_loadings():
    r = _returns(12)
    g = np.random.default_rng(5)
    f = {k: r[a] - r[b] for k, (a, b) in pf.STYLE_FACTORS.items()}
    planted = {
        "market": 0.6,
        "value": 0.3,
        "momentum": -0.4,
        "quality": 0.0,
        "size (equal weight)": 0.2,
        "min vol": 0.5,
    }
    y = 0.0004 + sum(v * f[k] for k, v in planted.items()) + g.normal(0, 0.002, len(r))
    res = pf.alpha_decomposition(y + r["BIL"], r)  # excess of T-bills when no benchmark is given
    lo = res["loadings"]["loading"]
    for k, v in planted.items():
        assert lo[k] == pytest.approx(v, abs=0.08)
    assert res["alpha (annual)"] == pytest.approx(0.0004 * 52, abs=0.01) and res["R²"] > 0.8
    # a 100% S&P 500 book: market loading 1, nothing else
    se = pf.style_exposures(pd.Series({"SPY": 1.0}), r)
    assert se["loadings"].loc["market", "loading"] == pytest.approx(1, abs=1e-6)
    assert se["loadings"].drop(index="market")["loading"].abs().max() < 1e-6


def test_resampled_weights_satisfy_the_constraints():
    r = _returns(13)
    cov = pf.covariance(r[list(CFG["universe"])], 156, 52)
    w_eq = pf.equilibrium_weights(list(cov.index), CFG)
    g = np.random.default_rng(3)
    mu = pd.Series(g.normal(0, 0.1, len(cov)), index=cov.index)
    cfg = copy.deepcopy(CFG)
    cfg["model"]["resample"] = {"draws": 8, "seed": 1}
    w, status = pf.optimise(mu, cov, w_eq, cfg)
    w_mv, _ = pf.optimise(mu, cov, w_eq, CFG)
    uni, sl = cfg["universe"], cfg["sleeves"]
    pick = lambda *s_: sum(w[a] for a in w.index if uni[a]["sleeve"] in s_)  # noqa: E731
    assert status.startswith("resampled") and w.sum() == pytest.approx(1)
    assert all(uni[a].get("min", 0) - 1e-5 <= w[a] <= uni[a]["max"] + 1e-5 for a in w.index)
    assert w.abs().sum() <= sl["gross_max"] + 1e-4
    assert sl["semis"]["min"] - 1e-5 <= pick("semis") <= sl["semis"]["max"] + 1e-5
    assert sl["equity_net"]["min"] - 1e-5 <= pick(*pf.EQUITY_SLEEVES) <= sl["equity_net"]["max"] + 1e-5
    vol_b = float(np.sqrt(w_eq @ cov @ w_eq))
    assert float(np.sqrt(w @ cov @ w)) <= vol_b * (1 + 1e-3)
    assert float(np.sqrt((w - w_eq) @ cov @ (w - w_eq))) <= cfg["model"]["tracking_error_max"] + 1e-4
    assert w.abs().sum() <= w_mv.abs().sum() + 1e-6  # averaging shrinks extreme positions
    again, _ = pf.optimise(mu, cov, w_eq, cfg)
    assert np.allclose(again, w)  # seeded: reproducible


def test_regime_series_is_not_empty_on_monthly_data():
    # regression: the publication-lag shift used to misalign the validity mask, leaving the series empty
    idx = pd.date_range("2000-01-01", periods=120, freq="MS")
    ip = pd.Series(np.linspace(100, 130, 120), idx)
    cpi = pd.Series(100 * 1.002 ** np.arange(120) * (1 + 0.01 * np.sin(np.arange(120) / 6)), idx)
    reg = pf.regime_series(ip, cpi).dropna()
    assert len(reg) > 100 and reg.str.startswith("growth").all()
    assert reg.index[0] > idx[15]  # 12 months for y/y + 3 for the change + publication lag


def test_committee_scores_and_brier_gate():
    dec = pd.DataFrame(
        [
            dict(
                agent="chief-investment-officer",
                target="SPY",
                metric="return",
                direction="above",
                probability=0.7,
                date="2026-11-17",
                horizon="2027-01-17",
                status="open",
                outcome=np.nan,
            ),
            dict(
                agent="chief-investment-officer",
                target="TLT",
                metric="return",
                direction="below",
                probability=0.6,
                date="2026-11-17",
                horizon="2026-12-17",
                status="open",
                outcome=np.nan,
            ),
            dict(
                agent="macro-strategist",
                target="GLD",
                metric="return",
                direction="above",
                probability=0.9,
                date="2026-11-17",
                horizon="2027-01-17",
                status="open",
                outcome=np.nan,
            ),
        ]
    )
    s = pf.committee_scores(dec, "2026-11-20", ["SPY", "TLT", "GLD"])
    assert s["SPY"] == pytest.approx(0.4) and s["TLT"] == pytest.approx(-0.2) and "GLD" not in s
    assert pf.committee_scores(dec, "2026-12-20", ["SPY", "TLT"]).index.tolist() == ["SPY"]  # TLT expired
    assert pf.committee_scores(dec, "2026-11-10", ["SPY"]).empty  # not yet decided
    assert pf.committee_confidence(dec) == 0.05  # fewer than 20 scored decisions
    good = pd.DataFrame(
        {
            "agent": "chief-investment-officer",
            "status": "resolved",
            "probability": [0.8] * 10 + [0.2] * 10,
            "outcome": [1] * 10 + [0] * 10,
        }
    )
    bad = good.assign(outcome=[0] * 10 + [1] * 10)
    assert 0.05 < pf.committee_confidence(good) <= 0.15 and pf.committee_confidence(bad) == 0.0


def test_usd_prices_drop_non_positive_prices():
    idx = pd.bdate_range("2001-01-01", periods=5)
    s = pd.Series([-1.0, 0.0, 2.0, 3.0, 4.0], idx)
    cfg = {"universe": {"HYNIX": {}}}
    px = pf.usd_prices(lambda k: s if k == "HYNIX" else None, cfg)
    assert (px["HYNIX"].dropna() > 0).all() and px["HYNIX"].notna().sum() == 3
