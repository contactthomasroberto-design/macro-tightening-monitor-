"""Do the models add anything to market prices? Backtests against the hardest benchmark.

1. Fed path. Target: the average effective fed funds rate over the next 12 months. Competitors at
   each monthly origin t (1990 onward, outcome known):
   - market: the 1-year Treasury yield at t (expected average policy rate plus a small term
     premium; the T-bill/fed funds basis is ignored);
   - rule: a partial-adjustment rule i_t = α + ρ i_{t−1} + β π_t + γ y_t estimated on data up to t
     only, iterated 12 months forward with inflation and the output gap held at their last known
     values; inputs lagged for publication (core PCE 1 month, the output gap 4 months);
   - no change: the fed funds rate at t.
2. Inflation. Our 12-month CPI combination forecast against the SPF median (both from the
   inflation module's pseudo-out-of-sample run).

Scores: RMSE, MAE, Diebold-Mariano tests with the Harvey-Leybourne-Newbold correction (squared
loss, HAC variance), and the forecast-encompassing regression

    (realised − benchmark) = a + b (model − benchmark) + e,   Newey-West, h − 1 lags,

where b > 0 means the model carries information the benchmark lacks (b = 1: use the model alone).
Also the hit rate when the two disagree by more than a threshold: did the outcome land on the
model's side of the benchmark? Data are latest vintages (revised), which flatters the model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def dm_test(e_model: np.ndarray, e_bench: np.ndarray, h: int) -> tuple[float, float]:
    """Diebold-Mariano on squared errors, HLN small-sample correction. Positive statistic: the
    model's errors are smaller. Returns (statistic, two-sided p-value)."""
    d = e_bench**2 - e_model**2
    n = len(d)
    dbar = d.mean()
    gamma = [np.mean((d[k:] - dbar) * (d[: n - k] - dbar)) for k in range(h)]
    var = (gamma[0] + 2 * sum(gamma[1:])) / n
    if var <= 0:
        return np.nan, np.nan
    dm = dbar / np.sqrt(var)
    hln = np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    stat = dm * hln
    return float(stat), float(2 * stats.t.sf(abs(stat), df=n - 1))


def encompassing(realised: pd.Series, model: pd.Series, bench: pd.Series, h: int) -> dict:
    """(realised − bench) = a + b (model − bench): b, its Newey-West t-statistic and p-value."""
    import statsmodels.api as sm

    df = pd.concat({"r": realised, "m": model, "b": bench}, axis=1).dropna()
    y = df["r"] - df["b"]
    x = sm.add_constant((df["m"] - df["b"]).rename("gap"))
    fit = sm.OLS(y, x).fit(cov_type="HAC", cov_kwds={"maxlags": max(1, h - 1)})
    return {
        "slope b": float(fit.params["gap"]),
        "t": float(fit.tvalues["gap"]),
        "p (b > 0)": float(stats.norm.sf(fit.tvalues["gap"])),
        "n": int(fit.nobs),
    }


def disagreement_hit_rate(realised, model, bench, threshold: float) -> dict:
    """When |model − bench| > threshold: share of outcomes on the model's side of the benchmark."""
    df = pd.concat({"r": realised, "m": model, "b": bench}, axis=1).dropna()
    big = df[(df["m"] - df["b"]).abs() > threshold]
    if big.empty:
        return {"cases": 0, "model side": np.nan}
    hit = np.sign(big["r"] - big["b"]) == np.sign(big["m"] - big["b"])
    # serial overlap: about one independent case per 12 months of origins
    return {"cases": int(len(big)), "model side": float(hit.mean())}


def fed_panel(
    dff: pd.Series, core_pce: pd.Series, gdp: pd.Series, gdppot: pd.Series, dgs1: pd.Series
) -> pd.DataFrame:
    """Monthly inputs. pi: core PCE y/y lagged 1 month; y: CBO output gap (quarterly, carried over the
    quarter) lagged 4 months; i: monthly average fed funds; mkt: monthly average 1-year yield."""
    m = lambda s: s.dropna().resample("MS").mean()  # noqa: E731
    pce = core_pce.dropna().resample("MS").last()
    pi = (100 * (pce / pce.shift(12) - 1)).shift(1)
    gap_q = 100 * (gdp.dropna().resample("QS").last() / gdppot.dropna().resample("QS").last() - 1)
    y = gap_q.resample("MS").ffill().shift(4)
    return pd.DataFrame({"i": m(dff), "pi": pi, "y": y, "mkt": m(dgs1)})


def rule_forecasts(
    panel: pd.DataFrame, start: str = "1990-01-01", h: int = 12, min_obs: int = 120
) -> pd.DataFrame:
    """Pseudo-out-of-sample: at each origin t, estimate the rule on months up to t, iterate h months."""
    rows = []
    d = panel.copy()
    d["i_lag"] = d["i"].shift(1)
    for t in d.loc[start:].index:
        hist = d.loc[:t].dropna(subset=["i", "i_lag", "pi", "y"])
        if len(hist) < min_obs or pd.isna(d.loc[t, ["i", "pi", "y"]]).any():
            continue
        X = np.column_stack([np.ones(len(hist)), hist[["i_lag", "pi", "y"]].to_numpy()])
        coef, *_ = np.linalg.lstsq(X, hist["i"].to_numpy(), rcond=None)
        a, rho, b, g = coef
        i, path = float(d.loc[t, "i"]), []
        for _ in range(h):
            i = max(0.0, a + rho * i + b * float(d.loc[t, "pi"]) + g * float(d.loc[t, "y"]))
            path.append(i)
        rows.append({"origin": t, "rule": float(np.mean(path)), "rho": float(rho)})
    return pd.DataFrame(rows).set_index("origin")


def fed_backtest(panel: pd.DataFrame, start: str = "1990-01-01", h: int = 12) -> dict:
    target = pd.concat([panel["i"].shift(-k) for k in range(1, h + 1)], axis=1).mean(axis=1, skipna=False)
    rf = rule_forecasts(panel, start, h)
    df = (
        pd.DataFrame(
            {
                "realised": target,
                "market (1Y yield)": panel["mkt"],
                "rule": rf["rule"],
                "no change": panel["i"],
            }
        )
        .loc[start:]
        .dropna()
    )
    return {"forecasts": df, **score_table(df, "market (1Y yield)", ["rule", "no change"], h, threshold=0.5)}


def score_table(df: pd.DataFrame, bench: str, others: list[str], h: int, threshold: float) -> dict:
    r = df["realised"]
    rows = []
    for c in [bench, *others]:
        e = (df[c] - r).to_numpy()
        rows.append(
            {
                "forecast": c,
                "RMSE": float(np.sqrt(np.mean(e**2))),
                "MAE": float(np.mean(np.abs(e))),
                "bias (forecast − realised)": float(e.mean()),
                "n": len(e),
            }
        )
    tab = pd.DataFrame(rows).set_index("forecast")
    tests = []
    for c in others:
        st, p = dm_test((df[c] - r).to_numpy(), (df[bench] - r).to_numpy(), h)
        enc = encompassing(r, df[c], df[bench], h)
        hit = disagreement_hit_rate(r, df[c], df[bench], threshold)
        tests.append(
            {
                "against": bench,
                "forecast": c,
                "DM stat (+ = forecast better)": st,
                "DM p": p,
                **enc,
                f"cases |gap| > {threshold}": hit["cases"],
                "outcome on forecast's side": hit["model side"],
            }
        )
    return {"scores": tab, "tests": pd.DataFrame(tests).set_index("forecast")}


def inflation_vs_spf(oos_forecasts: pd.DataFrame, h: int = 12) -> dict:
    """Our combination (COMB) against the SPF median, same origins and target."""
    f = oos_forecasts[oos_forecasts["h"] == h]
    piv = f.pivot_table(index="origin", columns="model", values="point")
    act = f.groupby("origin")["actual"].first()
    if not {"COMB", "SPF"} <= set(piv.columns):
        return {"forecasts": pd.DataFrame(), "scores": pd.DataFrame(), "tests": pd.DataFrame()}
    df = pd.DataFrame(
        {
            "realised": act,
            "SPF median": piv["SPF"],
            "our combination": piv["COMB"],
            "no change": piv.get("RW"),
        }
    ).dropna()
    return {
        "forecasts": df,
        **score_table(df, "SPF median", ["our combination", "no change"], h, threshold=0.5),
    }
