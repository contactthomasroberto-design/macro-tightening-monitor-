"""Macro regimes (BRIEF §5.9).

1. Two-by-two: growth above/below trend x inflation above/below target (+ margin).
   growth: 4-quarter real GDP growth (or the latest nowcast) vs potential growth (CBO potential).
   inflation: core inflation yoy vs target + margin.
2. Cross-check: two-state Markov-switching model on monthly core inflation (3-month annualised),
   switching mean and variance (Hamilton 1989; statsmodels MarkovRegression).
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from macro.utils import SEED

REGIME_NAMES = {
    (True, False): "Goldilocks (growth ≥ trend, inflation ≤ target)",
    (True, True): "Overheating (growth ≥ trend, inflation > target)",
    (False, True): "Stagflation risk (growth < trend, inflation > target)",
    (False, False): "Disinflationary slowdown (growth < trend, inflation ≤ target)",
}


def two_by_two(
    growth: pd.Series, trend: pd.Series, inflation: pd.Series, target: float, margin: float = 0.5
) -> pd.DataFrame:
    df = pd.concat({"growth": growth, "trend": trend, "inflation": inflation}, axis=1).dropna()
    hi_g = df["growth"] >= df["trend"]
    hi_i = df["inflation"] > target + margin
    df["regime"] = [REGIME_NAMES[(bool(g), bool(i))] for g, i in zip(hi_g, hi_i, strict=True)]
    return df


def markov_inflation(x: pd.Series, k: int = 2) -> dict:
    """Two-regime Markov switching on monthly inflation: x_t = mu_{S_t} + e_t, e_t ~ N(0, s2_{S_t}).
    Returns smoothed probability of the high-mean regime, regime means and expected durations."""
    from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

    y = x.dropna()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mod = MarkovRegression(y, k_regimes=k, trend="c", switching_variance=True)
        np.random.seed(SEED)  # the start-value search draws random parameters
        try:
            res = mod.fit(search_reps=20, disp=False)
        except (np.linalg.LinAlgError, ValueError):
            res = None
    if res is None:
        return {"error": "Markov-switching estimation failed"}
    params = pd.Series(np.asarray(res.params), index=res.model.param_names)
    means = np.array([params[f"const[{j}]"] for j in range(k)])
    hi = int(np.argmax(means))
    probs = res.smoothed_marginal_probabilities
    p_hi = probs[hi] if isinstance(probs, pd.DataFrame) else pd.Series(probs[:, hi], index=y.index)
    P = res.regime_transition[:, :, 0] if res.regime_transition.ndim == 3 else res.regime_transition
    durations = 1 / (1 - np.diag(P))
    return {
        "p_high": p_hi,
        "means": means,
        "high": hi,
        "durations": durations,
        "llf": float(res.llf),
        "n": int(res.nobs),
    }
