"""Candidate portfolio signals (research log H48-H51): country valuation, CFTC positioning, earnings
momentum and event de-risking. Each is off in the live allocation (confidence 0, de-risking disabled)."""

import copy

import numpy as np
import pandas as pd
import pytest

from macro import portfolio as pf

CFG = pf.load_config()
W = pd.date_range("2000-01-07", periods=900, freq="W-FRI")


def _returns(seed=0, n=900):
    g = np.random.default_rng(seed)
    f = g.normal(0.0015, 0.022, n)
    return pd.DataFrame({a: f + g.normal(0, 0.012, n) for a in pf.VALUATION_ASSETS}, index=W[:n])


def test_valuation_ranks_the_cheapest_country_highest_without_future_data():
    r = _returns(3)
    names = list(pf.VALUATION_ASSETS)
    r.loc[r.index[-26:], "EWZ"] = -0.02  # EWZ falls far below its own trend in the last half-year
    s = pf.valuation_scores(r)
    assert set(s.index) <= set(names) and s.between(-1, 1).all()
    assert s.idxmax() == "EWZ"
    t = r.index[-60]
    before = pf.valuation_scores(r.loc[:t])
    shocked = r.copy()
    shocked.loc[shocked.index > t, names] = 0.05
    assert pf.valuation_scores(shocked.loc[:t]).equals(before)
    assert pf.valuation_scores(r.iloc[:100]).empty  # under five years of history


def test_positioning_is_contrarian_only_in_the_tails_and_respects_the_release_lag():
    tues = pd.date_range("2015-01-06", periods=300, freq="W-TUE")
    g = np.random.default_rng(0)
    base = pd.Series(g.normal(0, 1, 300), index=tues)
    crowded = base.copy()
    crowded.iloc[-1] = 10.0  # record net long
    t = tues[-1] + pd.Timedelta(days=10)  # the Friday after the report's release
    assets = ["SPY", "IEF"]
    s = pf.positioning_scores({"TFF_ES_LEV": crowded, "TFF_UST10_LEV": base * 0}, t, assets)
    assert s["SPY"] == pytest.approx(-1.0, abs=0.05) and s["IEF"] == 0.0
    short = base.copy()
    short.iloc[-1] = -10.0
    assert pf.positioning_scores({"TFF_ES_LEV": short}, t, assets)["SPY"] > 0.9
    # released on the Friday at 15:30 ET: not usable at that Friday's rebalance
    same_friday = tues[-1] + pd.Timedelta(days=3)
    s2 = pf.positioning_scores({"TFF_ES_LEV": crowded}, same_friday, assets)
    assert s2.get("SPY", 0.0) > -0.5


def test_earnings_momentum_uses_filings_before_t_and_has_the_right_sign():
    filed = pd.date_range("2015-02-01", periods=40, freq="QS-FEB") + pd.Timedelta(days=19)
    g = np.random.default_rng(1)
    growth = np.r_[np.full(36, 0.02), [0.02, 0.06, 0.10, 0.14]]  # accelerating growth at the end
    rev = pd.Series(1e9 * np.exp(np.cumsum(growth + g.normal(0, 0.002, 40))), index=filed)
    t = filed[-1] + pd.Timedelta(days=3)
    s = pf.earnings_scores({"MU_REV": rev}, t, ["MU", "NVDA"])
    assert list(s.index) == ["MU"] and s["MU"] > 0.5
    # a filing dated t itself is not used
    assert pf.earnings_component(rev, filed[-1]) == pf.earnings_component(rev.iloc[:-1], filed[-1])
    slowing = pd.Series(1e9 * np.exp(np.cumsum(growth[::-1])), index=filed)
    assert pf.earnings_scores({"MU_REV": slowing}, t, ["MU"]).get("MU", 0.0) <= 0.05


def test_event_calendar_and_derisk():
    ev = pf.load_events()
    assert pf._first_friday(2026, 11) == pd.Timestamp("2026-11-06")
    assert pf._weekday_on_or_after(pd.Timestamp("2026-12-13")) == pd.Timestamp("2026-12-14")  # a Sunday
    fomc = ev.loc[ev["kind"] == "fomc", "date"]
    assert pd.Timestamp("2020-03-15") not in set(fomc)  # unscheduled: would be look-ahead
    assert (fomc.dt.year.value_counts() <= 8).all()
    t = pd.Timestamp("2026-12-04")  # FOMC on 9 December
    assert "fomc" in pf.events_ahead(ev, t, 7)
    assert "fomc" not in pf.events_ahead(ev, t - pd.Timedelta(days=7), 7)
    c0, vs0, hit0 = pf.event_derisk(CFG, ev, t, 1.0)
    assert c0 is CFG and vs0 == 1.0 and not hit0  # off by default: live weights unchanged
    on = copy.deepcopy(CFG)
    on["model"]["event_derisk"]["enabled"] = True
    _, vs1, hit1 = pf.event_derisk(on, ev, t, 1.0)
    assert vs1 == pytest.approx(0.8) and "fomc" in hit1
    nv = pd.DataFrame({"date": [t + pd.Timedelta(days=3)], "kind": ["nvda_earnings"]})
    c2, vs2, _ = pf.event_derisk(on, nv, t, 1.0)
    assert vs2 == 1.0
    assert c2["sleeves"]["semis"]["max"] == pytest.approx(0.8 * CFG["sleeves"]["semis"]["max"])
    assert on["sleeves"]["semis"]["max"] == CFG["sleeves"]["semis"]["max"]  # the input is not mutated


def test_candidate_families_carry_no_weight_by_default():
    for fam in ("valuation", "positioning", "earnings"):
        assert fam in pf.CANDIDATE_FAMILIES and fam not in pf.FAMILIES
        assert CFG["model"]["confidence"][fam] == 0.0
    assert not CFG["model"]["event_derisk"]["enabled"]
