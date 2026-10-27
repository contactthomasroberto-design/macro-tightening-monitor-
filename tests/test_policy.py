import numpy as np
import pandas as pd
import pytest

from macro import policy as pol


def test_taylor_1993_formula():
    # i = r* + pi + 0.5(pi - pi*) + 0.5 y with r*=0.5, pi=3, y=1 -> 0.5 + 3 + 0.5 + 0.5
    assert pol.taylor(3.0, 1.0, 0.5) == pytest.approx(4.5)
    assert pol.balanced_approach(3.0, 1.0, 0.5) == pytest.approx(5.0)
    assert pol.unemployment_gap_rule(3.0, 5.0, 4.5, 0.5) == pytest.approx(pol.taylor(3.0, -1.0, 0.5))


def test_reverse_views_invert_the_rule():
    i = pol.taylor(3.2, -0.4, 0.8)
    assert pol.reverse_inflation(i, -0.4, 0.8) == pytest.approx(3.2)
    assert pol.reverse_gap(i, 3.2, 0.8) == pytest.approx(-0.4)


def test_heatmap_robustness():
    heat = pol.rstar_heatmap(pi=4.0, y=1.0, i_actual=1.0, rstar_grid=[0, 1], a_pi_grid=[1.5, 2.0])
    assert pol.conclusion_robust(heat) == (True, "above")
    heat = pol.rstar_heatmap(pi=2.0, y=0.0, i_actual=2.5, rstar_grid=[0, 1], a_pi_grid=[1.5])
    assert pol.conclusion_robust(heat)[1] == "mixed"


def test_reaction_function_recovers_planted_parameters():
    g = np.random.default_rng(7)
    n = 400
    idx = pd.date_range("1960-01-01", periods=n, freq="QS")
    pi = 2 + np.cumsum(g.normal(0, 0.3, n)) * 0.3 + g.normal(0, 0.5, n)
    y = np.zeros(n)
    for t in range(1, n):
        y[t] = 0.8 * y[t - 1] + g.normal(0, 0.8)
    rho, a, b, c = 0.8, 1.0, 1.6, 0.4
    i = np.zeros(n)
    i[0] = 4
    for t in range(1, n):
        i[t] = rho * i[t - 1] + (1 - rho) * (a + b * pi[t] + c * y[t]) + g.normal(0, 0.15)
    q = pd.DataFrame({"i": i + 10, "pi": pi, "y": y}, index=idx)  # shift away from the lower bound
    r = pol.reaction_function(q, exclude_zlb=None)
    t = r.value
    assert t.loc["rho", "lower"] < rho < t.loc["rho", "upper"]
    assert t.loc["b (inflation)", "lower"] < b < t.loc["b (inflation)", "upper"]
    assert t.loc["c (output gap)", "lower"] < c < t.loc["c (output gap)", "upper"]
    assert r.extra["taylor_principle_p"] < 0.05


def test_priced_proxy_prefers_dated_assumption():
    v, srcs = pol.priced_rate_proxy(4.0, 3.0, {"value": 3.5, "source": "CME", "as_of": "2026-10-01"})
    assert v == 3.5 and "CME" in srcs
    v, srcs = pol.priced_rate_proxy(4.0, 3.0, {"value": None})
    assert v == 4.0 and "proxy" in srcs
    tab = pol.priced_vs_prescribed(3.0, 3.5, {"rule": 2.5})
    assert tab.loc["Market-implied (12m)", "moves"] == pytest.approx(2)
    assert tab.loc["rule", "moves"] == pytest.approx(-2)


def test_synchronisation_bounds():
    idx = pd.date_range("2000-01-01", periods=60, freq="MS")
    rates = pd.DataFrame(
        {"a": np.linspace(0, 5, 60), "b": np.linspace(0, 3, 60), "c": np.linspace(3, 0, 60)}, index=idx
    )
    s = pol.synchronisation(rates).dropna()
    assert s["hiking_share"].between(0, 1).all()
    assert s["hiking_share"].iloc[-1] == pytest.approx(2 / 3)
