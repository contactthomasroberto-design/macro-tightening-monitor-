"""Monetary-policy module (BRIEF §5.2): rule prescriptions, r* sensitivity, estimated reaction
function, policy gap, priced vs prescribed moves, cross-bank synchronisation.

Notation: i policy rate, pi inflation (yoy, target measure), pi* target, y output gap (% of
potential), u unemployment, u* natural rate, r* neutral real rate. All in percent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from macro.utils import Result, ols_hac


# =========================================================================== rule family
def taylor(pi, y, rstar, pi_star: float = 2.0, a_pi: float = 1.5, a_gap: float = 0.5):
    """Generalised Taylor (1993) rule: i = r* + pi* + a_pi (pi - pi*) + a_gap y.
    With a_pi = 1.5, a_gap = 0.5 this is i = r* + pi + 0.5 (pi - pi*) + 0.5 y."""
    return rstar + pi_star + a_pi * (pi - pi_star) + a_gap * y


def balanced_approach(pi, y, rstar, pi_star: float = 2.0, a_pi: float = 1.5, a_gap: float = 1.0):
    """Yellen (2012) 'balanced approach': Taylor with a gap coefficient of 1."""
    return taylor(pi, y, rstar, pi_star, a_pi, a_gap)


def unemployment_gap_rule(
    pi, u, ustar, rstar, pi_star: float = 2.0, a_pi: float = 1.5, okun: float = 2.0, a_gap: float = 0.5
):
    """Taylor rule with the output gap replaced by Okun's law: y ~= -okun (u - u*)."""
    return taylor(pi, -okun * (u - ustar), rstar, pi_star, a_pi, a_gap)


def first_difference(i_prev, pi, dy, pi_star: float = 2.0, a_pi: float = 0.5, a_gap: float = 0.5):
    """Orphanides (2003)-type change rule: i_t = i_{t-1} + a_pi (pi - pi*) + a_gap dy,
    dy = 4-quarter change in the output gap. Needs no r*. Applied at a quarterly frequency."""
    return i_prev + a_pi * (pi - pi_star) + a_gap * dy


def inertial(i_prev, target, rho: float = 0.85):
    """Smoothed rule: i_t = rho i_{t-1} + (1 - rho) i*_t, with i*_t a Taylor prescription."""
    return rho * i_prev + (1 - rho) * target


def rule_paths(q: pd.DataFrame, rstar: float, params: dict, pi_star: float = 2.0) -> pd.DataFrame:
    """Prescriptions over history (quarterly frame with columns i, pi, y, and optionally u, ustar).

    Inertial and first-difference rules are iterated from the actual rate at each previous quarter
    (one-step prescriptions), the convention of the Fed's Monetary Policy Report rule comparisons.
    """
    t93 = params["taylor1993"]
    ba = params["balanced_approach"]
    ug = params["unemployment_gap"]
    fd = params["first_difference"]
    inr = params["inertial"]
    out = pd.DataFrame(index=q.index)
    out["Taylor (1993)"] = taylor(q["pi"], q["y"], rstar, pi_star, t93["a_pi"], t93["a_gap"])
    out["Balanced approach"] = balanced_approach(q["pi"], q["y"], rstar, pi_star, ba["a_pi"], ba["a_gap"])
    if {"u", "ustar"} <= set(q.columns) and q["u"].notna().any():
        out["Unemployment-gap rule"] = unemployment_gap_rule(
            q["pi"], q["u"], q["ustar"], rstar, pi_star, ug["a_pi"], ug["okun"]
        )
    out["First-difference rule"] = first_difference(
        q["i"].shift(1), q["pi"], q["y"] - q["y"].shift(4), pi_star, fd["a_pi"], fd["a_gap"]
    )
    tgt = taylor(q["pi"], q["y"], rstar, pi_star, inr["a_pi"], inr["a_gap"])
    out["Inertial Taylor"] = inertial(q["i"].shift(1), tgt, inr["rho"])
    return out


def rstar_heatmap(
    pi: float, y: float, i_actual: float, rstar_grid, a_pi_grid, pi_star: float = 2.0, a_gap: float = 0.5
) -> pd.DataFrame:
    """Taylor prescription minus actual rate over (r*, a_pi). Positive = rule above actual."""
    m = np.array([[taylor(pi, y, r, pi_star, a, a_gap) - i_actual for r in rstar_grid] for a in a_pi_grid])
    return pd.DataFrame(m, index=pd.Index(a_pi_grid, name="a_pi"), columns=pd.Index(rstar_grid, name="r*"))


def conclusion_robust(heat: pd.DataFrame, tol: float = 0.0) -> tuple[bool, str]:
    """Does the sign of (rule - actual) hold across the whole (r*, a_pi) range?"""
    v = heat.to_numpy()
    if (v > tol).all():
        return True, "above"
    if (v < -tol).all():
        return True, "below"
    return False, "mixed"


# =========================================================================== reaction function
def reaction_function(q: pd.DataFrame, start=None, end=None, exclude_zlb: float | None = 0.25) -> Result:
    """Estimated partial-adjustment rule (Clarida, Gali and Gertler 2000 form):

        i_t = rho i_{t-1} + (1 - rho)(a + b pi_t + c y_t) + e_t

    estimated linearly as i_t = alpha + rho i_{t-1} + beta pi_t + gamma y_t + e_t (HAC s.e.), then
    b = beta/(1-rho), c = gamma/(1-rho), a = alpha/(1-rho), with delta-method s.e.
    Quarters with i_t and i_{t-1} below `exclude_zlb` are dropped (the rule is censored at the
    lower bound). Taylor principle: H0 b <= 1 against b > 1 (one-sided).
    """
    d = q.loc[start:end, ["i", "pi", "y"]].copy()
    d["i_lag"] = d["i"].shift(1)
    d = d.dropna()
    if exclude_zlb is not None:
        d = d[~((d["i"] < exclude_zlb) & (d["i_lag"] < exclude_zlb))]
    if len(d) < 20:
        return Result("reaction_function", None, n_obs=len(d), notes=["too few observations"])
    regs = ["i_lag", "pi"] + (["y"] if d["y"].std() > 1e-9 else [])  # drop a constant gap (no gap data)
    import statsmodels.api as sm

    X = sm.add_constant(d[regs])
    T = len(d)
    lags = int(np.floor(4 * (T / 100) ** (2 / 9)))
    full = sm.OLS(d["i"], X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    V = full.cov_params().to_numpy()
    params = full.params.to_numpy()
    al, rho, be = params[:3]
    ga = params[3] if "y" in regs else np.nan
    k = 1 - rho
    # long-run coefficients a = alpha/(1-rho), b = beta/(1-rho), c = gamma/(1-rho); delta-method s.e.
    lr = {"a": al / k, "b": be / k, "c": ga / k}
    n = len(regs) + 1
    grads = {"a": np.zeros(n), "b": np.zeros(n)}
    grads["a"][[0, 1]] = [1 / k, al / k**2]
    grads["b"][[1, 2]] = [be / k**2, 1 / k]
    if "y" in regs:
        grads["c"] = np.zeros(n)
        grads["c"][[1, 3]] = [ga / k**2, 1 / k]
    se = {nm: float(np.sqrt(g @ V @ g)) for nm, g in grads.items()}
    se.setdefault("c", np.nan)
    se["rho"] = float(np.sqrt(V[1, 1]))
    tab = pd.DataFrame(
        {"estimate": [rho, lr["a"], lr["b"], lr["c"]], "se": [se["rho"], se["a"], se["b"], se["c"]]},
        index=["rho", "a", "b (inflation)", "c (output gap)"],
    )
    tab["lower"] = tab["estimate"] - 1.645 * tab["se"]
    tab["upper"] = tab["estimate"] + 1.645 * tab["se"]
    t_tp = (lr["b"] - 1) / se["b"]
    p_tp = float(stats.norm.sf(t_tp))
    return Result(
        "reaction_function",
        tab,
        band_level=0.90,
        n_obs=len(d),
        n_specs_tried=1,
        extra={
            "taylor_principle_t": float(t_tp),
            "taylor_principle_p": p_tp,
            "start": d.index[0],
            "end": d.index[-1],
            "r2": float(full.rsquared),
            "fitted": pd.Series(full.fittedvalues, index=d.index),
        },
        notes=[
            "Partial-adjustment rule estimated on quarterly averages, HAC s.e., delta-method s.e. for long-run "
            "coefficients; lower-bound quarters excluded."
        ],
    )


def rolling_reaction(q: pd.DataFrame, window: int = 48, step: int = 2) -> pd.DataFrame:
    """Long-run inflation coefficient b over rolling windows (quarters)."""
    rows = []
    for end in range(window, len(q) + 1, step):
        sub = q.iloc[end - window : end]
        r = reaction_function(sub)
        if r.value is None:
            continue
        b = r.value.loc["b (inflation)"]
        rows.append(
            {
                "date": sub.index[-1],
                "b": b["estimate"],
                "lower": b["lower"],
                "upper": b["upper"],
                "rho": r.value.loc["rho", "estimate"],
            }
        )
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()


# =========================================================================== gaps and pricing
def policy_stance(i: float, pi: float, rstar_range: tuple[float, float]) -> dict:
    """Real policy rate (i - pi, backward-looking) against the r* range."""
    real = i - pi
    lo, hi = rstar_range
    stance = "restrictive" if real > hi else "accommodative" if real < lo else "within the neutral range"
    return {"real_rate": real, "rstar_low": lo, "rstar_high": hi, "stance": stance}


def priced_vs_prescribed(
    i_now: float, priced_12m: float, prescriptions: dict[str, float], step: float = 0.25
) -> pd.DataFrame:
    """Number of `step` moves priced over 12 months vs prescribed by each rule (prescription - i_now)."""
    rows = [{"path": "Market-implied (12m)", "rate": priced_12m, "moves": (priced_12m - i_now) / step}]
    rows += [{"path": k, "rate": v, "moves": (v - i_now) / step} for k, v in prescriptions.items()]
    return pd.DataFrame(rows).set_index("path")


def priced_rate_proxy(y2: float, i_now: float, assumption: dict | None) -> tuple[float, str]:
    """12-month-ahead priced policy rate.

    Preference: a dated OIS-implied value in config/assumptions.yaml. Fallback: the 2-year yield,
    which under a linear expected path from i_now equals the expected rate in 12 months (ignores the
    term premium — a crude proxy, labelled as such).
    """
    if assumption and assumption.get("value") is not None:
        return float(assumption["value"]), f"{assumption.get('source')} (as of {assumption.get('as_of')})"
    return float(y2), "2-year yield proxy (no term-premium adjustment)"


def reverse_inflation(
    i_priced: float, y: float, rstar: float, pi_star: float = 2.0, a_pi: float = 1.5, a_gap: float = 0.5
) -> float:
    """Inflation rate that makes the Taylor rule prescribe the priced rate, given the output gap:
    pi = pi* + (i - r* - pi* - a_gap y) / a_pi."""
    return pi_star + (i_priced - rstar - pi_star - a_gap * y) / a_pi


def reverse_gap(
    i_priced: float, pi: float, rstar: float, pi_star: float = 2.0, a_pi: float = 1.5, a_gap: float = 0.5
) -> float:
    """Output gap that makes the Taylor rule prescribe the priced rate, given inflation."""
    return (i_priced - rstar - pi_star - a_pi * (pi - pi_star)) / a_gap


# =========================================================================== synchronisation and FX
def synchronisation(rates: pd.DataFrame, window: int = 36) -> pd.DataFrame:
    """Cross-bank synchronisation (monthly policy rates, one column per bank):
    - share of banks whose rate rose over the past 12 months (hiking share)
    - average pairwise rolling correlation of 12-month changes."""
    d12 = rates.diff(12)
    share = (d12 > 0).sum(axis=1).where(d12.notna().all(axis=1)) / rates.shape[1]
    cols = list(rates.columns)
    pairs = [(a, b) for k, a in enumerate(cols) for b in cols[k + 1 :]]
    corr = pd.concat([d12[a].rolling(window).corr(d12[b]) for a, b in pairs], axis=1).mean(axis=1)
    return pd.DataFrame({"hiking_share": share, "avg_corr_12m_changes": corr})


def fx_differential_beta(fx: pd.Series, diff: pd.Series, window: int = 104) -> pd.DataFrame:
    """Rolling OLS of weekly FX log changes (%) on weekly changes in the 2Y rate differential (pp):
    dlog FX_t = a + beta d(diff)_t + e_t. 90% bands from HAC s.e."""
    w_fx = 100 * np.log(fx.resample("W-FRI").last()).diff()
    w_d = diff.resample("W-FRI").last().diff()
    df = pd.concat([w_fx.rename("fx"), w_d.rename("d")], axis=1).dropna()
    rows = []
    for end in range(window, len(df) + 1, 4):
        sub = df.iloc[end - window : end]
        r = ols_hac(sub["fx"], sub[["d"]])
        rows.append(
            {
                "date": sub.index[-1],
                "beta": r.params["d"],
                "lower": r.params["d"] - 1.645 * r.bse["d"],
                "upper": r.params["d"] + 1.645 * r.bse["d"],
            }
        )
    return pd.DataFrame(rows).set_index("date") if rows else pd.DataFrame()
