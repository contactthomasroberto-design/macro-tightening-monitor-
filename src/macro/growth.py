"""Growth: mixed-frequency dynamic-factor nowcast with news decomposition, and Growth-at-Risk
(BRIEF §5.5).

Nowcast (NY Fed Staff Nowcast 2.0 spirit, simplified): statsmodels DynamicFactorMQ on a small
monthly panel plus quarterly real GDP growth (annualised), factors Global / Soft / Nominal / Labor,
AR(2) factors, AR(1) idiosyncratic errors, EM estimation. The nowcast is the model's predicted GDP
growth for the target quarter given the data published by the information date; its standard error
gives 50% and 68% bands. News: the change in the nowcast between two information sets equals the
sum of (actual - model forecast) x weight over newly released data (statsmodels `news`), grouped
by release category, plus the effect of revisions.

Growth-at-Risk (Adrian, Boyarchenko and Giannone 2019): quantile regressions of average annualised
growth over the next h quarters on current growth and NFCI; a skewed t distribution is fitted to the
5/25/75/95% conditional quantiles; expected shortfall at 5%; recursive backtest with PIT and log score.
We use the Jones-Faddy skew t (closed form via the incomplete beta function), not the
Azzalini-Capitanio skew t used in the paper (stated).
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import optimize, stats

from macro import evaluation as ev
from macro.utils import Result

# series -> (transform, release category); transforms: dlog = 100*dlog, diff = first difference, level
GROWTH_SPEC: dict[str, tuple[str, str]] = {
    "PAYEMS": ("dlog", "labor"),
    "UNRATE": ("diff", "labor"),
    "ICSA": ("dlog", "labor"),
    "UMCSENT": ("diff", "surveys"),
    "GACDFSA066MSFRBPHI": ("level", "surveys"),
    "GACDINA066MSFRBNY": ("level", "surveys"),
    "INDPRO": ("dlog", "production"),
    "RSAFS": ("dlog", "consumption"),
    "PCEC96": ("dlog", "consumption"),
    "HOUST": ("dlog", "housing"),
    "BOPTEXP": ("dlog", "trade"),
    "CPIAUCSL": ("dlog", "prices"),
    "PPIFIS": ("dlog", "prices"),
}
GDP_ID = "GDPC1"
CATEGORY_FACTOR = {"surveys": "Soft", "prices": "Nominal", "labor": "Labor"}


def factor_structure() -> dict[str, list[str]]:
    """Every series loads on Global; surveys also on Soft, prices on Nominal, labor on Labor."""
    fac = {}
    for sid, (_, cat) in GROWTH_SPEC.items():
        fac[sid] = ["Global"] + ([CATEGORY_FACTOR[cat]] if cat in CATEGORY_FACTOR else [])
    fac[GDP_ID] = ["Global"]
    return fac


def transform(
    raw_m: pd.DataFrame, gdp_q: pd.Series, start: str = "1990-02"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monthly panel (PeriodIndex 'M') and quarterly GDP growth (PeriodIndex 'Q', annualised %)."""
    cols = {}
    for sid, (tr, _) in GROWTH_SPEC.items():
        if sid not in raw_m:
            continue
        s = raw_m[sid]
        cols[sid] = 100 * np.log(s).diff() if tr == "dlog" else s.diff() if tr == "diff" else s
    M = pd.DataFrame(cols).loc[start:]
    M.index = pd.PeriodIndex(M.index, freq="M")
    q = (400 * np.log(gdp_q).diff()).to_frame(GDP_ID).loc[start[:4] :]
    q.index = pd.PeriodIndex(q.index, freq="Q")
    return M, q


def _extend(M: pd.DataFrame, Q: pd.DataFrame, through: pd.Period) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reindex both frames through `through` (a quarter) so the target quarter exists (NaN)."""
    m_idx = pd.period_range(M.index[0], through.asfreq("M", "end"), freq="M")
    q_idx = pd.period_range(Q.index[0], through, freq="Q")
    return M.reindex(m_idx), Q.reindex(q_idx)


def fit_dfm(M: pd.DataFrame, Q: pd.DataFrame, maxiter: int = 200, min_obs: int = 36):
    """EM estimation. Series with fewer than `min_obs` observations at the fit date are left out
    (e.g. PPI final demand before 2012); the fitted column set is reused when the model is applied."""
    from statsmodels.tsa.statespace.dynamic_factor_mq import DynamicFactorMQ

    M = M[[c for c in M.columns if M[c].notna().sum() >= min_obs]]
    fac = {k: v for k, v in factor_structure().items() if k in M.columns or k == GDP_ID}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mod = DynamicFactorMQ(
            M, endog_quarterly=Q, factors=fac, factor_orders=2, idiosyncratic_ar1=True, standardize=True
        )
        return mod.fit(disp=False, maxiter=maxiter)


def monthly_columns(res) -> list[str]:
    return [c for c in res.model.endog_names if c != GDP_ID]


def apply(res, M: pd.DataFrame, Q: pd.DataFrame):
    M = M.reindex(columns=monthly_columns(res))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return res.apply(M, endog_quarterly=Q, retain_standardization=True)


def nowcast(res, M: pd.DataFrame, Q: pd.DataFrame, target: pd.Period) -> dict:
    """Predicted annualised GDP growth for quarter `target` given (M, Q), with 50%/68% bands."""
    Mx, Qx = _extend(M, Q, target)
    r = apply(res, Mx, Qx)
    month = target.asfreq("M", "end")
    p = r.get_prediction(start=month, end=month)
    mu = float(p.predicted_mean[GDP_ID].iloc[0])
    se = float(p.se_mean[GDP_ID].iloc[0])
    z50 = stats.norm.ppf(0.75)
    return {
        "target": target,
        "point": mu,
        "se": se,
        "lo50": mu - z50 * se,
        "hi50": mu + z50 * se,
        "lo68": mu - se,
        "hi68": mu + se,
    }


def news_decomposition(
    res, old: tuple[pd.DataFrame, pd.DataFrame], new: tuple[pd.DataFrame, pd.DataFrame], target: pd.Period
) -> dict:
    """Nowcast change between two information sets, by release category.

    total change = sum of news impacts (new releases) + revision impacts; categories from GROWTH_SPEC.
    """
    Mo, Qo = _extend(*old, target)
    Mn, Qn = _extend(*new, target)
    ro = apply(res, Mo, Qo)
    month = target.asfreq("M", "end")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        nw = ro.news(
            Mn, endog_quarterly=Qn, impact_date=month, impacted_variable=GDP_ID, comparison_type="updated"
        )
    prev = float(nw.prev_impacted_forecasts.loc[month, GDP_ID])
    post = float(nw.post_impacted_forecasts.loc[month, GDP_ID])
    det = nw.details_by_impact.reset_index() if nw.details_by_impact is not None else pd.DataFrame()
    by_cat: dict[str, float] = {}
    rows = []
    if not det.empty:
        for _, r in det.iterrows():
            var = r["updated variable"]
            cat = GROWTH_SPEC.get(var, ("", "gdp"))[1] if var != GDP_ID else "gdp"
            by_cat[cat] = by_cat.get(cat, 0.0) + float(r["impact"])
            rows.append(
                {
                    "variable": var,
                    "category": cat,
                    "reference": str(r["update date"]),
                    "actual": r["observed"],
                    "expected": r["forecast (prev)"],
                    "news": r["news"],
                    "weight": r["weight"],
                    "impact": r["impact"],
                }
            )
    revisions = post - prev - sum(by_cat.values())
    if abs(revisions) > 1e-6:
        by_cat["revisions"] = revisions
    return {
        "prev": prev,
        "post": post,
        "change": post - prev,
        "by_category": by_cat,
        "details": pd.DataFrame(rows),
    }


# ---------------------------------------------------------------------------- real-time evaluation
def ar_benchmark(gdp_growth: pd.Series, last_known: pd.Period, target: pd.Period) -> float:
    """AR(1) on quarterly annualised growth, iterated from the last published quarter to the target."""
    y = gdp_growth.loc[:last_known].dropna()
    if len(y) < 20:
        return np.nan
    X = np.column_stack([np.ones(len(y) - 1), y.iloc[:-1].to_numpy()])
    c, phi = np.linalg.lstsq(X, y.iloc[1:].to_numpy(), rcond=None)[0]
    f = float(y.iloc[-1])
    for _ in range((target - last_known).n):
        f = c + phi * f
    return f


# ---------------------------------------------------------------------------- Growth-at-Risk
QUANTILES = (0.05, 0.25, 0.50, 0.75, 0.95)


def gar_frame(gdp_q: pd.Series, nfci_q: pd.Series, h: int) -> pd.DataFrame:
    """y_{t+h} = average annualised growth over t+1..t+h = (400/h)(log GDP_{t+h} - log GDP_t);
    regressors: current annualised q/q growth and NFCI (quarterly average)."""
    lg = np.log(gdp_q)
    df = pd.DataFrame(
        {
            "y_fwd": 400.0 / h * (lg.shift(-h) - lg),
            "g": 400.0 * lg.diff(),
            "nfci": nfci_q,
        }
    )
    return df


def quantile_fit(df: pd.DataFrame, quantiles=QUANTILES) -> dict[float, np.ndarray]:
    import statsmodels.api as sm

    d = df.dropna()
    X = sm.add_constant(d[["g", "nfci"]])
    out = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for q in quantiles:
            out[q] = sm.QuantReg(d["y_fwd"], X).fit(q=q, max_iter=5000).params.to_numpy()
    return out


def predict_quantiles(coefs: dict[float, np.ndarray], x: dict) -> pd.Series:
    """Conditional quantiles at x = {'g':..,'nfci':..}, sorted to remove quantile crossing."""
    v = np.array([c[0] + c[1] * x["g"] + c[2] * x["nfci"] for c in coefs.values()])
    return pd.Series(np.sort(v), index=list(coefs.keys()))


class SkewT:
    """Jones and Faddy (2003) skew t with location/scale, in closed form.

    If B ~ Beta(a, b) then T = sqrt(a+b) (2B - 1) / (2 sqrt(B (1 - B))) has the JF skew-t law, so
    Q(u) = loc + scale * g(I^{-1}_{a,b}(u)) with I the regularised incomplete beta function and
    F(x) = I_{a,b}(1/2 (1 + z / sqrt(a + b + z^2))), z = (x - loc)/scale. a = b is symmetric
    (Student t with 2a d.o.f.); a < b skews left.
    """

    def __init__(self, a: float, b: float, loc: float, scale: float):
        self.a, self.b, self.loc, self.scale = float(a), float(b), float(loc), float(scale)

    def ppf(self, u):
        from scipy.special import betaincinv

        B = betaincinv(self.a, self.b, np.asarray(u, float))
        t = np.sqrt(self.a + self.b) * (2 * B - 1) / (2 * np.sqrt(B * (1 - B)))
        return self.loc + self.scale * t

    def cdf(self, x):
        from scipy.special import betainc

        z = (np.asarray(x, float) - self.loc) / self.scale
        return betainc(self.a, self.b, 0.5 * (1 + z / np.sqrt(self.a + self.b + z**2)))

    def logpdf(self, x):
        from scipy.special import betaln

        a, b = self.a, self.b
        z = (np.asarray(x, float) - self.loc) / self.scale
        r = z / np.sqrt(a + b + z**2)
        logc = (a + b - 1) * np.log(2) + betaln(a, b) + 0.5 * np.log(a + b)
        return (a + 0.5) * np.log1p(r) + (b + 0.5) * np.log1p(-r) - logc - np.log(self.scale)

    def pdf(self, x):
        return np.exp(self.logpdf(x))


SHAPE_BOUNDS = (0.75, 40.0)  # bounds on a, b keep tails and skew in a plausible range


def fit_skewt(q: pd.Series) -> dict:
    """Fit the JF skew t (a, b, loc, scale) to the 5/25/75/95% conditional quantiles by bounded
    least squares (ABG match these four quantiles). Returns parameters, a frozen distribution and
    the RMS fitting error."""
    taus = np.array([0.05, 0.25, 0.75, 0.95])
    target = q.loc[list(taus)].to_numpy()
    med = float(q.get(0.5, np.median(target)))
    iqr = max(target[2] - target[1], 1e-2)
    lo, hi = np.log(SHAPE_BOUNDS[0]), np.log(SHAPE_BOUNDS[1])

    def loss(p):
        d = SkewT(np.exp(p[0]), np.exp(p[1]), p[2], np.exp(p[3]))
        return float(np.sum((d.ppf(taus) - target) ** 2))

    best = None
    for a0, b0 in ((3, 3), (2, 6), (6, 2)):
        x0 = [np.log(a0), np.log(b0), med, np.log(iqr / 1.35)]
        r = optimize.minimize(
            loss,
            x0,
            method="L-BFGS-B",
            bounds=[(lo, hi), (lo, hi), (None, None), (np.log(1e-3), np.log(100))],
        )
        if best is None or r.fun < best.fun:
            best = r
    a, b, loc, sc = np.exp(best.x[0]), np.exp(best.x[1]), best.x[2], np.exp(best.x[3])
    return {
        "a": a,
        "b": b,
        "loc": loc,
        "scale": sc,
        "dist": SkewT(a, b, loc, sc),
        "fit_error": float(np.sqrt(best.fun / 4)),
    }


def expected_shortfall(dist, alpha: float = 0.05, n: int = 400) -> float:
    """ES_alpha = (1/alpha) * integral_0^alpha Q(u) du (mean growth in the worst alpha share of outcomes)."""
    u = (np.arange(n) + 0.5) / n * alpha
    return float(np.mean(dist.ppf(u)))


def growth_at_risk(gdp_q: pd.Series, nfci_q: pd.Series, h: int = 4) -> Result:
    """Current conditional growth distribution at horizon h."""
    df = gar_frame(gdp_q, nfci_q, h)
    coefs = quantile_fit(df)
    xnow = df[["g", "nfci"]].dropna().iloc[-1]
    q = predict_quantiles(coefs, xnow.to_dict())
    st = fit_skewt(q)
    es = expected_shortfall(st["dist"])
    coef_tab = pd.DataFrame(coefs, index=["const", "current growth", "NFCI"]).T
    coef_tab.index.name = "quantile"
    return Result(
        f"gar_h{h}",
        float(st["dist"].ppf(0.05)),
        lower=float(q[0.05]),
        upper=float(q[0.95]),
        band_level=0.90,
        n_obs=int(df.dropna().shape[0]),
        n_specs_tried=1,
        extra={
            "quantiles": q,
            "skewt": {k: v for k, v in st.items() if k != "dist"},
            "dist": st["dist"],
            "expected_shortfall_5": es,
            "coefficients": coef_tab,
            "x_now": xnow,
            "h": h,
            "date": df[["g", "nfci"]].dropna().index[-1],
        },
        notes=[
            f"Quantile regressions of average growth over the next {h} quarter(s) on current growth and NFCI; "
            "Jones-Faddy skew t fitted to the 5/25/75/95% quantiles (approximation of ABG's skew t)."
        ],
    )


def gar_backtest(
    gdp_q: pd.Series, nfci_q: pd.Series, h: int = 4, start: str = "2000-01-01", min_obs: int = 60
) -> dict:
    """Recursive out-of-sample backtest: at each origin t, fit on pairs whose outcome is known by t,
    predict the distribution of y_{t+h}, then score the realised outcome (PIT, log score). The
    unconditional benchmark fits the same skew t to unconditional sample quantiles."""
    df = gar_frame(gdp_q, nfci_q, h)
    rows = []
    for t in df.loc[start:].index:
        known = df.loc[: t - pd.DateOffset(months=3 * h)].dropna()
        if len(known) < min_obs or pd.isna(df.loc[t, "y_fwd"]) or df.loc[t, ["g", "nfci"]].isna().any():
            continue
        coefs = quantile_fit(known)
        q = predict_quantiles(coefs, df.loc[t, ["g", "nfci"]].to_dict())
        dist = fit_skewt(q)["dist"]
        uq = pd.Series(np.quantile(known["y_fwd"], QUANTILES), index=QUANTILES)
        udist = fit_skewt(uq)["dist"]
        y = df.loc[t, "y_fwd"]
        rows.append(
            {
                "origin": t,
                "actual": y,
                "q05": q[0.05],
                "median": q[0.5],
                "q95": q[0.95],
                "pit": float(dist.cdf(y)),
                "log_score": float(dist.logpdf(y)),
                "pit_uncond": float(udist.cdf(y)),
                "log_score_uncond": float(udist.logpdf(y)),
            }
        )
    bt = pd.DataFrame(rows).set_index("origin")
    summ = {}
    if not bt.empty:
        summ = {
            "n": len(bt),
            "mean_log_score": float(bt["log_score"].mean()),
            "mean_log_score_uncond": float(bt["log_score_uncond"].mean()),
            "pit_ks_p": ev.pit_uniformity_pvalue(bt["pit"]),
            "coverage_90": float(((bt["actual"] >= bt["q05"]) & (bt["actual"] <= bt["q95"])).mean()),
            "share_below_q05": float((bt["actual"] < bt["q05"]).mean()),
        }
    return {"table": bt, "summary": summ}


def info_dates(q: pd.Period) -> dict[str, pd.Timestamp]:
    """Information dates for nowcasting quarter q: end of its 1st and 2nd months, and 25 days after
    the quarter ends (just before the advance GDP release ~30 days after quarter end)."""
    m1 = q.asfreq("M", "start")
    return {
        "end of month 1": (m1).to_timestamp(how="end").normalize(),
        "end of month 2": (m1 + 1).to_timestamp(how="end").normalize(),
        "pre-release": q.to_timestamp(how="end").normalize() + pd.Timedelta(days=25),
    }


def realtime_evaluation(
    vintage_fn,
    gdp_growth: pd.Series,
    quarters: pd.PeriodIndex,
    refit_years: int = 5,
    spf_cq: pd.Series | None = None,
) -> dict:
    """Pseudo real-time evaluation: for each target quarter and information date, rebuild the data
    set published by that date (release lags), nowcast with parameters estimated on the data
    available at the start of the current `refit_years` block, and compare with the outcome
    (latest-vintage GDP). Benchmarks: AR(1) on published GDP; SPF current-quarter mean (mid-quarter)."""
    rows = []
    fitted = {}
    for q in quarters:
        block = (q.year - quarters[0].year) // refit_years
        if block not in fitted:
            fit_date = pd.Timestamp(f"{quarters[0].year + block * refit_years}-01-01")
            M0, Q0 = vintage_fn(fit_date)
            fitted[block] = fit_dfm(M0, Q0, maxiter=60)
        res = fitted[block]
        actual = gdp_growth.get(q, np.nan)
        for label, d in info_dates(q).items():
            M, Q = vintage_fn(d)
            last_known = Q[GDP_ID].dropna().index.max()
            if last_known >= q:
                continue
            nc = nowcast(res, M, Q, q)
            row = {
                "quarter": q,
                "horizon": label,
                "info_date": d,
                "nowcast": nc["point"],
                "se": nc["se"],
                "actual": actual,
                "AR(1)": ar_benchmark(Q[GDP_ID], last_known, q),
            }
            if spf_cq is not None and label != "end of month 1":
                row["SPF"] = spf_cq.get(q, np.nan)
            rows.append(row)
    df = pd.DataFrame(rows)
    df["err_dfm"] = df["actual"] - df["nowcast"]
    df["err_ar"] = df["actual"] - df["AR(1)"]
    if "SPF" in df:
        df["err_spf"] = df["actual"] - df["SPF"]
    scores = []
    for hz, g in df.groupby("horizon", sort=False):
        g = g.dropna(subset=["actual"])
        r = {
            "horizon": hz,
            "n": len(g),
            "rmse DFM": ev.rmse(g["err_dfm"]),
            "rmse AR(1)": ev.rmse(g["err_ar"]),
            "mae DFM": ev.mae(g["err_dfm"]),
            "mae AR(1)": ev.mae(g["err_ar"]),
        }
        dm = ev.diebold_mariano(g["err_dfm"], g["err_ar"], h=1)
        r["DM vs AR p"] = dm["pvalue"]
        if "err_spf" in g and g["err_spf"].notna().sum() > 10:
            r["rmse SPF"] = ev.rmse(g["err_spf"])
            r["DM vs SPF p"] = ev.diebold_mariano(g["err_dfm"], g["err_spf"], h=1)["pvalue"]
        dens = g.dropna(subset=["se"])
        r["log score DFM"] = float(np.mean(ev.log_score_normal(dens["actual"], dens["nowcast"], dens["se"])))
        r["coverage 68%"] = float((np.abs(dens["err_dfm"]) <= dens["se"]).mean())
        scores.append(r)
    return {"table": df, "scores": pd.DataFrame(scores).set_index("horizon"), "refits": len(fitted)}


def weekly_history(res, vintage_fn, end: pd.Timestamp, weeks: int = 12) -> pd.DataFrame:
    """Nowcast at each of the last `weeks` Fridays with the news decomposition vs the previous week.
    When the target quarter rolls over (GDP released), the decomposition restarts."""
    dates = pd.date_range(end=end, periods=weeks + 1, freq="W-FRI")
    rows = []
    prev_data, prev_target = None, None
    for d in dates:
        M, Q = vintage_fn(d)
        target = Q[GDP_ID].dropna().index.max() + 1
        nc = nowcast(res, M, Q, target)
        row = {
            "date": d,
            "target": str(target),
            "nowcast": nc["point"],
            "lo68": nc["lo68"],
            "hi68": nc["hi68"],
            "lo50": nc["lo50"],
            "hi50": nc["hi50"],
        }
        if prev_data is not None and prev_target == target:
            nd = news_decomposition(res, prev_data, (M, Q), target)
            row.update({f"news: {k}": v for k, v in nd["by_category"].items()})
            row["change"] = nd["change"]
        rows.append(row)
        prev_data, prev_target = (M, Q), target
    return pd.DataFrame(rows).set_index("date").iloc[1:]
