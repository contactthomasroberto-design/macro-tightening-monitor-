"""Inflation module (BRIEF §5.1).

Pure functions on monthly DataFrames built by `macro.panels`. Each function documents the
formula it implements. Results are latest-vintage unless real-time vintages are supplied.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from macro import evaluation as ev
from macro.utils import OLSResult, Result, annualised, ols_hac, yoy

COMPONENTS = ["headline", "core", "energy", "food", "services", "goods"]


# =========================================================================== decomposition
def log_change(s: pd.Series, k: int = 1) -> pd.Series:
    """100 * (log x_t - log x_{t-k})."""
    return 100 * (np.log(s) - np.log(s.shift(k)))


def decomposition(panel: pd.DataFrame) -> pd.DataFrame:
    """Year-on-year % change of each available component."""
    cols = [c for c in COMPONENTS + ["pce", "core_pce"] if c in panel]
    return pd.DataFrame({c: yoy(panel[c]) for c in cols})


def momentum(s: pd.Series) -> pd.DataFrame:
    """1m, 3m and 6m annualised rates and the yoy rate of a price index:
    a_k = 100 * ((x_t / x_{t-k})^(12/k) - 1)."""
    return pd.DataFrame(
        {"1m ann.": annualised(s, 1), "3m ann.": annualised(s, 3), "6m ann.": annualised(s, 6), "yoy": yoy(s)}
    )


def underlying(panel: pd.DataFrame) -> pd.DataFrame:
    """US underlying measures in yoy terms. Median and trimmed-mean CPI are published as
    annualised m/m rates r_t; yoy = 100 * (prod_{j<12} (1 + r_{t-j}/1200) - 1)."""
    out = {}
    for c in ("median", "trimmed"):
        if c in panel:
            g = (1 + panel[c] / 1200).rolling(12).apply(np.prod, raw=True)
            out[c] = 100 * (g - 1)
    if "sticky" in panel:
        out["sticky"] = panel["sticky"]
    if "core" in panel:
        out["core"] = yoy(panel["core"])
    return pd.DataFrame(out)


def broadening(panel: pd.DataFrame, target: float) -> Result:
    """Share of components whose 6m annualised rate exceeds the target.
    Components: food, energy, services, core goods (+ median/trimmed where available)."""
    rates = {}
    for c in ("food", "energy", "services", "goods"):
        if c in panel:
            rates[c] = annualised(panel[c], 6)
    for c in ("median", "trimmed"):
        if c in panel:
            rates[c] = panel[c].rolling(6).mean()
    df = pd.DataFrame(rates)
    share = (df > target).sum(axis=1).where(df.notna().all(axis=1)) / df.shape[1]
    return Result(
        "broadening",
        share.dropna(),
        n_obs=df.shape[1],
        notes=[
            f"Share of {df.shape[1]} components above target on a 6m annualised basis: "
            f"coarse with few components ({', '.join(df.columns)})."
        ],
    )


# =========================================================================== persistence
def fit_ar_bic(y: pd.Series, max_p: int = 12) -> tuple[int, OLSResult]:
    """AR(p) with intercept, p chosen by BIC on a common sample (first max_p obs dropped)."""
    y = y.dropna()
    X_all = pd.concat({f"L{j}": y.shift(j) for j in range(1, max_p + 1)}, axis=1)
    base = pd.concat([y.rename("y"), X_all], axis=1).dropna()
    best = None
    for p in range(1, max_p + 1):
        X = np.column_stack([np.ones(len(base)), base[[f"L{j}" for j in range(1, p + 1)]].to_numpy()])
        beta, *_ = np.linalg.lstsq(X, base["y"].to_numpy(), rcond=None)
        resid = base["y"].to_numpy() - X @ beta
        T = len(resid)
        bic = T * np.log(resid @ resid / T) + (p + 1) * np.log(T)
        if best is None or bic < best[0]:
            best = (bic, p)
    assert best is not None
    p = best[1]
    res = ols_hac(base["y"], base[[f"L{j}" for j in range(1, p + 1)]])
    return p, res


def half_life(phis: np.ndarray, horizon: int = 240) -> float:
    """Months until the impulse response of an AR(p) to a unit shock first falls below 0.5."""
    p = len(phis)
    irf = np.zeros(horizon + p)
    irf[p - 1] = 1.0
    for t in range(p, horizon + p):
        irf[t] = sum(phis[j] * irf[t - 1 - j] for j in range(p))
    path = irf[p - 1 :]
    below = np.where(path < 0.5)[0]
    return float(below[0]) if len(below) else np.inf


def persistence(series_mm: pd.Series, max_p: int = 12, window: int = 120) -> Result:
    """Persistence of monthly annualised inflation.

    rho = sum_j phi_j from y_t = c + sum_{j<=p} phi_j y_{t-j} + e_t (p by BIC, HAC s.e.);
    se(rho) = sqrt(1' V 1). Rolling rho over `window` months with p fixed at the full-sample BIC
    choice exposes drifts in persistence (a de-anchoring symptom).
    """
    y = series_mm.dropna()
    p, res = fit_ar_bic(y, max_p)
    names = [f"L{j}" for j in range(1, p + 1)]
    phis = res.params[names].to_numpy()
    cov = _hac_cov(y, p)
    rho = float(phis.sum())
    se = float(np.sqrt(np.ones(p) @ cov @ np.ones(p)))
    roll_rho, roll_se, idx = [], [], []
    for end in range(window, len(y) + 1, 3):
        yy = y.iloc[end - window : end]
        X = pd.concat({f"L{j}": yy.shift(j) for j in range(1, p + 1)}, axis=1)
        r = ols_hac(yy, X)
        c = _hac_cov(yy, p)
        roll_rho.append(float(r.params[names].sum()))
        roll_se.append(float(np.sqrt(np.ones(p) @ c @ np.ones(p))))
        idx.append(yy.index[-1])
    roll = pd.DataFrame({"rho": roll_rho, "se": roll_se}, index=idx)
    roll["lower"] = roll["rho"] - 1.645 * roll["se"]
    roll["upper"] = roll["rho"] + 1.645 * roll["se"]
    return Result(
        "persistence",
        rho,
        lower=rho - 1.645 * se,
        upper=rho + 1.645 * se,
        band_level=0.90,
        n_obs=res.nobs,
        n_specs_tried=max_p,
        extra={"p": p, "half_life_months": half_life(phis), "rolling": roll, "window": window, "phis": phis},
        notes=[
            f"AR({p}) chosen by BIC among p=1..{max_p}; HAC standard errors; rolling window {window} months."
        ],
    )


def _hac_cov(y: pd.Series, p: int) -> np.ndarray:
    import statsmodels.api as sm

    X = pd.concat({f"L{j}": y.shift(j) for j in range(1, p + 1)}, axis=1)
    df = pd.concat([y.rename("y"), X], axis=1).dropna()
    T = len(df)
    lags = int(np.floor(4 * (T / 100) ** (2 / 9)))
    r = sm.OLS(df["y"], sm.add_constant(df.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return r.cov_params().iloc[1:, 1:].to_numpy()


# =========================================================================== energy pass-through
def energy_passthrough(panel: pd.DataFrame, lags: int = 6, split: str = "2020-01-01") -> Result:
    """Distributed lag of headline-minus-core monthly inflation on local-currency oil:

        (dlog P^head_t - dlog P^core_t) = a + sum_{j=0..L} b_j dlog Oil_{t-j} + e_t

    (all in %). Cumulative pass-through B = sum b_j, se(B) = sqrt(1'V1) with HAC V.
    Reported for the full sample and for pre/post `split` to check stability.
    """
    import statsmodels.api as sm

    y = log_change(panel["headline"]) - log_change(panel["core"])
    oil = log_change(panel["oil"])
    X = pd.concat({f"oil_L{j}": oil.shift(j) for j in range(lags + 1)}, axis=1)
    df = pd.concat([y.rename("y"), X], axis=1).dropna()
    rows, curves = [], {}
    for label, sub in (
        ("full", df),
        (f"pre-{split[:4]}", df[df.index < split]),
        (f"post-{split[:4]}", df[df.index >= split]),
    ):
        if len(sub) < 3 * (lags + 2):
            rows.append(
                {
                    "sample": label,
                    "n": len(sub),
                    "cumulative": np.nan,
                    "se": np.nan,
                    "lower": np.nan,
                    "upper": np.nan,
                }
            )
            continue
        T = len(sub)
        mlag = int(np.floor(4 * (T / 100) ** (2 / 9)))
        r = sm.OLS(sub["y"], sm.add_constant(sub.drop(columns="y"))).fit(
            cov_type="HAC", cov_kwds={"maxlags": mlag}
        )
        b = r.params.iloc[1:].to_numpy()
        V = r.cov_params().iloc[1:, 1:].to_numpy()
        cum = b.sum()
        se = float(np.sqrt(np.ones(len(b)) @ V @ np.ones(len(b))))
        rows.append(
            {
                "sample": label,
                "n": T,
                "start": sub.index[0].date(),
                "end": sub.index[-1].date(),
                "cumulative": cum,
                "se": se,
                "lower": cum - 1.96 * se,
                "upper": cum + 1.96 * se,
            }
        )
        cs = np.cumsum(b)
        cvar = [float(np.ones(k + 1) @ V[: k + 1, : k + 1] @ np.ones(k + 1)) for k in range(len(b))]
        curves[label] = pd.DataFrame(
            {"cum": cs, "lower": cs - 1.96 * np.sqrt(cvar), "upper": cs + 1.96 * np.sqrt(cvar)},
            index=range(lags + 1),
        )
    tab = pd.DataFrame(rows).set_index("sample")
    full = tab.loc["full"]
    return Result(
        "energy_passthrough",
        float(full["cumulative"]),
        lower=float(full["lower"]),
        upper=float(full["upper"]),
        band_level=0.95,
        n_obs=int(full["n"]),
        n_specs_tried=1,
        extra={"table": tab, "curves": curves, "lags": lags},
        notes=[
            "Cumulative effect of a 1% oil-price change on headline-minus-core inflation (pp, monthly), lags 0-6, HAC s.e."
        ],
    )


# =========================================================================== supply side: GSCPI LP
def local_projection(
    y_level: pd.Series, shock: pd.Series, horizons: int = 12, n_lags: int = 3, level: float = 0.90
) -> pd.DataFrame:
    """Jorda (2005) local projections of cumulative log change on a shock:

        100*(log y_{t+h} - log y_{t-1}) = a_h + b_h s_t + sum_{j=1..L} c_j dlog y_{t-j} + sum d_j s_{t-j} + e_{t+h}

    HAC s.e. with h+1 lags. Returns b_h with bands for h = 0..horizons.
    """
    dly = log_change(y_level)
    ly = 100 * np.log(y_level)
    z = stats.norm.ppf(0.5 + level / 2)
    rows = []
    for h in range(horizons + 1):
        dep = ly.shift(-h) - ly.shift(1)
        X = pd.concat(
            {
                "shock": shock,
                **{f"dy_L{j}": dly.shift(j) for j in range(1, n_lags + 1)},
                **{f"s_L{j}": shock.shift(j) for j in range(1, n_lags + 1)},
            },
            axis=1,
        )
        r = ols_hac(dep, X, maxlags=h + 1)
        rows.append(
            {
                "h": h,
                "beta": r.params["shock"],
                "se": r.bse["shock"],
                "lower": r.params["shock"] - z * r.bse["shock"],
                "upper": r.params["shock"] + z * r.bse["shock"],
                "n": r.nobs,
            }
        )
    return pd.DataFrame(rows).set_index("h")


def supply_passthrough(panel: pd.DataFrame, horizons: int = 12) -> Result:
    """GSCPI local projections on producer prices and core goods (NY Fed SR 1017 approach, simplified)."""
    out = {}
    if "gscpi" not in panel:
        return Result("supply_passthrough", None, notes=["GSCPI unavailable"])
    for c in ("ppi", "goods"):
        if c in panel and panel[c].notna().sum() > 60:
            out[c] = local_projection(panel[c], panel["gscpi"], horizons)
    n = int(min(v["n"].min() for v in out.values())) if out else 0
    return Result(
        "supply_passthrough",
        out,
        band_level=0.90,
        n_obs=n,
        n_specs_tried=1,
        notes=[
            "Response (cumulative %, log points) to a one-standard-deviation GSCPI reading; 3 lags of each control."
        ],
    )


# =========================================================================== expectations factor
def expectations_factor(
    exp: pd.DataFrame,
    realized_yoy: pd.Series,
    anchor_col: str = "SPF_CPI10",
    window: int = 60,
    pre_end: str = "2019-12-01",
) -> Result:
    """Common inflation-expectations factor (CIE-style, simplified to a static factor):

    1. standardise each measure on the balanced sample: z_it = (x_it - m_i)/s_i
    2. first principal component f_t of z (sign: positive loading on the anchor measure)
    3. rescale to the anchor's units: F_t = m_a + s_a * f_t / sd(f)
    4. de-anchoring: rolling OLS dF_t = a + beta * dpi_t + e_t over `window` months (HAC s.e.);
       flag when beta > 0 is significant at 10% AND beta exceeds the 95th percentile of its
       pre-`pre_end` rolling distribution.

    The Fed Board CIE uses a dynamic factor model with time-varying loadings and is revised each
    update; this static PCA is an educational approximation. Research series, not official.
    """
    df = exp.dropna()
    if df.shape[0] < 36 or df.shape[1] < 3:
        return Result("expectations_factor", None, notes=["not enough expectation measures"])
    m, s = df.mean(), df.std()
    z = (df - m) / s
    u, sv, vt = np.linalg.svd(z.to_numpy() - z.to_numpy().mean(0), full_matrices=False)
    load = pd.Series(vt[0], index=df.columns)
    f = pd.Series(u[:, 0] * sv[0], index=df.index)
    if anchor_col in load and load[anchor_col] < 0:
        load, f = -load, -f
    share = float(sv[0] ** 2 / (sv**2).sum())
    anchor = df[anchor_col] if anchor_col in df else df.iloc[:, 0]
    F = anchor.mean() + anchor.std() * (f - f.mean()) / f.std()
    dF = F.diff()
    dpi = realized_yoy.reindex(F.index).diff()
    betas, ses, idx = [], [], []
    for end in range(window, len(F)):
        sub_y, sub_x = dF.iloc[end - window + 1 : end + 1], dpi.iloc[end - window + 1 : end + 1]
        r = ols_hac(sub_y, sub_x.to_frame("dpi"))
        betas.append(r.params["dpi"])
        ses.append(r.bse["dpi"])
        idx.append(F.index[end])
    roll = pd.DataFrame({"beta": betas, "se": ses}, index=idx)
    roll["lower"] = roll["beta"] - 1.645 * roll["se"]
    roll["upper"] = roll["beta"] + 1.645 * roll["se"]
    pre = roll.loc[:pre_end, "beta"]
    p95 = float(pre.quantile(0.95)) if len(pre) > 12 else np.nan
    last = roll.iloc[-1] if len(roll) else None
    flag = bool(last is not None and last["lower"] > 0 and last["beta"] > p95)
    return Result(
        "expectations_factor",
        F,
        n_obs=len(df),
        n_specs_tried=1,
        extra={
            "loadings": load,
            "explained_share": share,
            "rolling_beta": roll,
            "pre_p95": p95,
            "deanchoring_flag": flag,
            "measures": list(df.columns),
            "window": window,
        },
        notes=[
            "Static first principal component across survey and market measures, rescaled to "
            f"{anchor_col}; balanced sample from {df.index[0].date()}. Research series, may be revised, not an official statistic."
        ],
    )


# =========================================================================== forecasting
HORIZONS_EVAL = (1, 3, 6, 12)
MODELS = ("RW", "AR", "PC", "MF", "EN", "COMB")
MODEL_LABELS = {
    "RW": "Random walk",
    "AR": "AR (BIC)",
    "PC": "Phillips curve",
    "MF": "Mixed-frequency (daily oil)",
    "EN": "Elastic net",
    "COMB": "Equal-weight combination",
    "SPF": "SPF consensus",
}


def realtime_value(s: pd.Series, freq: str, lag_days: int, info_dates: pd.DatetimeIndex) -> pd.Series:
    """For each information date d, the latest observation of `s` published by d."""
    from macro.data.vintages import available_at

    s = s.dropna()
    avail = available_at(s, freq, lag_days)
    tab = pd.DataFrame({"avail": avail.to_numpy(), "v": s.to_numpy()}).sort_values("avail")
    q = pd.DataFrame({"d": info_dates}).sort_values("d")
    m = pd.merge_asof(q, tab, left_on="d", right_on="avail", direction="backward")
    return pd.Series(m["v"].to_numpy(), index=info_dates)


@dataclass
class ForecastInputs:
    """Monthly features at forecast origins t (month of the last published CPI). Values are those
    available on the information date d_t = end of month t + CPI release lag."""

    X: pd.DataFrame  # features at origin t
    target: pd.Series  # yoy headline indexed by reference month
    level: pd.Series  # headline index
    components: pd.DataFrame  # m/m % changes of core, energy, food (reference months)


def build_inputs(
    panel: pd.DataFrame,
    exp_long: pd.Series | None,
    ugap: pd.Series,
    oil_daily: pd.Series,
    release_lags: dict[str, tuple[str, int]],
    cpi_lag: int = 15,
) -> ForecastInputs:
    """Assemble real-time features. `release_lags` maps feature name -> (freq, lag_days)."""
    head = panel["headline"]
    months = head.dropna().index
    info = months + pd.offsets.MonthEnd(0) + pd.Timedelta(days=cpi_lag)
    pi = yoy(head)
    feat = {
        "pi": pi.reindex(months),
        "pi_core": yoy(panel["core"]).reindex(months) if "core" in panel else np.nan,
        "mm3": annualised(head, 3).reindex(months),
    }
    oil_m = panel["oil"]
    feat["oil12"] = log_change(oil_m, 12).reindex(months)
    feat["oil3"] = log_change(oil_m, 3).reindex(months)
    feat["oil_m1"] = log_change(oil_m, 1).reindex(months)
    feat["gscpi"] = (
        realtime_value(panel["gscpi"], *release_lags["gscpi"], info).to_numpy()
        if "gscpi" in panel
        else np.nan
    )
    feat["ugap"] = realtime_value(ugap, *release_lags["ugap"], info).to_numpy()
    feat["exp"] = (
        realtime_value(exp_long, *release_lags["exp"], info).to_numpy() if exp_long is not None else np.nan
    )
    # month-to-date oil: average of daily Brent from the start of month t+1 to the information date,
    # relative to month t's average (the 'inside the month' energy signal of Knotek-Zaman)
    od = oil_daily.dropna()
    mtd = []
    for t, d in zip(months, info, strict=True):
        nxt = t + pd.offsets.MonthBegin(1)
        w = od[(od.index >= nxt) & (od.index <= d)]
        base = oil_m.get(t, np.nan)
        mtd.append(100 * (np.log(w.mean()) - np.log(base)) if len(w) and base == base else np.nan)
    feat["oil_mtd"] = mtd
    X = pd.DataFrame(feat, index=months)
    comps = pd.DataFrame({c: log_change(panel[c]) for c in ("core", "energy", "food") if c in panel})
    comps["headline"] = log_change(head)
    return ForecastInputs(X=X, target=pi, level=head, components=comps)


def _lstsq(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    X1 = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    resid = y - X1 @ beta
    return beta, float(np.sqrt(resid @ resid / max(len(y) - X1.shape[1], 1)))


def _direct_pairs(X: pd.DataFrame, target: pd.Series, cols: list[str], h: int, t: pd.Timestamp):
    """Training pairs (x_s, y_{s+h}) with s+h <= t (outcome known at origin t)."""
    y_lead = target.shift(-h).reindex(X.index)
    df = pd.concat([X[cols], y_lead.rename("y")], axis=1).loc[: t - pd.DateOffset(months=h)].dropna()
    return df[cols].to_numpy(), df["y"].to_numpy()


def _ar_forecast(
    X: pd.DataFrame, target: pd.Series, h: int, t: pd.Timestamp, max_p: int = 6
) -> tuple[float, float]:
    lagged = pd.concat({f"pi_L{j}": X["pi"].shift(j) for j in range(max_p)}, axis=1)
    best = None
    for p in range(1, max_p + 1):
        cols = [f"pi_L{j}" for j in range(p)]
        Xa, ya = _direct_pairs(lagged, target, cols, h, t)
        if len(ya) < 36:
            continue
        beta, sd = _lstsq(Xa, ya)
        T = len(ya)
        bic = T * np.log(sd**2) + (p + 1) * np.log(T)
        if best is None or bic < best[0]:
            xt = lagged.loc[t, cols].to_numpy(dtype=float)
            best = (bic, float(beta[0] + xt @ beta[1:]), sd)
    return (best[1], best[2]) if best else (np.nan, np.nan)


def _reg_forecast(
    X: pd.DataFrame, target: pd.Series, cols: list[str], h: int, t: pd.Timestamp
) -> tuple[float, float]:
    cols = [c for c in cols if X[c].notna().any()]
    Xa, ya = _direct_pairs(X, target, cols, h, t)
    if len(ya) < 36:
        return np.nan, np.nan
    beta, sd = _lstsq(Xa, ya)
    xt = X.loc[t, cols].to_numpy(dtype=float)
    if np.isnan(xt).any():
        return np.nan, np.nan
    return float(beta[0] + xt @ beta[1:]), sd


def _mf_forecast(inp: ForecastInputs, h: int, t: pd.Timestamp, window: int = 120) -> tuple[float, float]:
    """Knotek-Zaman-style parsimonious nowcast (simplified):

        dlog P^head_{t+k} = w_c c_{t+k} + w_e e_{t+k} + w_f f_{t+k}      (weights by OLS, no constant)
        c, f at their trailing 12-month average;  e_{t+1} = g * oil_mtd_t  (g by OLS of energy m/m on
        oil m/m), e_{t+k} = 0 for k > 1 (oil assumed flat — no futures curve in the free data).
    The yoy forecast compounds the monthly path onto the last published index level.
    """
    comps = inp.components.loc[:t].dropna().iloc[-window:]
    if len(comps) < 36 or "energy" not in comps:
        return np.nan, np.nan
    A = comps[["core", "energy", "food"]].to_numpy()
    w, *_ = np.linalg.lstsq(A, comps["headline"].to_numpy(), rcond=None)
    xy = pd.concat([comps["energy"], inp.X["oil_m1"]], axis=1).dropna()
    g = (
        float(np.dot(xy.iloc[:, 0], xy.iloc[:, 1]) / np.dot(xy.iloc[:, 1], xy.iloc[:, 1]))
        if len(xy) > 24
        else 0.0
    )
    c_bar = comps["core"].iloc[-12:].mean()
    f_bar = comps["food"].iloc[-12:].mean()
    mtd = inp.X.loc[t, "oil_mtd"]
    path = []
    for k in range(1, h + 1):
        e_k = g * mtd if (k == 1 and mtd == mtd) else 0.0
        path.append(w[0] * c_bar + w[1] * e_k + w[2] * f_bar)
    lvl = inp.level
    if t not in lvl.index:
        return np.nan, np.nan
    target_month = t + pd.DateOffset(months=h)
    base_idx = target_month - pd.DateOffset(months=12)
    if base_idx <= t:
        base = lvl.get(base_idx, np.nan)
        fc_level = lvl[t] * np.exp(np.sum(path) / 100)
    else:  # base month also in the future: compound from the same path
        fc_level = np.exp(np.sum(path[-12:]) / 100)
        base = 1.0
    # in-sample s.d. of the one-step monthly error of this recipe (k=1 uses realised oil as a proxy
    # for the month-to-date signal; k>1 omits energy), accumulated over the h months
    trend = w[0] * comps["core"].rolling(12).mean().shift(1) + w[2] * comps["food"].rolling(12).mean().shift(
        1
    )
    e1 = comps["headline"] - trend - w[1] * g * inp.X["oil_m1"].reindex(comps.index)
    ek = comps["headline"] - trend
    sd1, sdk = float(np.nanstd(e1)), float(np.nanstd(ek))
    resid_sd = float(np.sqrt(sd1**2 + (h - 1) * sdk**2)) if h <= 12 else np.nan
    return float(100 * (fc_level / base - 1)), resid_sd


def _en_model(X: pd.DataFrame, target: pd.Series, h: int, t: pd.Timestamp, cols: list[str]):
    from sklearn.linear_model import ElasticNetCV
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    Xa, ya = _direct_pairs(X, target, cols, h, t)
    if len(ya) < 60:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = make_pipeline(
            StandardScaler(),
            ElasticNetCV(l1_ratio=[0.2, 0.5, 0.9], alphas=30, cv=TimeSeriesSplit(5), max_iter=5000),
        )
        model.fit(Xa, ya)
    resid_sd = float(np.std(ya - model.predict(Xa)))
    return model, resid_sd


def en_features(X: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    lags = pd.concat({f"pi_L{j}": X["pi"].shift(j) for j in range(6)}, axis=1)
    Z = pd.concat([X, lags], axis=1)
    cols = [
        c
        for c in ["pi_core", "mm3", "oil12", "oil3", "gscpi", "ugap", "exp", *lags.columns]
        if Z[c].notna().any()
    ]
    return Z, cols


def pseudo_oos(
    inp: ForecastInputs,
    start: str = "2005-01-01",
    horizons=HORIZONS_EVAL,
    refit_every: int = 12,
    spf: pd.Series | None = None,
) -> dict:
    """Expanding-window pseudo out-of-sample evaluation (latest-vintage data, release-lag aware).

    Returns {"forecasts": long DataFrame (origin, h, model, point, sigma, actual), "scores": {h: table}}.
    sigma for density scores = RMSE of the model's own past OOS errors at that horizon (outcomes
    known by the origin, >= 24 of them), else its in-sample residual s.d.
    """
    X = inp.X
    Z, en_cols = en_features(X)
    origins = X.loc[start:].index
    last_known = inp.target.dropna().index.max()
    rows = []
    en_cache: dict[int, tuple] = {}
    for k, t in enumerate(origins):
        for h in horizons:
            tgt_date = t + pd.DateOffset(months=h)
            actual = inp.target.get(tgt_date, np.nan) if tgt_date <= last_known else np.nan
            fc = {
                "RW": (X.loc[t, "pi"], np.nan),
                "AR": _ar_forecast(X, inp.target, h, t),
                "PC": _reg_forecast(X, inp.target, ["pi", "ugap", "oil12", "exp"], h, t),
                "MF": _mf_forecast(inp, h, t),
            }
            if k % refit_every == 0 or h not in en_cache:
                en_cache[h] = _en_model(Z, inp.target, h, t, en_cols)
            if en_cache[h] is not None:
                xt = Z.loc[[t], en_cols].to_numpy(dtype=float)
                fc["EN"] = (
                    (float(en_cache[h][0].predict(xt)[0]), en_cache[h][1])
                    if not np.isnan(xt).any()
                    else (np.nan, np.nan)
                )
            else:
                fc["EN"] = (np.nan, np.nan)
            comb = [fc[m][0] for m in ("AR", "PC", "MF", "EN") if fc[m][0] == fc[m][0]]
            fc["COMB"] = (float(np.mean(comb)) if comb else np.nan, np.nan)
            if spf is not None and h == 12:
                fc["SPF"] = (spf.get(t, np.nan), np.nan)
            for m, (pt, sd) in fc.items():
                rows.append(
                    {"origin": t, "h": h, "model": m, "point": pt, "insample_sd": sd, "actual": actual}
                )
    fcs = pd.DataFrame(rows)
    fcs["error"] = fcs["actual"] - fcs["point"]
    fcs["sigma"] = _oos_sigma(fcs)
    scores = {}
    for h in horizons:
        sub = fcs[fcs["h"] == h]
        errs = sub.pivot(index="origin", columns="model", values="error")
        dens = {m: g.set_index("origin")[["actual", "point", "sigma"]] for m, g in sub.groupby("model")}
        scores[h] = ev.scoreboard(errs, benchmark="RW", h=h, densities=dens)
    return {"forecasts": fcs, "scores": scores, "start": start, "n_origins": len(origins)}


def _oos_sigma(fcs: pd.DataFrame, min_n: int = 24) -> pd.Series:
    out = pd.Series(np.nan, index=fcs.index)
    for (_model, h), g in fcs.groupby(["model", "h"]):
        g = g.sort_values("origin")
        known_at = g["origin"] + pd.DateOffset(months=int(h))
        errs = g["error"].to_numpy()
        for i, (idx, t) in enumerate(zip(g.index, g["origin"], strict=True)):
            mask = (known_at.to_numpy() <= t) & ~np.isnan(errs)
            past = errs[mask]
            if len(past) >= min_n:
                out[idx] = float(np.sqrt(np.mean(past**2)))
            else:
                sd = g["insample_sd"].iloc[i]
                out[idx] = sd * 1.25 if sd == sd and sd > 0 else np.nan
    return out


def latest_forecasts(inp: ForecastInputs, oos: dict, horizons=range(1, 13)) -> pd.DataFrame:
    """Forecasts from the last origin for h = 1..12, sigma from the full OOS error history
    (RMSE at the nearest evaluated horizon, interpolated)."""
    X = inp.X
    Z, en_cols = en_features(X)
    t = X["pi"].dropna().index.max()
    fcs = oos["forecasts"]
    rm = (
        fcs.dropna(subset=["error"])
        .groupby(["model", "h"])["error"]
        .apply(lambda e: float(np.sqrt(np.mean(e**2))))
    )
    rows = []
    for h in horizons:
        en = _en_model(Z, inp.target, h, t, en_cols)
        fc = {
            "RW": X.loc[t, "pi"],
            "AR": _ar_forecast(X, inp.target, h, t)[0],
            "PC": _reg_forecast(X, inp.target, ["pi", "ugap", "oil12", "exp"], h, t)[0],
            "MF": _mf_forecast(inp, h, t)[0],
            "EN": float(en[0].predict(Z.loc[[t], en_cols].to_numpy(dtype=float))[0])
            if en is not None
            else np.nan,
        }
        fc["COMB"] = float(np.nanmean([fc[m] for m in ("AR", "PC", "MF", "EN")]))
        for m, v in fc.items():
            hs = np.array(sorted({hh for (mm, hh) in rm.index if mm == m}))
            vals = np.array([rm[(m, hh)] for hh in hs]) if len(hs) else np.array([])
            sig = float(np.interp(h, hs, vals)) if len(hs) else np.nan
            rows.append(
                {
                    "origin": t,
                    "target_date": t + pd.DateOffset(months=h),
                    "h": h,
                    "model": m,
                    "point": v,
                    "sigma": sig,
                }
            )
    return pd.DataFrame(rows)


def prob_exceed(point: float, sigma: float, threshold: float) -> float:
    """P(pi > threshold) under N(point, sigma^2)."""
    if not (sigma == sigma and sigma > 0):
        return np.nan
    return float(1 - stats.norm.cdf((threshold - point) / sigma))
