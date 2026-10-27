"""Curves, term premium and sovereign stress (BRIEF §5.4).

All yields in percent; spreads and changes reported in basis points where stated.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from macro.utils import Result, expanding_percentile, expanding_zscore

REGIMES = ["bull steepener", "bear steepener", "bull flattener", "bear flattener", "range-bound"]


def us_spreads(y: pd.DataFrame) -> pd.DataFrame:
    """Curve slopes and curvature in bp from daily yields (columns 3m, 2y, 5y, 10y, 30y):
    3m10y = 10y - 3m; 2s10s = 10y - 2y; 5s30s = 30y - 5y; 2s5s10s butterfly = 2*5y - 2y - 10y."""
    return 100 * pd.DataFrame(
        {
            "3m10y": y["10y"] - y["3m"],
            "2s10s": y["10y"] - y["2y"],
            "5s30s": y["30y"] - y["5y"],
            "2s5s10s fly": 2 * y["5y"] - y["2y"] - y["10y"],
        }
    )


def ten_year_decompositions(
    y10: pd.Series, real10: pd.Series, be10: pd.Series, tp: dict[str, pd.Series]
) -> dict:
    """10Y = real yield + breakeven (identity on TIPS-based measures, residual = basis/rounding);
    10Y = expected average short rate + term premium, for each published term-premium model:
    expected component = 10Y - TP (as the models define it)."""
    df = pd.concat({"10y": y10, "real": real10, "breakeven": be10}, axis=1).dropna()
    df["residual"] = df["10y"] - df["real"] - df["breakeven"]
    tps = {}
    for name, s in tp.items():
        d = pd.concat({"10y": y10, "term premium": s}, axis=1).dropna()
        d["expected short rate"] = d["10y"] - d["term premium"]
        tps[name] = d
    return {"real_be": df, "tp": tps}


def classify_regime(
    y2: pd.Series, y10: pd.Series, window: int = 21, threshold_bp: float = 5.0
) -> pd.DataFrame:
    """Curve regime over rolling `window` business days.

    d_slope = change in (10y - 2y), d_level = change in (2y + 10y)/2, both in bp.
    Steepener if d_slope > 0, flattener if < 0; bull if d_level < 0 (yields falling), bear if > 0.
    'range-bound' when |d_slope| < threshold and |d_level| < threshold.
    """
    df = pd.concat({"y2": y2, "y10": y10}, axis=1).dropna()
    slope = 100 * (df["y10"] - df["y2"])
    level = 100 * (df["y10"] + df["y2"]) / 2
    ds, dl = slope.diff(window), level.diff(window)
    reg = np.where(
        ds > 0,
        np.where(dl < 0, "bull steepener", "bear steepener"),
        np.where(dl < 0, "bull flattener", "bear flattener"),
    )
    reg = np.where((ds.abs() < threshold_bp) & (dl.abs() < threshold_bp), "range-bound", reg)
    out = pd.DataFrame({"d_slope_bp": ds, "d_level_bp": dl, "regime": reg}, index=df.index)
    return out.dropna(subset=["d_slope_bp"])


def regime_frequencies(reg: pd.DataFrame, condition: pd.Series | None = None) -> pd.DataFrame:
    """Share of days in each regime, unconditionally and (optionally) when `condition` is True."""
    out = {"all days": reg["regime"].value_counts(normalize=True)}
    if condition is not None:
        c = condition.reindex(reg.index).ffill().fillna(False).astype(bool)
        out["condition true"] = reg.loc[c, "regime"].value_counts(normalize=True)
        out["condition false"] = reg.loc[~c, "regime"].value_counts(normalize=True)
    return (100 * pd.DataFrame(out).reindex(REGIMES).fillna(0.0)).round(1)


def sovereign_stress(
    spreads_bp: pd.DataFrame,
    min_periods: int = 36,
    speed_months: int = 3,
    z_level: float = 2.0,
    pct_level: float = 95.0,
    z_speed: float = 2.0,
) -> dict:
    """Expanding-window z-scores and percentiles (information up to t only), plus a speed signal:
    3-month change standardised by the expanding s.d. of past 3-month changes.
    Stress flag: level z > 2 or percentile > 95, OR speed z > 2."""
    z = spreads_bp.apply(lambda s: expanding_zscore(s, min_periods))
    pct = spreads_bp.apply(lambda s: expanding_percentile(s, min_periods))
    chg = spreads_bp.diff(speed_months)
    speed = chg.apply(lambda s: s / s.expanding(min_periods).std())
    flag_level = (z > z_level) | (pct > pct_level)
    flag_speed = speed > z_speed
    latest = pd.DataFrame(
        {
            "spread (bp)": spreads_bp.iloc[-1],
            "z-score": z.iloc[-1],
            "percentile": pct.iloc[-1],
            f"{speed_months}m change (bp)": chg.iloc[-1],
            "speed z": speed.iloc[-1],
            "level flag": flag_level.iloc[-1],
            "speed flag": flag_speed.iloc[-1],
        }
    )
    return {"z": z, "pct": pct, "speed": speed, "flag": flag_level | flag_speed, "latest": latest}


def duration_factor(y10: pd.DataFrame, window: int = 60) -> Result:
    """Global duration factor: PCA on monthly changes in 10Y yields (one column per country).
    Explained share of PC1 full-sample and rolling over `window` months."""
    d = y10.diff().dropna()
    z = (d - d.mean()) / d.std()
    _, s, vt = np.linalg.svd(z.to_numpy(), full_matrices=False)
    share = float(s[0] ** 2 / (s**2).sum())
    load = pd.Series(vt[0], index=d.columns)
    if load.sum() < 0:
        load = -load
    roll = []
    for end in range(window, len(d) + 1):
        sub = d.iloc[end - window : end]
        zz = (sub - sub.mean()) / sub.std()
        sv = np.linalg.svd(zz.to_numpy(), compute_uv=False)
        roll.append((sub.index[-1], float(sv[0] ** 2 / (sv**2).sum())))
    rs = pd.Series(dict(roll))
    factor = pd.Series(z.to_numpy() @ load.to_numpy(), index=d.index).cumsum()
    return Result(
        "duration_factor",
        share,
        n_obs=len(d),
        n_specs_tried=1,
        extra={
            "loadings": load,
            "rolling_share": rs,
            "factor_cum": factor,
            "window": window,
            "countries": list(d.columns),
            "sample": (d.index[0], d.index[-1]),
        },
        notes=["PCA on standardised monthly changes in 10Y yields; common sample across countries."],
    )
