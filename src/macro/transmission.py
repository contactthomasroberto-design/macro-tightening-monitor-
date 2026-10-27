"""Transmission of tightening to markets (BRIEF §5.6).

Returns: equity and FX in % log changes; yields in bp changes. All uncertainty by bootstrap or HAC.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from macro.utils import Result, block_bootstrap_indices, bootstrap_ci, ols_hac, rng

INFLATION_BUCKETS = [(-np.inf, 2.0, "core < 2%"), (2.0, 3.0, "core 2-3%"), (3.0, np.inf, "core > 3%")]


def stock_bond_by_regime(
    eq_ret_m: pd.Series, d10_m: pd.Series, core_yoy: pd.Series, n_boot: int = 1000, block: int = 6
) -> pd.DataFrame:
    """Correlation of monthly equity returns with monthly bond returns (proxied by -d10Y) within
    inflation regimes; block-bootstrap 90% CI. Positive = stocks and bonds fall together."""
    df = pd.concat({"eq": eq_ret_m, "bond": -d10_m, "infl": core_yoy}, axis=1).dropna()
    rows = []
    for lo, hi, label in INFLATION_BUCKETS:
        sub = df[(df["infl"] >= lo) & (df["infl"] < hi)]
        if len(sub) < 24:
            rows.append(
                {"regime": label, "n_months": len(sub), "corr": np.nan, "lower": np.nan, "upper": np.nan}
            )
            continue
        xy = sub[["eq", "bond"]].to_numpy()
        idx = block_bootstrap_indices(len(xy), block, n_boot, rng())
        draws = np.array([np.corrcoef(xy[i, 0], xy[i, 1])[0, 1] for i in idx])
        rows.append(
            {
                "regime": label,
                "n_months": len(sub),
                "corr": float(np.corrcoef(xy[:, 0], xy[:, 1])[0, 1]),
                "lower": float(np.quantile(draws, 0.05)),
                "upper": float(np.quantile(draws, 0.95)),
            }
        )
    return pd.DataFrame(rows).set_index("regime")


def rolling_stock_bond(eq_ret_m: pd.Series, d10_m: pd.Series, window: int = 24) -> pd.Series:
    return eq_ret_m.rolling(window).corr(-d10_m).dropna()


def policy_events(target: pd.Series) -> pd.DataFrame:
    """Dates where the policy target changed, with the size of the move (pp)."""
    d = target.diff()
    ev = d[d.fillna(0) != 0]
    return pd.DataFrame({"move": ev, "type": np.where(ev > 0, "hike", "cut")})


def event_study(
    prices: dict[str, pd.Series],
    kinds: dict[str, str],
    events: pd.DatetimeIndex,
    window: int = 5,
    n_boot: int = 1000,
) -> dict[str, pd.DataFrame]:
    """Cumulative change from day -window-1 to day k in [-window, +window] around each event.
    kinds: 'yield' -> bp change; 'price' -> % log change. Mean path with 90% bootstrap CI over events."""
    out = {}
    for name, s in prices.items():
        s = s.dropna()
        idx = s.index
        paths = []
        for e in events:
            pos = idx.searchsorted(e)
            if pos - window - 1 < 0 or pos + window >= len(idx):
                continue
            base = s.iloc[pos - window - 1]
            seg = s.iloc[pos - window : pos + window + 1].to_numpy()
            chg = 100 * (seg - base) if kinds[name] == "yield" else 100 * (np.log(seg) - np.log(base))
            paths.append(chg)
        if not paths:
            continue
        P = np.array(paths)
        g = rng()
        boot = np.array([P[g.integers(0, len(P), len(P))].mean(0) for _ in range(n_boot)])
        out[name] = pd.DataFrame(
            {
                "mean": P.mean(0),
                "lower": np.quantile(boot, 0.05, axis=0),
                "upper": np.quantile(boot, 0.95, axis=0),
            },
            index=range(-window, window + 1),
        )
        out[name].attrs["n_events"] = len(P)
    return out


def real_yield_betas(
    ret: pd.DataFrame, d_real: pd.Series, d_be: pd.Series, regime: pd.Series | None = None
) -> pd.DataFrame:
    """Weekly returns (%) on weekly changes in the 10Y real yield and breakeven (pp), HAC s.e.:
    r_t = a + b_real d(real)_t + b_be d(be)_t + e_t. A b_real of -10 means a 100bp rise in real
    yields comes with a 10% fall: a 'duration' of about 10 years in equity terms."""
    rows = []
    for name in ret.columns:
        for label, mask in _regime_masks(ret.index, regime):
            df = pd.concat({"r": ret[name], "dr": d_real, "dbe": d_be}, axis=1).dropna()
            df = df[mask.reindex(df.index).fillna(False)] if mask is not None else df
            if len(df) < 52:
                continue
            r = ols_hac(df["r"], df[["dr", "dbe"]])
            rows.append(
                {
                    "asset": name,
                    "regime": label,
                    "n_weeks": r.nobs,
                    "b_real": r.params["dr"],
                    "se_real": r.bse["dr"],
                    "b_breakeven": r.params["dbe"],
                    "se_breakeven": r.bse["dbe"],
                    "r2": r.rsquared,
                }
            )
    return pd.DataFrame(rows)


def _regime_masks(index, regime: pd.Series | None):
    yield "all", None
    if regime is not None:
        reg = regime.reindex(index, method="ffill")
        for v in sorted(reg.dropna().unique()):
            yield str(v), reg == v


def rolling_real_beta(r: pd.Series, d_real: pd.Series, d_be: pd.Series, window: int = 52) -> pd.DataFrame:
    df = pd.concat({"r": r, "dr": d_real, "dbe": d_be}, axis=1).dropna()
    rows = []
    for end in range(window, len(df) + 1, 4):
        sub = df.iloc[end - window : end]
        res = ols_hac(sub["r"], sub[["dr", "dbe"]])
        rows.append(
            {
                "date": sub.index[-1],
                "b_real": res.params["dr"],
                "lower": res.params["dr"] - 1.645 * res.bse["dr"],
                "upper": res.params["dr"] + 1.645 * res.bse["dr"],
            }
        )
    return pd.DataFrame(rows).set_index("date")


def local_projections_surprise(
    responses: dict[str, tuple[pd.Series, str]], surprise: pd.Series, horizons: int = 20
) -> dict:
    """Responses over 0..H business days to a policy-surprise proxy (1-day change in the 2Y yield on
    decision days, pp):  y_{t+h} - y_{t-1} = a_h + b_h s_t + e,  estimated on the event sample, HC1 s.e.
    The proxy mixes surprise and information effects: labelled 'proxy'."""
    out = {}
    s = surprise.dropna()
    for name, (series, kind) in responses.items():
        y = series.dropna()
        rows = []
        for h in range(horizons + 1):
            dep = []
            for d in s.index:
                pos = y.index.searchsorted(d)
                if pos - 1 < 0 or pos + h >= len(y):
                    dep.append(np.nan)
                    continue
                a, b = y.iloc[pos - 1], y.iloc[pos + h]
                dep.append(100 * (b - a) if kind == "yield" else 100 * (np.log(b) - np.log(a)))
            d = pd.DataFrame({"y": dep, "s": s.to_numpy()}, index=s.index).dropna()
            if len(d) < 10:
                continue
            r = sm.OLS(d["y"], sm.add_constant(d[["s"]])).fit(cov_type="HC1")
            rows.append(
                {
                    "h": h,
                    "beta": r.params["s"],
                    "lower": r.params["s"] - 1.645 * r.bse["s"],
                    "upper": r.params["s"] + 1.645 * r.bse["s"],
                    "n": int(r.nobs),
                }
            )
        if rows:
            out[name] = pd.DataFrame(rows).set_index("h")
    return out


def fx_differential_model(fx_m: pd.Series, diff_m: pd.Series, name: str) -> Result:
    """Monthly log FX level on the rate differential (pp):  100 log FX_t = a + b diff_t + u_t (HAC).
    Fitted value = 'differential-implied' level; residual = deviation. Levels regressions of
    persistent series can be spurious: the changes regression is reported alongside."""
    df = pd.concat({"fx": 100 * np.log(fx_m), "diff": diff_m}, axis=1).dropna()
    lv = ols_hac(df["fx"], df[["diff"]])
    ch = ols_hac(df["fx"].diff(), df[["diff"]].diff())
    fitted = lv.params["const"] + lv.params["diff"] * df["diff"]
    sd = float(lv.resid.std())
    implied = np.exp(fitted / 100)
    out = pd.DataFrame(
        {
            "actual": fx_m.reindex(df.index),
            "implied": implied,
            "lower": np.exp((fitted - 1.645 * sd) / 100),
            "upper": np.exp((fitted + 1.645 * sd) / 100),
        }
    )
    dev = float(df["fx"].iloc[-1] - fitted.iloc[-1])
    return Result(
        f"fx_{name}",
        dev,
        n_obs=lv.nobs,
        n_specs_tried=2,
        extra={
            "path": out,
            "levels": {"b": lv.params["diff"], "se": lv.bse["diff"], "r2": lv.rsquared},
            "changes": {"b": ch.params["diff"], "se": ch.bse["diff"], "r2": ch.rsquared},
        },
        notes=["% deviation of the spot rate from the differential-implied level (levels regression, HAC)."],
    )


def bootstrap_mean(x) -> tuple[float, float, float]:
    return bootstrap_ci(np.asarray(x), np.mean, n_boot=1000, level=0.90)
