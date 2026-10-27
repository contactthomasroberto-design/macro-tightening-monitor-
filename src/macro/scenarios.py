"""Scenario engine and Monte Carlo (BRIEF §5.8). Quarterly, 8 quarters, US.

Equations (estimated on quarterly data; parameters and residuals feed the simulation):

  Phillips curve  pi_t = c + rho pi_{t-1} + kappa (u*_t - u_t) + theta d4log(oil)_t + e_t       (OLS, HAC)
  Unemployment    u_t  = u_0 + du^s_t + v_t,  v_t = 0.5 v_{t-1} + w_t, w_t bootstrapped from the residuals
                  of an AR(1) on quarterly changes in unemployment (winsorised at the 2.5/97.5
                  percentiles so that the 2020 spike does not dominate; the scenario path carries the cycle)
  Policy          i*_t = a + b pi_t + c y_t,   y_t = -okun (u_t - u*),
                  i_t  = i_{t-1} + clip(rho_i i_{t-1} + (1 - rho_i) i*_t - i_{t-1}, +/- max step),
                  floored at the effective lower bound (0.125)
  10Y yield       y10_t = avg(i_{t..t+39}) + tp_t (policy held at its last value beyond the horizon,
                  converging to r* + pi* at 3% per quarter) + scenario term-premium change

Scenario s adds oil shocks, an unemployment path and non-energy inflation impulses (scenarios.yaml).
Monte Carlo: N paths per scenario with residual bootstrap (Phillips and policy residuals, Δu
innovations); scenario mixing by probability weights.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from macro.utils import ols_hac, rng


@dataclass
class EngineParams:
    c: float
    rho: float
    kappa: float
    theta: float
    resid_pi: np.ndarray
    rf_rho: float
    rf_a: float
    rf_b: float
    rf_c: float
    resid_i: np.ndarray
    resid_du: np.ndarray
    okun: float
    ustar: float
    rstar: float
    pi_star: float
    max_step_q: float
    floor: float = 0.125
    n_obs: int = 0


def estimate_phillips(q: pd.DataFrame) -> tuple[dict, np.ndarray, int, pd.DataFrame]:
    """Quarterly headline yoy inflation on its lag, the unemployment gap and the 4-quarter oil change."""
    d = pd.DataFrame(
        {"pi": q["pi"], "pi_l": q["pi"].shift(1), "ugap_neg": q["ustar"] - q["u"], "oil4": q["oil4"]}
    ).dropna()
    r = ols_hac(d["pi"], d[["pi_l", "ugap_neg", "oil4"]])
    tab = pd.DataFrame({"estimate": r.params, "se": r.bse})
    return (
        {
            "c": r.params["const"],
            "rho": r.params["pi_l"],
            "kappa": r.params["ugap_neg"],
            "theta": r.params["oil4"],
        },
        r.resid.to_numpy(),
        r.nobs,
        tab,
    )


def simulate(
    p: EngineParams,
    init: dict,
    scen: dict,
    n: int,
    quarters: int = 8,
    seed: int | None = None,
    shocks: bool = True,
) -> dict[str, np.ndarray]:
    """Simulate n paths for one scenario. init: pi, u, i, oil4_base, tp. Returns arrays (n, quarters)."""
    g = rng(seed)
    pi = np.zeros((n, quarters))
    u = np.zeros((n, quarters))
    i = np.zeros((n, quarters))
    y10 = np.zeros((n, quarters))
    oil = np.array(scen["oil_shock_pct"], float)
    du = np.array(scen["unemp_change_pp"], float)
    inf_imp = np.array(scen["infl_shock_pp"], float)
    tp = init["tp"] + np.array(scen["tp_change_bp"], float) / 100
    pi_prev = np.full(n, init["pi"])
    i_prev = np.full(n, init["i"])
    v = np.zeros(n)
    for t in range(quarters):
        e_pi = g.choice(p.resid_pi, n) if shocks else 0.0
        e_i = g.choice(p.resid_i, n) if shocks else 0.0
        v = 0.5 * v + (g.choice(p.resid_du, n) if shocks else 0.0)
        u[:, t] = init["u"] + du[t] + v
        oil4 = oil[t] - (oil[t - 4] if t >= 4 else 0.0) + (init["oil4_base"] if t < 4 else 0.0) * (1 - t / 4)
        pi[:, t] = p.c + p.rho * pi_prev + p.kappa * (p.ustar - u[:, t]) + p.theta * oil4 + inf_imp[t] + e_pi
        ygap = -p.okun * (u[:, t] - p.ustar)
        target = p.rf_a + p.rf_b * pi[:, t] + p.rf_c * ygap
        desired = p.rf_rho * i_prev + (1 - p.rf_rho) * target + e_i
        step = np.clip(desired - i_prev, -p.max_step_q, p.max_step_q)
        i[:, t] = np.maximum(p.floor, np.round((i_prev + step) * 4) / 4)
        pi_prev, i_prev = pi[:, t], i[:, t]
    lr = p.rstar + p.pi_star
    for t in range(quarters):
        # expected average short rate over 40 quarters: simulated path to the horizon, then decay to lr
        known = i[:, t:quarters]
        k = known.shape[1]
        tail_h = np.arange(1, 40 - k + 1)
        tail = lr + (i[:, -1:] - lr) * (0.97**tail_h)[None, :]
        y10[:, t] = (known.sum(1) + tail.sum(1)) / 40 + tp[t]
    return {"pi": pi, "u": u, "i": i, "y10": y10}


def run_monte_carlo(
    p: EngineParams,
    init: dict,
    scenarios: dict,
    n_per: int = 10_000,
    quarters: int = 8,
    seed: int | None = None,
) -> dict:
    """Simulate every scenario with shocks (n_per paths) and without shocks (deterministic path)."""
    out = {}
    for k, (name, sc) in enumerate(scenarios.items()):
        out[name] = {
            "mc": simulate(p, init, sc, n_per, quarters, seed=None if seed is None else seed + k),
            "det": simulate(p, init, sc, 1, quarters, shocks=False),
        }
    return out


def mixture(sims: dict, weights: dict[str, float], var: str) -> tuple[np.ndarray, np.ndarray]:
    """Stack all scenario paths with per-path weights w_s / N_s (probability-weighted mixture)."""
    arrs, w = [], []
    tot = sum(weights.values())
    for name, s in sims.items():
        a = s["mc"][var]
        arrs.append(a)
        w.append(np.full(a.shape[0], weights.get(name, 0.0) / tot / a.shape[0]))
    return np.vstack(arrs), np.concatenate(w)


def weighted_quantile(values: np.ndarray, weights: np.ndarray, qs) -> np.ndarray:
    """Column-wise weighted quantiles of (n, T) `values`."""
    out = np.zeros((len(qs), values.shape[1]))
    for t in range(values.shape[1]):
        o = np.argsort(values[:, t])
        cw = np.cumsum(weights[o])
        cw /= cw[-1]
        out[:, t] = np.interp(qs, cw, values[o, t])
    return out


def moves_probabilities(
    i_paths: np.ndarray, weights: np.ndarray, i0: float, step: float = 0.25, within: int = 4, ks=(1, 2, 3, 4)
) -> pd.DataFrame:
    """P(at least k more hikes / cuts of `step` within `within` quarters), from peak / trough."""
    peak = i_paths[:, :within].max(1)
    trough = i_paths[:, :within].min(1)
    hikes = np.floor((peak - i0) / step + 1e-9)
    cuts = np.floor((i0 - trough) / step + 1e-9)
    return pd.DataFrame(
        {
            "P(at least k hikes)": [float(weights[hikes >= k].sum()) for k in ks],
            "P(at least k cuts)": [float(weights[cuts >= k].sum()) for k in ks],
        },
        index=pd.Index(ks, name="k"),
    )


def sahm_trigger(u_paths: np.ndarray, u0: float, threshold: float = 0.5) -> np.ndarray:
    """Sahm-type trigger on quarterly paths: the 2-quarter average of unemployment rises by
    >= threshold pp above its running minimum (starting from u0)."""
    u = np.c_[np.full(len(u_paths), u0), u_paths]
    avg2 = (u[:, 1:] + u[:, :-1]) / 2
    run_min = np.minimum.accumulate(np.c_[np.full(len(u_paths), u0), avg2], axis=1)[:, :-1]
    return ((avg2 - run_min) >= threshold).any(axis=1)


def recession_probability(
    u_paths: np.ndarray, weights: np.ndarray, u0: float, threshold: float = 0.5
) -> float:
    """Weighted share of paths that trigger the Sahm-type rule within the horizon."""
    return float(weights[sahm_trigger(u_paths, u0, threshold)].sum())


def reverse_stress(
    sims: dict,
    base_weights: dict[str, float],
    priced_12m: float,
    hawkish=("sticky", "energy_shock"),
    dovish=("disinflation", "hard_landing"),
) -> dict:
    """Probability on the hawkish group that makes the weighted mean policy rate at 4 quarters equal
    the priced rate; within-group proportions kept as in `base_weights`."""
    mean4 = {k: float(v["mc"]["i"][:, 3].mean()) for k, v in sims.items()}

    def wmean(ph):
        hw = sum(base_weights[k] for k in hawkish) or 1
        dw = sum(base_weights[k] for k in dovish) or 1
        w = {
            **{k: ph * base_weights[k] / hw for k in hawkish},
            **{k: (1 - ph) * base_weights[k] / dw for k in dovish},
        }
        return sum(w[k] * mean4[k] for k in w)

    lo, hi = wmean(0.0), wmean(1.0)
    if not (min(lo, hi) <= priced_12m <= max(lo, hi)):
        return {
            "p_hawkish": None,
            "range": (lo, hi),
            "mean4": mean4,
            "note": "priced rate outside the range spanned by the scenarios",
        }
    grid = np.linspace(0, 1, 1001)
    vals = np.array([wmean(x) for x in grid])
    ph = float(grid[np.argmin(np.abs(vals - priced_12m))])
    return {"p_hawkish": ph, "range": (lo, hi), "mean4": mean4, "note": ""}


def market_mapping(
    d_policy: np.ndarray,
    beta2: tuple[float, float],
    beta10: tuple[float, float],
    eq_beta_real: tuple[float, float],
    d_breakeven: float = 0.0,
) -> pd.DataFrame:
    """Map a change in the expected policy rate (pp) to 2Y/10Y yields (bp) and equities (%):
    d2Y = beta2 * d_policy;  d10Y = beta10 * d_policy;  d_real = d10Y - d_breakeven;
    equity % = b_real * d_real. Bands from +/-1.645 s.e. of each beta (independent; indicative)."""
    rows = []
    for dp in d_policy:
        d2 = beta2[0] * dp
        d10 = beta10[0] * dp
        dr = d10 - d_breakeven
        eq = eq_beta_real[0] * dr
        rows.append(
            {
                "policy change (pp)": dp,
                "2Y (bp)": 100 * d2,
                "2Y band (bp)": f"±{100 * 1.645 * beta2[1] * abs(dp):.0f}",
                "10Y (bp)": 100 * d10,
                "10Y band (bp)": f"±{100 * 1.645 * beta10[1] * abs(dp):.0f}",
                "S&P 500 (%)": eq,
                "S&P band (%)": f"±{1.645 * eq_beta_real[1] * abs(dr):.1f}",
            }
        )
    return pd.DataFrame(rows)
