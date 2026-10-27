import numpy as np
import pandas as pd
import pytest

from macro import positioning as pos
from macro import transmission as tr


def test_event_study_recovers_jump():
    idx = pd.bdate_range("2020-01-01", periods=300)
    s = pd.Series(1.0, index=idx)
    events = idx[[50, 120, 200]]
    for e in events:
        s.loc[e:] += 0.25  # +25bp on each event day
    out = tr.event_study({"y": s}, {"y": "yield"}, events, window=5, n_boot=100)["y"]
    assert out.loc[-1, "mean"] == pytest.approx(0)
    assert out.loc[0, "mean"] == pytest.approx(25)
    assert out.attrs["n_events"] == 3


def test_real_yield_beta_recovered():
    g = np.random.default_rng(2)
    n = 600
    idx = pd.date_range("2000-01-07", periods=n, freq="W-FRI")
    dr = pd.Series(g.normal(0, 0.1, n), index=idx)
    dbe = pd.Series(g.normal(0, 0.05, n), index=idx)
    r = pd.DataFrame({"eq": -8 * dr + 3 * dbe + g.normal(0, 0.5, n)}, index=idx)
    out = tr.real_yield_betas(r, dr, dbe).iloc[0]
    assert abs(out["b_real"] + 8) < 3 * out["se_real"]


def test_stock_bond_regime_correlation():
    g = np.random.default_rng(3)
    n = 400
    idx = pd.date_range("1980-01-01", periods=n, freq="MS")
    infl = pd.Series(np.where(np.arange(n) < 200, 1.5, 4.0), index=idx)
    eq = pd.Series(g.normal(0, 1, n), index=idx)
    d10 = pd.Series(
        np.where(infl > 3, -0.7 * eq + g.normal(0, 0.5, n), 0.5 * eq + g.normal(0, 0.5, n)), index=idx
    )
    t = tr.stock_bond_by_regime(eq, d10, infl, n_boot=200)
    assert t.loc["core > 3%", "lower"] > 0
    assert t.loc["core < 2%", "upper"] < 0


def test_positioning_adjustments_and_flags():
    idx = pd.date_range("2020-01-07", periods=200, freq="W-TUE")
    net = pd.Series(np.arange(200.0), index=idx)
    px = {"SPX": pd.Series(4000.0, index=idx)}
    usd = pos.adjust(net, "TFF_ES_LEV", px)
    assert usd.iloc[-1] == pytest.approx(199 * 50 * 4000 / 1e9)
    assert pos.adjust(net, "TFF_SOFR3M_LEV", px).iloc[-1] == pytest.approx(199 * 25 / 70)
    tab, _ = pos.positioning_table({"TFF_ES_LEV": usd})
    assert tab["flag"].iloc[0] == "crowded long"
