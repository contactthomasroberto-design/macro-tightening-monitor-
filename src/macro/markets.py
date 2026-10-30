"""Cross-asset market analytics for the Markets tab.

Pure functions (pandas in, pandas or `Result` out, no I/O). The bundle that feeds them from the data
layer is `pipeline.markets_bundle`; the universe and the stress-index settings are in
`config/markets.yaml`. Conventions, used everywhere below:

- moves are measured in the unit a desk would quote: basis points for yields and spreads, log
  returns in % for prices, index points for volatility indices (`change`);
- a move is judged against its own history: the z-score divides the latest h-day move by the
  standard deviation of h-day moves over the previous three years, excluding the move itself
  (`move_zscore`), so a 10 bp move in the 2-year and a 10 bp move in the Bund are not treated alike;
- nothing here forecasts or recommends. Regime statistics are descriptive, in-sample, with the
  overlap of forward windows accounted for in the standard errors.

Methods follow standard practice: realised volatility and vol-normalised moves (RiskMetrics-style
scaling), a composite stress index of rolling z-scores (in the spirit of the OFR and St. Louis Fed
indices, which serve as benchmarks), growth/rates quadrants for cross-asset regimes, rolling
correlations of daily changes, rolling sensitivities to rate differentials estimated on changes
(not levels, to avoid spurious level regressions), and the Estrella-Mishkin probit of recession on
the 10-year minus 3-month Treasury spread (the model behind the New York Fed's recession probability).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from macro.utils import Result

BD_PER_YEAR = 252
HORIZONS = {"1D": 1, "1W": 5, "1M": 21, "3M": 63}
ZSCORE_WINDOW = 3 * BD_PER_YEAR
UNITS = {"yield": "bp", "spread": "bp", "price": "%", "vol": "pts"}


# =========================================================================== moves
def business_daily(s: pd.Series, limit: int = 5) -> pd.Series:
    """Series on business days from its first to its last observation; holidays carried forward (at
    most `limit` days), never extended past the last observation."""
    s = s.dropna()
    if s.empty:
        return s
    s = s[~s.index.duplicated(keep="last")].sort_index()
    idx = pd.bdate_range(s.index[0], s.index[-1])
    return s.reindex(idx.union(s.index)).ffill(limit=limit).reindex(idx)


def change(s: pd.Series, kind: str, h: int = 1) -> pd.Series:
    """h-period change in quoting units: bp (yield, spread), log return in % (price), points (vol)."""
    if kind in ("yield", "spread"):
        return (s - s.shift(h)) * 100.0
    if kind == "price":
        return 100.0 * np.log(s / s.shift(h))
    if kind == "vol":
        return s - s.shift(h)
    raise ValueError(f"unknown kind {kind!r}")


def level_display(x: float, kind: str) -> float:
    """Level in quoting units: spreads in bp, everything else as published."""
    return x * 100.0 if kind == "spread" else x


def change_since(s: pd.Series, kind: str, start: pd.Timestamp) -> float:
    """Change from the last value on or before `start` to the last value."""
    s = s.dropna()
    base = s.loc[:start]
    if base.empty or s.empty:
        return np.nan
    pair = pd.Series([base.iloc[-1], s.iloc[-1]], index=[base.index[-1], s.index[-1]])
    return float(change(pair, kind, 1).iloc[-1])


def move_zscore(s: pd.Series, kind: str, h: int = 21, window: int = ZSCORE_WINDOW) -> float:
    """Latest h-day move divided by the standard deviation of h-day moves over the `window` business
    days that end where the latest move starts (zero mean: no drift is assumed over a month)."""
    ch = change(s, kind, h).dropna()
    if len(ch) < h + 60:
        return np.nan
    hist = ch.iloc[-(window + h) : -h]
    sd = float(np.sqrt((hist**2).mean()))
    return float(ch.iloc[-1] / sd) if sd > 0 else np.nan


def percentile_of_last(s: pd.Series, years: float) -> float:
    """Percentile (0-100) of the last value within the trailing `years` of the series."""
    s = s.dropna()
    if s.empty:
        return np.nan
    w = s.loc[s.index[-1] - pd.DateOffset(years=int(years)) :]
    return float((w <= w.iloc[-1]).mean() * 100.0)


def realized_vol(s: pd.Series, kind: str, window: int = 21) -> pd.Series:
    """Annualised volatility of daily changes over `window` days, in quoting units per year."""
    return change(s, kind, 1).rolling(window, min_periods=int(window * 0.8)).std() * np.sqrt(BD_PER_YEAR)


@dataclass(frozen=True)
class Asset:
    id: str
    name: str
    cls: str
    kind: str
    risk: int


def dashboard(series: dict[str, pd.Series], assets: list[Asset]) -> pd.DataFrame:
    """One row per asset: level, moves over 1D/1W/1M/3M/YTD, the 1M move in standard deviations,
    where the level and the realised volatility sit in their own history, and data staleness."""
    newest = max((s.dropna().index[-1] for s in series.values() if not s.dropna().empty), default=None)
    rows = []
    for a in assets:
        raw = series.get(a.id)
        if raw is None or raw.dropna().empty:
            continue
        s = business_daily(raw)
        last_date = s.index[-1]
        ytd_start = pd.Timestamp(year=last_date.year, month=1, day=1) - pd.Timedelta(days=1)
        rv = realized_vol(s, a.kind)
        row = {
            "asset": a.name,
            "id": a.id,
            "class": a.cls,
            "kind": a.kind,
            "unit": UNITS[a.kind],
            "risk": a.risk,
            "last": level_display(float(s.iloc[-1]), a.kind),
            "as_of": last_date,
            "stale_bdays": int(len(pd.bdate_range(last_date, newest)) - 1) if newest is not None else 0,
        }
        for lab, h in HORIZONS.items():
            ch = change(s, a.kind, h)
            row[lab] = float(ch.iloc[-1]) if len(ch.dropna()) else np.nan
        row["YTD"] = change_since(s, a.kind, ytd_start)
        row["z 1M"] = move_zscore(s, a.kind, 21)
        row["level pct 10y"] = percentile_of_last(s, 10)
        row["history (y)"] = round(
            min(10.0, (last_date - s.index[0]).days / 365.25), 1
        )  # window behind the pct
        row["rvol 1M"] = float(rv.iloc[-1]) if rv.notna().any() else np.nan
        row["rvol pct 3y"] = percentile_of_last(rv, 3)
        rows.append(row)
    return pd.DataFrame(rows).set_index("asset") if rows else pd.DataFrame()


# =========================================================================== stress
def rolling_z(s: pd.Series, window: int, min_days: int) -> pd.Series:
    """(x - rolling mean) / rolling std over the trailing window (only past and current data)."""
    m = s.rolling(window, min_periods=min_days).mean()
    sd = s.rolling(window, min_periods=min_days).std()
    return (s - m) / sd


def stress_index(components: dict[str, pd.Series], window: int = 1260, min_days: int = 504) -> Result:
    """Equal-weighted average of rolling z-scores of risk measures (volatility, credit spreads). A
    reading of +1 means stress one standard deviation above its 5-year average. Reported only on days
    where at least half the components have a z-score; a component not yet published for the latest
    day keeps its previous reading (up to five business days)."""
    z = pd.DataFrame({k: rolling_z(business_daily(v), window, min_days) for k, v in components.items()})
    z = z.ffill(limit=5)  # a component published a day later keeps its last reading: no composition jumps
    need = max(1, int(np.ceil(z.shape[1] / 2)))
    comp = z.mean(axis=1).where(z.notna().sum(axis=1) >= need)
    comp = comp.dropna()
    last = z.loc[comp.index[-1]] if not comp.empty else pd.Series(dtype=float)
    return Result(
        "stress_index",
        comp,
        sources=list(components),
        as_of=str(comp.index[-1].date()) if not comp.empty else None,
        n_obs=int(comp.size),
        n_specs_tried=1,
        notes=[f"rolling window {window} business days, z-score shown after {min_days} days"],
        extra={"components": z.loc[comp.index], "contributions": (last / z.shape[1]).sort_values()},
    )


def benchmark_correlations(composite: pd.Series, benchmarks: dict[str, pd.Series]) -> pd.DataFrame:
    """Validation: correlation of the weekly composite with published stress indices, in levels and
    in 4-week changes (the second is the demanding test: levels share slow trends)."""
    wk = composite.resample("W-FRI").last()
    rows = []
    for name, b in benchmarks.items():
        bw = b.dropna().resample("W-FRI").last()
        df = pd.concat([wk, bw], axis=1, keys=["mtm", "bench"]).dropna()
        if len(df) < 52:
            continue
        d4 = df.diff(4).dropna()
        rows.append(
            {
                "benchmark": name,
                "corr (levels)": float(df["mtm"].corr(df["bench"])),
                "corr (4-week changes)": float(d4["mtm"].corr(d4["bench"])),
                "weeks": len(df),
                "from": df.index[0].date(),
            }
        )
    return pd.DataFrame(rows).set_index("benchmark") if rows else pd.DataFrame()


# =========================================================================== regimes
REGIMES = {
    "Goldilocks": "equities up, yields down: growth without rate pressure",
    "Reflation": "equities up, yields up: growth and inflation repricing together",
    "Rates shock": "equities down, yields up: tightening or inflation scare, bonds do not hedge",
    "Risk-off": "equities down, yields down: growth scare, flight to quality",
}


def quadrant_regimes(equity: pd.Series, y10: pd.Series, h: int = 63) -> pd.Series:
    """Daily label from the signs of the h-day equity log return and the h-day 10-year yield change."""
    df = pd.concat({"eq": business_daily(equity), "y": business_daily(y10)}, axis=1).dropna()
    r = change(df["eq"], "price", h)
    dy = change(df["y"], "yield", h)
    ok = r.notna() & dy.notna()
    lab = np.where(
        r >= 0, np.where(dy < 0, "Goldilocks", "Reflation"), np.where(dy >= 0, "Rates shock", "Risk-off")
    )
    return pd.Series(lab, index=df.index).where(ok).dropna()


def regime_spells(regime: pd.Series) -> dict:
    """Current regime, since when, and the share of days spent in each regime."""
    regime = regime.dropna()
    cur = regime.iloc[-1]
    changes = regime.ne(regime.shift())
    start = regime.index[changes][-1]
    return {
        "current": cur,
        "since": start,
        "days": int(len(regime.loc[start:])),
        "share": regime.value_counts(normalize=True).reindex(list(REGIMES)).fillna(0.0),
    }


def regime_forward_moves(
    regime: pd.Series, assets: dict[str, tuple[pd.Series, str]], h: int = 21
) -> pd.DataFrame:
    """Average move over the next h business days by current regime, for each asset.

    The regime on day t uses data up to t only, and the move is measured from t to t+h. Forward
    windows overlap (a new one starts every day), so the standard error uses the effective number of
    independent windows, n / h. Descriptive full-sample averages: nothing here is a forecast."""
    rows = []
    for name, (s, kind) in assets.items():
        fwd = change(business_daily(s), kind, h).shift(-h)
        df = pd.concat({"r": regime, "f": fwd}, axis=1).dropna()
        for reg in REGIMES:
            x = df.loc[df["r"] == reg, "f"]
            n = len(x)
            if n < 2 * h:
                continue
            n_eff = n / h
            se = float(x.std() / np.sqrt(n_eff))
            rows.append(
                {
                    "regime": reg,
                    "asset": name,
                    "unit": UNITS[kind],
                    "mean": float(x.mean()),
                    "t-stat": float(x.mean() / se) if se > 0 else np.nan,
                    "share up": float((x > 0).mean()),
                    "days": n,
                    "independent windows": round(n_eff, 1),
                }
            )
    return pd.DataFrame(rows)


# =========================================================================== correlations
@dataclass(frozen=True)
class Pair:
    name: str
    a: str
    kind_a: str
    sign_a: int
    b: str
    kind_b: str
    sign_b: int
    reading: str


CORR_PAIRS = [
    Pair(
        "Stock-bond",
        "SPX",
        "price",
        1,
        "DGS10",
        "yield",
        -1,
        "returns of equities and of 10Y Treasuries (bond return taken as minus the yield change); "
        "positive: bonds no longer hedge equities",
    ),
    Pair(
        "Dollar-equities",
        "DTWEXBGS",
        "price",
        1,
        "SPX",
        "price",
        1,
        "negative: the dollar rallies when equities fall (safe-haven dollar)",
    ),
    Pair(
        "Dollar-US rates",
        "DTWEXBGS",
        "price",
        1,
        "DGS10",
        "yield",
        1,
        "positive: the dollar trades on US rates",
    ),
    Pair(
        "Yen-equities",
        "USDJPY",
        "price",
        1,
        "SPX",
        "price",
        1,
        "positive: the yen strengthens (USD/JPY falls) when equities fall",
    ),
    Pair(
        "Oil-breakevens",
        "BRENT_FUT",
        "price",
        1,
        "T10YIE",
        "yield",
        1,
        "positive: inflation compensation follows energy",
    ),
    Pair(
        "Gold-real yields",
        "GOLD_FUT",
        "price",
        1,
        "DFII10",
        "yield",
        1,
        "negative is the textbook relation (gold has no coupon)",
    ),
]


def rolling_correlation(
    a: pd.Series, kind_a: str, b: pd.Series, kind_b: str, window: int = 63, sign_a: int = 1, sign_b: int = 1
) -> pd.Series:
    """Rolling correlation of daily changes (signs let a yield stand for a bond return)."""
    df = pd.concat(
        {
            "a": sign_a * change(business_daily(a), kind_a, 1),
            "b": sign_b * change(business_daily(b), kind_b, 1),
        },
        axis=1,
    ).dropna()
    return df["a"].rolling(window, min_periods=int(window * 0.8)).corr(df["b"]).dropna()


def correlation_table(corrs: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for name, c in corrs.items():
        if c.empty:
            continue
        last1y = c.loc[c.index[-1] - pd.DateOffset(years=1) :]
        rows.append(
            {
                "pair": name,
                "current (3M)": float(c.iloc[-1]),
                "1y low": float(last1y.min()),
                "1y high": float(last1y.max()),
                "10y average": float(c.loc[c.index[-1] - pd.DateOffset(years=10) :].mean()),
                "percentile 10y": percentile_of_last(c, 10),
            }
        )
    return pd.DataFrame(rows).set_index("pair") if rows else pd.DataFrame()


# =========================================================================== sensitivities
def change_beta(
    y: pd.Series, kind_y: str, x: pd.Series, kind_x: str, window: int = 104, h: int = 13, freq: str = "W-FRI"
) -> Result:
    """Sensitivity of weekly moves of y to weekly moves of x, estimated by OLS on changes over the last
    `window` weeks with Newey-West standard errors; then how much of y's last h-week move the move in x
    explains (beta x h-week move of x). Rolling beta and R^2 are returned for the chart.

    Weekly (Friday-to-Friday) changes, not daily: the series close at different hours (Tokyo,
    Frankfurt, New York), and daily changes of asynchronous closes understate the relation."""
    import statsmodels.api as sm

    lv = pd.concat({"y": business_daily(y), "x": business_daily(x)}, axis=1).dropna().resample(freq).last()
    df = pd.concat({"y": change(lv["y"], kind_y, 1), "x": change(lv["x"], kind_x, 1)}, axis=1).dropna()
    if len(df) < window // 2:
        return Result("change_beta", None, notes=["not enough overlapping data"])
    w = df.iloc[-window:]
    fit = sm.OLS(w["y"], sm.add_constant(w["x"])).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    beta, se = float(fit.params["x"]), float(fit.bse["x"])
    mp = window // 2
    roll_beta = (
        df["y"].rolling(window, min_periods=mp).cov(df["x"]) / df["x"].rolling(window, min_periods=mp).var()
    )
    roll_r2 = df["y"].rolling(window, min_periods=mp).corr(df["x"]) ** 2
    actual = float(change(lv["y"], kind_y, h).iloc[-1])
    x_move = float(change(lv["x"], kind_x, h).iloc[-1])
    explained = beta * x_move
    return Result(
        "change_beta",
        beta,
        lower=beta - 1.96 * se,
        upper=beta + 1.96 * se,
        band_level=0.95,
        n_obs=len(w),
        n_specs_tried=1,
        as_of=str(lv.index[-1].date()),
        extra={
            "se": se,
            "r2": float(fit.rsquared),
            "actual": actual,
            "x_move": x_move,
            "explained": explained,
            "residual": actual - explained,
            "rolling_beta": roll_beta.dropna(),
            "rolling_r2": roll_r2.dropna(),
            "unit_y": UNITS[kind_y],
            "unit_x": UNITS[kind_x],
            "h_weeks": h,
            "window_weeks": window,
        },
    )


# =========================================================================== curve-implied recession
def _auc(score: np.ndarray, y: np.ndarray) -> float:
    """Area under the ROC curve (Mann-Whitney), ties counted one half."""
    pos, neg = score[y == 1], score[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return np.nan
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def curve_recession_probit(spread: pd.Series, usrec: pd.Series, horizon: int = 12) -> Result:
    """Estrella-Mishkin probit: P(NBER recession in month t+horizon) = Phi(a + b * spread_t), spread =
    monthly average of 10-year minus 3-month Treasury yields. Estimated on every month whose outcome
    is known; the in-sample fit is the only validation offered (few recessions)."""
    import statsmodels.api as sm
    from scipy.stats import norm

    sp = spread.dropna().resample("MS").mean()
    rec = usrec.dropna().resample("MS").last()
    target = rec.shift(-horizon)
    df = pd.concat({"spread": sp, "rec": target}, axis=1).dropna()
    if len(df) < 120 or df["rec"].sum() < 2:
        return Result("curve_recession", None, notes=["not enough data"])
    X = sm.add_constant(df["spread"])
    fit = sm.Probit(df["rec"], X).fit(disp=0)
    a, b = float(fit.params["const"]), float(fit.params["spread"])
    prob = pd.Series(norm.cdf(a + b * sp.values), index=sp.index + pd.DateOffset(months=horizon))
    fitted = fit.predict(X)
    return Result(
        "curve_recession",
        float(prob.iloc[-1]),
        n_obs=len(df),
        n_specs_tried=1,
        as_of=str(sp.index[-1].date()),
        sources=["T10Y3M", "USREC"],
        notes=[
            f"probability of recession in {horizon} months; in-sample fit, {int(df['rec'].sum())} recession months"
        ],
        extra={
            "a": a,
            "b": b,
            "se": fit.bse.to_dict(),
            "pseudo_r2": float(fit.prsquared),
            "auc": _auc(fitted.to_numpy(), df["rec"].to_numpy()),
            "history": prob,
            "spread_now": float(sp.iloc[-1]),
            "target_month": prob.index[-1],
        },
    )


# =========================================================================== carry and roll-down
US_CURVE = {"DGS3MO": 0.25, "DGS1": 1.0, "DGS2": 2.0, "DGS5": 5.0, "DGS10": 10.0, "DGS30": 30.0}


def _duration(y_pct: float, m: float) -> float:
    """Modified duration of a par bond with semi-annual coupons (years)."""
    y = y_pct / 100
    if y <= 0:
        return m
    return (1 - (1 + y / 2) ** (-2 * m)) / y


def rates_carry_roll(
    curve: dict[float, float], vol_bp: dict[float, float], horizon: float = 0.25
) -> pd.DataFrame:
    """Carry and roll-down over `horizon` years for a long position in each tenor, in bp of yield.

    carry: (y_m − y_cash) × horizon / duration, the yield cushion the coupon over cash provides;
    roll-down: y_m − y_{m − horizon} (linear interpolation), the fall in yield from ageing along an
    unchanged curve. Breakeven = carry + roll-down: how much the yield can rise over the horizon
    before the position loses. Ratio to the realised volatility over the same horizon: carry per unit
    of risk. Assumes an unchanged curve; it is what the curve pays, not a forecast."""
    tenors = sorted(curve)
    ys = [curve[t] for t in tenors]
    cash = curve[tenors[0]]
    rows = []
    for m in tenors:
        if m <= horizon:
            continue
        y = curve[m]
        y_short = float(np.interp(m - horizon, tenors, ys))
        dur = _duration(y, m)
        carry = (y - cash) * 100 * horizon / dur
        roll = (y - y_short) * 100
        vol = vol_bp.get(m, np.nan) * np.sqrt(horizon)
        rows.append(
            {
                "tenor (years)": m,
                "yield (%)": y,
                "carry (bp)": carry,
                "roll-down (bp)": roll,
                "breakeven (bp)": carry + roll,
                "3-month vol (bp)": vol,
                "breakeven / vol": (carry + roll) / vol if vol == vol and vol > 0 else np.nan,
            }
        )
    return pd.DataFrame(rows).set_index("tenor (years)")


def fx_carry(
    pairs: dict[str, tuple[pd.Series, pd.Series, pd.Series, int]], horizon: float = 0.25
) -> pd.DataFrame:
    """Interest carry of holding the first currency against the second over `horizon` years, in %, and
    per unit of realised volatility. pairs: name -> (fx level, rate of the held currency, rate of the
    funding currency, sign: +1 if a rise in the quoted level is a gain for the holder)."""
    rows = []
    for name, (fx, r_hold, r_fund, sign) in pairs.items():
        rh, rf = r_hold.dropna(), r_fund.dropna()
        if rh.empty or rf.empty or fx.dropna().empty:
            continue
        carry = (float(rh.iloc[-1]) - float(rf.iloc[-1])) * horizon
        vol = float(realized_vol(business_daily(fx), "price", 63).dropna().iloc[-1]) * np.sqrt(horizon)
        rows.append(
            {
                "position": name,
                "rate held (%)": float(rh.iloc[-1]),
                "rate funded (%)": float(rf.iloc[-1]),
                "3-month carry (%)": carry,
                "3-month vol (%)": vol,
                "carry / vol": carry / vol if vol > 0 else np.nan,
                "sign": sign,
            }
        )
    return pd.DataFrame(rows).set_index("position") if rows else pd.DataFrame()
