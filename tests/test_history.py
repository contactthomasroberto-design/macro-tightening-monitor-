"""Historical cycles (GMD): cycle dating, outcomes and base rates on planted panels."""

import numpy as np
import pandas as pd
import pytest

from macro import history as h
from macro.data import gmd


def _panel(rates, growth, infl=3.0, start=2000, iso="AAA", crisis=None):
    n = len(rates)
    gdp = 100 * np.exp(np.cumsum(np.r_[0, np.asarray(growth[1:], float) / 100]))
    return pd.DataFrame(
        {
            "ISO3": iso,
            "countryname": iso,
            "year": np.arange(start, start + n),
            "cbrate": rates,
            "strate": np.nan,
            "infl": infl,
            "rGDP": gdp,
            "BankingCrisis": crisis if crisis is not None else 0.0,
        }
    )


def test_cycle_dated_trough_to_peak_with_recession():
    rates = [1, 1, 2, 3, 4, 3, 2, 2, 2]
    growth = [2, 2, 2, 2, 1, -1, 2, 2, 2]  # fall in the year after the peak (2004 -> 2005)
    c = h.find_cycles(_panel(rates, growth), last_year=2008)
    assert len(c) == 1
    r = c.iloc[0]
    assert (r["trough"], r["peak"], r["rise_pp"]) == (2001, 2004, 3.0)
    assert r["recession_after"] and r["completed"]


def test_small_rises_are_not_cycles_and_open_window_is_unknown():
    rates = [1, 1.5, 1.2, 1.6, 1.1, 1, 1, 3, 3.5]
    c = h.find_cycles(_panel(rates, [2] * 9), last_year=2008)
    assert len(c) == 1  # only the final 1 -> 3.5 rise
    assert c.iloc[0]["recession_after"] is None  # peak 2008, outcome window not over
    assert not c.iloc[0]["completed"]


def test_projection_years_excluded_and_ignore_years():
    rates = [1, 2, 3, 2, 1, 1, 1]
    growth = [2, 2, 2, 2, 2, -3, 2]  # 2005 is negative, outside peak(2002)+2 -> no recession
    c = h.find_cycles(_panel(rates, growth), last_year=2006)
    assert not c.iloc[0]["recession_after"]
    growth2 = [2, 2, 2, -3, 2, 2, 2]  # 2003 negative: recession, unless 2003 is ignored
    assert h.find_cycles(_panel(rates, growth2), last_year=2006).iloc[0]["recession_after"]
    c3 = h.find_cycles(_panel(rates, growth2), last_year=2006, ignore_years=(2003,))
    assert not c3.iloc[0]["recession_after"]
    assert h.find_cycles(_panel(rates, growth2), last_year=2001).empty  # projections cut off


def test_wilson_interval_and_summary():
    lo, hi = h.wilson(5, 10)
    assert lo < 0.5 < hi and lo == pytest.approx(0.2366, abs=1e-3)
    cyc = pd.DataFrame(
        {
            "era": ["a", "a", "b"],
            "recession_after": [True, False, None],
            "crisis_after": [False, False, True],
            "rise_pp": [1.0, 3.0, 2.0],
        }
    )
    s = h.summarise(cyc, "era").set_index("era")
    assert s.loc["a", "cycles (N)"] == 2 and s.loc["a", "share ending in recession"] == 0.5
    assert s.loc["b", "cycles (N)"] == 0


def test_current_position_past_peak_and_self_exclusion():
    rates = [0.25, 0.25, 2.0, 5.0, 4.5, 3.5]
    p = _panel(rates, [2] * 6, start=2020, iso="USA")
    cur = h.current_position(p, last_year=2025, countries=("USA",))
    r = cur.loc["USA"]
    assert (r["trough"], r["peak"], r["rise (pp)"]) == (2021, 2023, 4.75)  # latest year at the low
    assert r["stage"].startswith("past peak")
    cyc = pd.DataFrame(
        {
            "ISO3": ["USA"],
            "trough": [2021],
            "rise_pp": [4.75],
            "infl_at_peak": [3.0],
            "recession_after": [False],
        }
    )
    assert h.similar_share(cyc, 4.75, 3.0, exclude=("USA", 2021))["n"] == 0
    assert h.similar_share(cyc, 4.75, 3.0)["n"] == 1


def test_demo_panel_has_cycles():
    c = h.find_cycles(gmd.demo_panel(), last_year=2025)
    assert len(c) > 100 and c["recession_after"].notna().sum() > 50
