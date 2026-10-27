"""Forecast evaluation (BRIEF §2.4): point and density accuracy, calibration, and tests.

Point:    RMSE = sqrt(mean(e^2)), MAE = mean(|e|), e = y - yhat.
Density:  Gaussian predictive N(mu, sigma^2):
          log score  LS  = log phi((y - mu)/sigma) - log sigma               (higher is better)
          CRPS       = sigma * [ z (2 Phi(z) - 1) + 2 phi(z) - 1/sqrt(pi) ],  z = (y - mu)/sigma
                       (Gneiting and Raftery 2007; lower is better)
          PIT        = Phi((y - mu)/sigma)  — uniform if the density is calibrated.
Test:     Diebold-Mariano (1995) on loss differential d_t = L(e1_t) - L(e2_t), HAC variance with
          h-1 lags, Harvey-Leybourne-Newbold (1997) small-sample correction, t(T-1) reference.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def rmse(e) -> float:
    e = np.asarray(e, float)
    e = e[~np.isnan(e)]
    return float(np.sqrt(np.mean(e**2))) if len(e) else np.nan


def mae(e) -> float:
    e = np.asarray(e, float)
    e = e[~np.isnan(e)]
    return float(np.mean(np.abs(e))) if len(e) else np.nan


def log_score_normal(y, mu, sigma) -> np.ndarray:
    y, mu, sigma = (np.asarray(a, float) for a in (y, mu, sigma))
    return stats.norm.logpdf(y, loc=mu, scale=sigma)


def crps_normal(y, mu, sigma) -> np.ndarray:
    y, mu, sigma = (np.asarray(a, float) for a in (y, mu, sigma))
    z = (y - mu) / sigma
    return sigma * (z * (2 * stats.norm.cdf(z) - 1) + 2 * stats.norm.pdf(z) - 1 / np.sqrt(np.pi))


def pit_normal(y, mu, sigma) -> np.ndarray:
    y, mu, sigma = (np.asarray(a, float) for a in (y, mu, sigma))
    return stats.norm.cdf((y - mu) / sigma)


def pit_uniformity_pvalue(pit) -> float:
    """Kolmogorov-Smirnov p-value of PITs against U(0,1). Overlapping multi-step forecasts make
    PITs autocorrelated, so this p-value is indicative only (stated on the page)."""
    p = np.asarray(pit, float)
    p = p[~np.isnan(p)]
    return float(stats.kstest(p, "uniform").pvalue) if len(p) > 5 else np.nan


def diebold_mariano(e1, e2, h: int = 1, loss: str = "se") -> dict:
    """DM test of equal accuracy. Negative statistic => model 1 more accurate than model 2."""
    e1, e2 = np.asarray(e1, float), np.asarray(e2, float)
    m = ~(np.isnan(e1) | np.isnan(e2))
    e1, e2 = e1[m], e2[m]
    T = len(e1)
    if T < 10:
        return {"dm": np.nan, "pvalue": np.nan, "T": T}
    d = (e1**2 - e2**2) if loss == "se" else (np.abs(e1) - np.abs(e2))
    dbar = d.mean()
    dc = d - dbar
    gamma = [np.dot(dc[k:], dc[: T - k]) / T for k in range(h)]
    var = gamma[0] + 2 * sum(gamma[1:])
    if var <= 0:
        var = gamma[0]
    dm = dbar / np.sqrt(var / T)
    hln = np.sqrt((T + 1 - 2 * h + h * (h - 1) / T) / T)
    stat = hln * dm
    p = 2 * stats.t.sf(abs(stat), df=T - 1)
    return {"dm": float(stat), "pvalue": float(p), "T": T}


def evaluate_density(df: pd.DataFrame, y: str = "actual", mu: str = "point", sigma: str = "sigma") -> dict:
    ok = df[[y, mu, sigma]].dropna()
    e = ok[y] - ok[mu]
    return {
        "n": len(ok),
        "rmse": rmse(e),
        "mae": mae(e),
        "log_score": float(np.mean(log_score_normal(ok[y], ok[mu], ok[sigma]))) if len(ok) else np.nan,
        "crps": float(np.mean(crps_normal(ok[y], ok[mu], ok[sigma]))) if len(ok) else np.nan,
        "pit_ks_p": pit_uniformity_pvalue(pit_normal(ok[y], ok[mu], ok[sigma])),
    }


def scoreboard(
    errors: pd.DataFrame, benchmark: str, h: int, densities: dict[str, pd.DataFrame] | None = None
) -> pd.DataFrame:
    """Table per model: RMSE, MAE, relative RMSE vs benchmark, DM vs benchmark, density scores.

    errors: columns = models, rows = forecast origins, values = actual - forecast (aligned sample).
    """
    common = errors.dropna()
    rows = []
    for m in errors.columns:
        r = {"model": m, "n": len(common), "rmse": rmse(common[m]), "mae": mae(common[m])}
        r["rel_rmse_vs_" + benchmark] = r["rmse"] / rmse(common[benchmark]) if benchmark in common else np.nan
        if m != benchmark and benchmark in common:
            dm = diebold_mariano(common[m], common[benchmark], h=h)
            r["dm_stat"], r["dm_pvalue"] = dm["dm"], dm["pvalue"]
        if densities and m in densities:
            dd = densities[m].loc[densities[m].index.intersection(common.index)]
            de = evaluate_density(dd)
            r["log_score"], r["crps"], r["pit_ks_p"] = de["log_score"], de["crps"], de["pit_ks_p"]
        rows.append(r)
    return pd.DataFrame(rows).set_index("model")
