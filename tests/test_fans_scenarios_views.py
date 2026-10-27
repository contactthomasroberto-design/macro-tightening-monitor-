import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy import integrate

from macro import fans, scenarios, views


@settings(max_examples=60, deadline=None)
@given(mode=st.floats(-5, 10), sigma=st.floats(0.05, 3), gamma=st.floats(-0.9, 0.9))
def test_tpn_is_a_distribution(mode, sigma, gamma):
    s1, s2 = fans.scales(sigma, gamma)
    total, _ = integrate.quad(
        lambda x: fans.tpn_pdf(x, mode, s1, s2), mode - 40 * s1, mode + 40 * s2, points=[mode]
    )
    assert total == pytest.approx(1.0, abs=1e-6)
    ps = np.linspace(0.01, 0.99, 25)
    q = fans.tpn_ppf(ps, mode, s1, s2)
    assert np.all(np.diff(q) > 0)  # monotone quantiles
    assert np.allclose(fans.tpn_cdf(q, mode, s1, s2), ps, atol=1e-8)  # ppf inverts cdf


@settings(max_examples=40, deadline=None)
@given(sigma=st.floats(0.1, 2), skew=st.floats(-0.5, 0.5))
def test_gamma_reproduces_requested_skew(sigma, skew):
    g = fans.gamma_from_skew(sigma, skew)
    s1, s2 = fans.scales(sigma, g)
    achieved = fans.tpn_mean(0.0, s1, s2)
    if abs(g) < 0.95 - 1e-6:
        assert achieved == pytest.approx(skew, abs=1e-6)
    else:
        assert np.sign(achieved) == np.sign(skew) or skew == 0


def test_fan_quantiles_nested_bands():
    idx = pd.date_range("2027-01-01", periods=4, freq="QS")
    q = fans.fan_quantiles(
        pd.Series([2.0, 2.2, 2.4, 2.5], index=idx),
        pd.Series([0.3, 0.5, 0.7, 0.9], index=idx),
        pd.Series([2.1, 2.4, 2.7, 2.9], index=idx),
    )
    probs = sorted(c for c in q.columns if isinstance(c, float))
    vals = q[probs].to_numpy()
    assert np.all(np.diff(vals, axis=1) >= -1e-12)
    assert (q["gamma"] > 0).all()  # mean above mode => upside skew
    widths = (q[0.95] - q[0.05]).to_numpy()
    assert np.all(np.diff(widths) > 0)


def _params():
    return scenarios.EngineParams(
        c=0.2,
        rho=0.9,
        kappa=0.1,
        theta=0.01,
        resid_pi=np.array([-0.1, 0.0, 0.1]),
        rf_rho=0.8,
        rf_a=0.5,
        rf_b=1.5,
        rf_c=0.5,
        resid_i=np.array([-0.05, 0.05]),
        resid_du=np.array([-0.1, 0.1]),
        okun=2.0,
        ustar=4.0,
        rstar=0.75,
        pi_star=2.0,
        max_step_q=0.5,
    )


SCEN = {
    "a": {
        "oil_shock_pct": [0] * 8,
        "unemp_change_pp": [0] * 8,
        "infl_shock_pp": [0] * 8,
        "tp_change_bp": [0] * 8,
    },
    "b": {
        "oil_shock_pct": [0] * 8,
        "unemp_change_pp": [0.3 * k for k in range(8)],
        "infl_shock_pp": [0] * 8,
        "tp_change_bp": [0] * 8,
    },
}
INIT = {"pi": 3.0, "u": 4.0, "i": 4.0, "oil4_base": 0.0, "tp": 0.5}


def test_engine_respects_step_cap_and_floor():
    s = scenarios.simulate(_params(), INIT, SCEN["b"], 500, seed=1)
    steps = np.diff(np.c_[np.full(500, INIT["i"]), s["i"]], axis=1)
    assert np.all(np.abs(steps) <= 0.5 + 0.125 + 1e-9)  # cap, plus rounding to 25bp
    assert np.all(s["i"] >= 0.125)
    assert np.allclose((s["i"] * 4) % 1, 0)


def test_mixture_weights_sum_to_one_and_moves_monotone():
    sims = scenarios.run_monte_carlo(_params(), INIT, SCEN, n_per=2000, seed=3)
    vals, w = scenarios.mixture(sims, {"a": 0.7, "b": 0.3}, "i")
    assert w.sum() == pytest.approx(1.0)
    mv = scenarios.moves_probabilities(vals, w, INIT["i"])
    assert (np.diff(mv["P(at least k hikes)"]) <= 1e-12).all()
    assert (np.diff(mv["P(at least k cuts)"]) <= 1e-12).all()
    q = scenarios.weighted_quantile(vals, w, [0.05, 0.5, 0.95])
    assert np.all(q[0] <= q[1]) and np.all(q[1] <= q[2])
    # rising unemployment scenario triggers the Sahm-type rule far more often
    assert (
        scenarios.sahm_trigger(sims["b"]["mc"]["u"], 4.0).mean()
        > scenarios.sahm_trigger(sims["a"]["mc"]["u"], 4.0).mean()
    )


def test_sahm_trigger_deterministic():
    u = np.array([[4.0, 4.3, 4.7, 5.0]])
    assert scenarios.sahm_trigger(u, 4.0)[0]
    assert not scenarios.sahm_trigger(np.array([[4.0, 4.1, 4.0, 4.1]]), 4.0)[0]


def test_status_and_confirmation():
    assert views.status_from(0.1, (0.5, 1, 2)) == "good"
    assert views.status_from(2.5, (0.5, 1, 2)) == "critical"
    assert views.status_from(-1.5, (0.0, -1.0, -2.0), higher_is_worse=False) == "serious"
    c = views.market_confirmation({"2Y yield": 10, "S&P 500": 2.0}, "tightening")
    assert bool(c.loc["2Y yield", "consistent"]) and not bool(c.loc["S&P 500", "consistent"])


def test_view_template_rejects_recommendations():
    with pytest.raises(ValueError):
        views.view_template("We recommend to buy duration", [], "", [], [], [], [])
    t = views.view_template("Models imply tightening", ["x"], "priced", ["y"], ["z"], ["c"], ["sensitivity"])
    assert "Implications and sensitivities (not recommendations)" in t
