"""Shared helpers: run mode, disclaimers, run metadata, the common `Result` container,
and small statistical utilities (transforms, HAC OLS, block bootstrap).
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm

from macro.config import ROOT

log = logging.getLogger("macro")

SEED = 20240611  # fixed seed for every stochastic routine (BRIEF §2.11)

DISCLAIMER = (
    "Educational research product. May be revised or discontinued. Not an official view of any "
    "central bank and not investment advice."
)
RESEARCH_SERIES_NOTE = "Research series, may be revised, not an official statistic."
SYNTHETIC_BANNER = "SYNTHETIC DATA — demo mode, numbers are simulated and carry no information about markets"


def mode() -> str:
    """`demo` (synthetic, offline) or `live` (real sources). Default: demo, the safe choice."""
    m = os.environ.get("MACRO_MODE", "demo").strip().lower()
    if m not in {"demo", "live"}:
        raise ValueError(f"MACRO_MODE must be 'demo' or 'live', got {m!r}")
    return m


def is_demo() -> bool:
    return mode() == "demo"


def rng(seed: int | None = None) -> np.random.Generator:
    return np.random.default_rng(SEED if seed is None else seed)


def git_hash() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_metadata(data_vintage: dt.date | str | None = None) -> dict[str, str]:
    """Metadata logged with every output (BRIEF §2.11)."""
    return {
        "git_hash": git_hash(),
        "mode": mode(),
        "data_vintage": str(data_vintage) if data_vintage is not None else "latest",
        "run_timestamp": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@dataclass
class Result:
    """Common container for every model output.

    The UI and the reports only read `Result`s, so every displayed number carries its
    uncertainty, benchmark and provenance. `value` may be a scalar, a Series or a DataFrame.
    """

    name: str
    value: Any
    lower: Any = None
    upper: Any = None
    band_level: float | None = None  # e.g. 0.68 or 0.90
    benchmark: dict[str, Any] = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    as_of: str | None = None
    n_obs: int | None = None
    n_specs_tried: int | None = None
    notes: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("value", "lower", "upper"):
            if isinstance(d[k], pd.Series | pd.DataFrame):
                d[k] = f"<{type(d[k]).__name__} len={len(d[k])}>"
        d.pop("extra", None)
        return d


# --------------------------------------------------------------------------- transforms
PERIODS_PER_YEAR = {"D": 252, "W": 52, "M": 12, "Q": 4}


def yoy(s: pd.Series, periods: int = 12) -> pd.Series:
    """Year-on-year % change: 100 * (x_t / x_{t-periods} - 1)."""
    return 100.0 * (s / s.shift(periods) - 1.0)


def annualised(s: pd.Series, months: int, periods_per_year: int = 12) -> pd.Series:
    """Annualised % change over `months` periods: 100 * ((x_t / x_{t-k})^(ppy/k) - 1)."""
    return 100.0 * ((s / s.shift(months)) ** (periods_per_year / months) - 1.0)


def to_monthly(s: pd.Series, how: str = "mean") -> pd.Series:
    """Resample to month-start index (mean for rates/levels, last for stocks)."""
    r = s.resample("MS")
    return r.mean() if how == "mean" else r.last()


def to_quarterly(s: pd.Series, how: str = "mean") -> pd.Series:
    r = s.resample("QS")
    return r.mean() if how == "mean" else r.last()


def expanding_zscore(s: pd.Series, min_periods: int = 60) -> pd.Series:
    """z_t = (x_t - mean_{<=t}) / sd_{<=t}: uses only information available at t."""
    m = s.expanding(min_periods).mean()
    sd = s.expanding(min_periods).std()
    return (s - m) / sd


def expanding_percentile(s: pd.Series, min_periods: int = 60) -> pd.Series:
    """Percentile rank of x_t within x_{<=t} (0-100)."""
    return s.expanding(min_periods).apply(
        lambda x: 100.0 * (x[:-1] < x[-1]).mean() if len(x) > 1 else np.nan, raw=True
    )


def rolling_percentile(s: pd.Series, window: int) -> pd.Series:
    return s.rolling(window, min_periods=max(10, window // 3)).apply(
        lambda x: 100.0 * (x[:-1] < x[-1]).mean(), raw=True
    )


# --------------------------------------------------------------------------- regressions
@dataclass
class OLSResult:
    params: pd.Series
    bse: pd.Series
    tvalues: pd.Series
    pvalues: pd.Series
    nobs: int
    rsquared: float
    resid: pd.Series
    cov_type: str

    def ci(self, level: float = 0.95) -> pd.DataFrame:
        from scipy import stats

        z = stats.norm.ppf(0.5 + level / 2)
        return pd.DataFrame({"lower": self.params - z * self.bse, "upper": self.params + z * self.bse})


def ols_hac(y: pd.Series, X: pd.DataFrame, maxlags: int | None = None, add_const: bool = True) -> OLSResult:
    """OLS with Newey-West (HAC) standard errors.

    Default bandwidth: floor(4 * (T/100)^(2/9)) (Newey-West 1994 rule of thumb).
    """
    df = pd.concat([y.rename("__y"), X], axis=1).dropna()
    yy = df.pop("__y")
    XX = sm.add_constant(df, has_constant="add") if add_const else df
    T = len(yy)
    if maxlags is None:
        maxlags = int(np.floor(4 * (T / 100.0) ** (2.0 / 9.0)))
    res = sm.OLS(yy, XX).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})
    return OLSResult(
        params=res.params,
        bse=res.bse,
        tvalues=res.tvalues,
        pvalues=res.pvalues,
        nobs=int(res.nobs),
        rsquared=float(res.rsquared),
        resid=res.resid,
        cov_type=f"HAC(maxlags={maxlags})",
    )


def block_bootstrap_indices(
    n: int, block: int, n_boot: int, gen: np.random.Generator | None = None
) -> np.ndarray:
    """Moving-block bootstrap: (n_boot, n) array of indices built from random blocks of length `block`."""
    gen = gen or rng()
    block = max(1, min(block, n))
    n_blocks = int(np.ceil(n / block))
    starts = gen.integers(0, n - block + 1, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)[:, :n]
    return idx


def bootstrap_ci(
    x: np.ndarray,
    stat=np.mean,
    n_boot: int = 2000,
    level: float = 0.90,
    block: int = 1,
    seed: int | None = None,
) -> tuple[float, float, float]:
    """Point estimate and percentile (block-)bootstrap interval for `stat(x)`."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 3:
        return (float(stat(x)) if len(x) else np.nan, np.nan, np.nan)
    idx = block_bootstrap_indices(len(x), block, n_boot, rng(seed))
    draws = np.array([stat(x[i]) for i in idx])
    a = (1 - level) / 2
    return float(stat(x)), float(np.quantile(draws, a)), float(np.quantile(draws, 1 - a))


def last_valid(s: pd.Series) -> tuple[pd.Timestamp | None, float]:
    s = s.dropna()
    if s.empty:
        return None, np.nan
    return s.index[-1], float(s.iloc[-1])


def fmt_date(d: Any) -> str:
    if d is None or (isinstance(d, float) and np.isnan(d)):
        return "n/a"
    return pd.Timestamp(d).strftime("%Y-%m-%d")
