"""Bank of England-style fan charts (BRIEF §5.8; Britton, Fisher and Whitley 1998).

Two-piece normal (TPN) with mode mu and left/right scales s1, s2:

    f(x) = A exp(-(x - mu)^2 / (2 s1^2))   for x <  mu
    f(x) = A exp(-(x - mu)^2 / (2 s2^2))   for x >= mu,      A = sqrt(2/pi) / (s1 + s2)

BoE parametrisation with an overall uncertainty sigma and skew gamma in (-1, 1):
    s1 = sigma / sqrt(1 + gamma),  s2 = sigma / sqrt(1 - gamma)
    mean - mode = sqrt(2/pi) (s2 - s1)

The central projection is the MODE. Skew comes from probability-weighted alternative scenarios:
the mean is the probability-weighted path, the mode the modal path, and gamma solves
mean - mode = sqrt(2/pi)(s2 - s1) for the given sigma. Sigma comes from past forecast errors.

Bands: nine equal-tailed central intervals of 10%, 20%, ..., 90% probability. (The BoE draws its
bands to include the mode; under skew the two conventions differ slightly — stated on the page.)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize, stats

BAND_PROBS = tuple(round(0.1 * k, 1) for k in range(1, 10))  # 10% ... 90%
SQRT_2_OVER_PI = np.sqrt(2 / np.pi)


def scales(sigma: float, gamma: float) -> tuple[float, float]:
    return sigma / np.sqrt(1 + gamma), sigma / np.sqrt(1 - gamma)


def tpn_pdf(x, mode: float, s1: float, s2: float):
    x = np.asarray(x, float)
    A = SQRT_2_OVER_PI / (s1 + s2)
    s = np.where(x < mode, s1, s2)
    return A * np.exp(-((x - mode) ** 2) / (2 * s**2))


def tpn_cdf(x, mode: float, s1: float, s2: float):
    x = np.asarray(x, float)
    w1 = 2 * s1 / (s1 + s2)
    w2 = 2 * s2 / (s1 + s2)
    return np.where(x < mode, w1 * stats.norm.cdf((x - mode) / s1), 1 - w2 * stats.norm.sf((x - mode) / s2))


def tpn_ppf(p, mode: float, s1: float, s2: float):
    """Inverse CDF. F(mode) = s1/(s1+s2)."""
    p = np.asarray(p, float)
    pm = s1 / (s1 + s2)
    left = mode + s1 * stats.norm.ppf(np.clip(p * (s1 + s2) / (2 * s1), 1e-12, 1 - 1e-12))
    right = mode + s2 * stats.norm.isf(np.clip((1 - p) * (s1 + s2) / (2 * s2), 1e-12, 1 - 1e-12))
    return np.where(p < pm, left, right)


def tpn_mean(mode: float, s1: float, s2: float) -> float:
    return mode + SQRT_2_OVER_PI * (s2 - s1)


def gamma_from_skew(sigma: float, mean_minus_mode: float, max_abs: float = 0.95) -> float:
    """Solve sqrt(2/pi)(s2(gamma) - s1(gamma)) = mean - mode for gamma in (-max_abs, max_abs).
    Clipped at the bounds when the requested skew is larger than achievable."""
    if sigma <= 0:
        return 0.0

    def f(g):
        s1, s2 = scales(sigma, g)
        return SQRT_2_OVER_PI * (s2 - s1) - mean_minus_mode

    lo, hi = -max_abs, max_abs
    if f(lo) > 0:
        return lo
    if f(hi) < 0:
        return hi
    return float(optimize.brentq(f, lo, hi))


def fan_quantiles(modes: pd.Series, sigmas: pd.Series, means: pd.Series | None = None) -> pd.DataFrame:
    """Quantile table for each horizon: columns = lower/upper edges of the 10%...90% bands plus
    'mode', 'mean', 'gamma'. With `means` the skew follows mean - mode, otherwise symmetric."""
    rows = []
    for t in modes.index:
        mode, sig = float(modes[t]), float(sigmas[t])
        mm = float(means[t]) - mode if means is not None else 0.0
        g = gamma_from_skew(sig, mm) if sig > 0 else 0.0
        s1, s2 = scales(sig, g) if sig > 0 else (1e-9, 1e-9)
        r = {"mode": mode, "mean": tpn_mean(mode, s1, s2), "gamma": g, "s1": s1, "s2": s2}
        for p in BAND_PROBS:
            lo, hi = tpn_ppf([0.5 - p / 2, 0.5 + p / 2], mode, s1, s2)
            r[round(0.5 - p / 2, 2)] = float(lo)
            r[round(0.5 + p / 2, 2)] = float(hi)
        r[0.5] = float(tpn_ppf(0.5, mode, s1, s2))
        rows.append(r)
    return pd.DataFrame(rows, index=modes.index)


HOW_TO_READ = (
    "How to read this fan: the dark central line is the most likely path (the mode). Each pair of "
    "shaded bands adds 10% probability; the whole fan covers 90%. Outcomes outside the fan are expected "
    "about one time in ten, so the fan is NOT the full range of possible outcomes. Asymmetry comes from "
    "the probability-weighted scenarios; the width from past forecast errors."
)
