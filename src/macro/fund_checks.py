"""Operational checks of the systematic portfolio: real-fund benchmarks, liquidity, price anomalies
and model health. Pure functions (pandas in, pandas out); the bundle wiring is in
`pipeline.portfolio_bundle`, the intraday price check in scripts/portfolio_monitor.py.

1. Fund benchmarks: can the model beat products an investor can simply buy (managed futures, risk
   parity, hedge-fund replication ETFs)? Same metrics as the backtest, over the funds' common history.
2. Liquidity: days to liquidate each position of a notional fund at a fixed share of the average
   daily dollar volume (static, dated estimates in config/portfolio.yaml).
3. Price anomalies: daily moves beyond k standard deviations of the trailing year that the sector
   proxy does not share, and disagreements between two independent price sources.
4. Model health: weight stability, predicted against realised volatility, binding constraints,
   optimiser fallbacks, and the paper book against the backtest.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WEEKS = 52

# Secondary benchmarks: id in config/series.yaml -> label. DBMF is also in the universe.
FUND_BENCHMARKS = {
    "DBMF": "Managed futures (iMGP DBi, DBMF)",
    "RPAR": "Risk parity (RPAR)",
    "QAI": "Hedge-fund multi-strategy replication (IQ Hedge, QAI)",
    "HDG": "Hedge-fund replication (ProShares, HDG)",
}


# ---------------------------------------------------------------------------- 1. fund benchmarks
def fund_benchmarks(
    model: pd.Series,
    benchmark: pd.Series,
    cash: pd.Series,
    funds: dict[str, pd.Series],
    metrics_fn,
    min_weeks: int = 52,
) -> pd.DataFrame:
    """Metrics of the model, the 60/40 benchmark and each fund over their common history (the
    weeks where all of them have a return). Funds with fewer than `min_weeks` weeks are left out so
    that one young fund does not shorten the comparison for all. Columns: one per series; the row
    'first week' says where the common window starts."""
    funds = {k: v.dropna() for k, v in funds.items() if v is not None and v.dropna().size >= min_weeks}
    if not funds:
        return pd.DataFrame()
    frame = pd.DataFrame({"our model": model, "benchmark 60/40": benchmark, **funds}).dropna()
    if len(frame) < min_weeks:
        return pd.DataFrame()
    out = {}
    for k in frame.columns:
        b = None if k == "benchmark 60/40" else frame["benchmark 60/40"]
        out[k] = pd.Series(metrics_fn(frame[k], cash, b))
    t = pd.DataFrame(out)
    t.loc["weeks"] = len(frame)
    t.loc["first week"] = frame.index[0].strftime("%Y-%m-%d")  # type: ignore[union-attr]
    return t


# ---------------------------------------------------------------------------- 2. liquidity
def liquidity(
    weights: pd.Series,
    adv_usd: dict[str, float],
    notional_usd: float,
    participation: float = 0.10,
    max_days: float = 1.0,
    max_share_adv: float = 0.01,
) -> pd.DataFrame:
    """Position size against average daily dollar volume for a fund of `notional_usd`.

    days to liquidate = |w| × notional / (participation × ADV). A position is flagged when it takes
    more than `max_days` days at that participation, or is larger than `max_share_adv` of one day's
    volume. Lines without an ADV estimate are flagged 'no ADV estimate'."""
    rows = []
    for a, w in weights.items():
        if abs(w) < 1e-6:
            continue
        pos = abs(float(w)) * notional_usd
        adv = float(adv_usd.get(str(a)) or 0)  # YAML reads '3.0e10' (no sign) as a string
        if not adv:
            rows.append(
                {"asset": a, "weight": float(w), "position (USD m)": pos / 1e6, "flag": "no ADV estimate"}
            )
            continue
        share = pos / adv
        days = pos / (participation * adv)
        flags = []
        if days > max_days:
            flags.append(f"> {max_days:g} day to exit")
        if share > max_share_adv:
            flags.append(f"> {100 * max_share_adv:g}% of ADV")
        rows.append(
            {
                "asset": a,
                "weight": float(w),
                "position (USD m)": pos / 1e6,
                "ADV (USD m)": adv / 1e6,
                "share of ADV": share,
                "days to liquidate": days,
                "flag": "; ".join(flags),
            }
        )
    cols = ["weight", "position (USD m)", "ADV (USD m)", "share of ADV", "days to liquidate", "flag"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows).set_index("asset").reindex(columns=cols)
    return df.sort_values("days to liquidate", ascending=False, na_position="first")


# ---------------------------------------------------------------------------- 3. price anomalies
def price_jumps(
    px: pd.DataFrame,
    proxies: dict[str, str],
    k: float = 6.0,
    window: int = 252,
    last_days: int = 5,
    proxy_k: float = 3.0,
) -> pd.DataFrame:
    """Daily log moves beyond `k` trailing standard deviations (one year, ending the day before) in
    the last `last_days` observations of each series, kept only when the sector proxy did not move
    by more than `proxy_k` of its own standard deviations the same day (a real market move shows in
    the proxy too; a bad print or an unadjusted split does not)."""
    rows = []
    lr = np.log(px.where(px > 0)).diff()
    for a in px.columns:
        x = lr[a].dropna()
        if len(x) < window // 2 + last_days:
            continue
        sd = x.rolling(window, min_periods=window // 2).std().shift(1)
        z = (x / sd).iloc[-last_days:]
        for d, v in z[z.abs() > k].items():
            p = proxies.get(a)
            pz = np.nan
            if p and p in lr and p != a:
                y = lr[p].dropna()
                psd = y.rolling(window, min_periods=window // 2).std().shift(1)
                # the proxy's move on the same and the next session: Seoul or Tokyo close before New
                # York, so a market move there shows in a US proxy the same or the next day
                zs = []
                for dd in [d, *y.index[y.index > d][:1]]:
                    sd_ = psd.get(dd, np.nan)
                    if dd in y.index and sd_ == sd_ and sd_ > 0:
                        zs.append(float(y[dd] / sd_))
                if zs:
                    pz = max(zs, key=abs)
            if pz == pz and abs(pz) > proxy_k:
                continue  # the proxy moved too: a market move, not a data error
            rows.append(
                {
                    "date": d,
                    "asset": a,
                    "kind": "jump",
                    "move": float(np.expm1(x[d])),
                    "z": float(v),
                    "proxy": p or "",
                    "proxy z": pz,
                    "detail": f"{100 * np.expm1(x[d]):+.1f}% ({v:+.1f} sd)"
                    + (f", {p} {pz:+.1f} sd" if pz == pz else ", no proxy move available"),
                }
            )
    return pd.DataFrame(rows, columns=["date", "asset", "kind", "move", "z", "proxy", "proxy z", "detail"])


def source_mismatches(
    primary: dict[str, tuple[pd.Timestamp, float]],
    secondary: dict[str, tuple[pd.Timestamp, float]],
    tol: float = 0.02,
) -> pd.DataFrame:
    """Closes of the same day from two sources that differ by more than `tol` (relative). Only
    same-date pairs are compared: a stale second source is not an anomaly of the first."""
    rows = []
    for a, (d1, p1) in primary.items():
        if a not in secondary:
            continue
        d2, p2 = secondary[a]
        if pd.Timestamp(d1).normalize() != pd.Timestamp(d2).normalize() or not p1 or not p2:
            continue
        gap = p1 / p2 - 1
        if abs(gap) > tol:
            rows.append(
                {
                    "date": pd.Timestamp(d1).normalize(),
                    "asset": a,
                    "kind": "source mismatch",
                    "move": float(gap),
                    "z": np.nan,
                    "proxy": "",
                    "proxy z": np.nan,
                    "detail": f"Yahoo {p1:,.2f} vs Stooq {p2:,.2f} ({100 * gap:+.1f}%)",
                }
            )
    return pd.DataFrame(rows, columns=["date", "asset", "kind", "move", "z", "proxy", "proxy z", "detail"])


def append_anomalies(df: pd.DataFrame, path) -> pd.DataFrame:
    """Append anomalies not yet recorded (same date, asset and kind) to the CSV archive; returns the
    new rows."""
    from pathlib import Path

    path = Path(path)
    if df.empty:
        return df
    df = df.assign(date=pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"))
    if path.exists():
        old = pd.read_csv(path)
        key = set(zip(old["date"].astype(str), old["asset"], old["kind"], strict=False))
        df = df[[(d, a, k) not in key for d, a, k in zip(df["date"], df["asset"], df["kind"], strict=False)]]
    if df.empty:
        return df
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, mode="a", header=not path.exists(), index=False)
    return df


def read_anomalies(path, days: int | None = None) -> pd.DataFrame:
    from pathlib import Path

    if not Path(path).exists():
        return pd.DataFrame(columns=["date", "asset", "kind", "move", "z", "proxy", "proxy z", "detail"])
    df = pd.read_csv(path, parse_dates=["date"])
    if days is not None and not df.empty:
        df = df[df["date"] >= df["date"].max() - pd.Timedelta(days=days)]
    return df


# ---------------------------------------------------------------------------- 4. model health
def weight_turnover(weights: pd.DataFrame) -> pd.Series:
    """Sum of absolute weight changes between consecutive rebalances (L1; one-way turnover × 2)."""
    w = weights.fillna(0.0)
    return w.diff().abs().sum(axis=1).iloc[1:]


def predicted_vs_realised(
    weights: pd.DataFrame,
    r: pd.DataFrame,
    ret: pd.Series,
    window: int = 156,
    horizon: int = 26,
    step: int = 4,
) -> pd.DataFrame:
    """Ex-ante volatility of the weights at each rebalance (sample covariance of the trailing
    `window` weeks, every `step`-th rebalance to stay cheap) against the volatility the portfolio
    then realised over the next `horizon` weeks. Ratio > 1: the model under-estimated risk."""
    rows = []
    dates = weights.index[::step]
    for t in dates:
        w = weights.loc[t]
        w = w[w.abs() > 1e-6]
        a = [x for x in w.index if x in r.columns]
        hist = r.loc[:t, a].iloc[-window:]
        fut = ret.loc[ret.index > t].iloc[:horizon]
        if len(hist) < window // 2 or len(fut) < horizon // 2:
            continue
        S = hist.fillna(0).cov().to_numpy() * WEEKS
        wv = w.reindex(a).to_numpy()
        pred = float(np.sqrt(max(wv @ S @ wv, 0.0)))
        real = float(fut.std() * np.sqrt(WEEKS))
        rows.append(
            {"date": t, "predicted": pred, "realised": real, "ratio": real / pred if pred else np.nan}
        )
    return (
        pd.DataFrame(rows).set_index("date")
        if rows
        else pd.DataFrame(columns=["predicted", "realised", "ratio"])
    )


def binding_constraints(
    w: pd.Series,
    cfg: dict,
    risk: dict,
    vol_scale: float = 1.0,
    equity_sleeves=("equity", "style", "sector", "semis"),
    tol: float = 1e-3,
) -> pd.DataFrame:
    """Which limits of the optimiser the weights sit on (within `tol`): line bounds, sleeve limits,
    gross exposure, volatility cap and tracking-error cap."""
    uni, sl, m = cfg["universe"], cfg["sleeves"], cfg["model"]
    rows = []

    def add(name, value, limit, side):
        at = abs(value - limit) <= tol * max(1.0, abs(limit)) or (
            value > limit if side == "max" else value < limit
        )
        rows.append({"limit": name, "value": value, "bound": limit, "side": side, "binding": bool(at)})

    for a, x in w.items():
        u = uni.get(a, {})
        if "max" in u and abs(x - float(u["max"])) <= tol:
            add(f"{a} max", float(x), float(u["max"]), "max")
        if float(u.get("min", 0.0)) != 0.0 and abs(x - float(u["min"])) <= tol:
            add(f"{a} min", float(x), float(u["min"]), "min")
    sleeve = pd.Series({a: uni.get(a, {}).get("sleeve", "") for a in w.index})
    semis = float(w[sleeve == "semis"].sum())
    add("semiconductors net max", semis, sl["semis"]["max"], "max")
    add("semiconductors net min", semis, sl["semis"]["min"], "min")
    eq = float(w[sleeve.isin(equity_sleeves)].sum())
    add("net equity max", eq, sl["equity_net"]["max"], "max")
    add("net equity min", eq, sl["equity_net"]["min"] * vol_scale, "min")
    add("gross exposure", float(w.abs().sum()), sl.get("gross_max", 1.0), "max")
    if "alt_max" in sl:
        add("alternatives", float(w[sleeve == "alt"].sum()), sl["alt_max"], "max")
    if "fx_gross_max" in sl:
        add("currencies gross", float(w[sleeve == "fx"].abs().sum()), sl["fx_gross_max"], "max")
    add(
        "volatility cap",
        float(risk["volatility"]),
        float(risk["benchmark volatility"]) * m["vol_cap_vs_benchmark"] * vol_scale,
        "max",
    )
    add("tracking error", float(risk["tracking error"]), m["tracking_error_max"], "max")
    return pd.DataFrame(rows)


def paper_vs_backtest(paper_nav: pd.Series, backtest_ret: pd.Series) -> dict:
    """Weekly returns of the paper book against the backtest's over the weeks both exist."""
    if paper_nav is None or len(paper_nav) < 3:
        return {}
    pw = paper_nav.resample("W-FRI").last().pct_change().dropna()
    j = pd.concat({"paper": pw, "backtest": backtest_ret}, axis=1).dropna()
    if len(j) < 2:
        return {"weeks": len(j)}
    d = j["paper"] - j["backtest"]
    return {
        "weeks": len(j),
        "paper cumulative": float((1 + j["paper"]).prod() - 1),
        "backtest cumulative": float((1 + j["backtest"]).prod() - 1),
        "tracking difference (annualised)": float(d.mean() * WEEKS),
        "tracking error (annualised)": float(d.std() * np.sqrt(WEEKS)) if len(j) > 2 else np.nan,
        "correlation": float(j.corr().iloc[0, 1]) if len(j) > 2 else np.nan,
    }


def model_health(
    run: dict,
    r: pd.DataFrame,
    target: pd.Series,
    cfg: dict,
    risk: dict,
    target_status: str,
    vol_scale: float = 1.0,
    paper_nav: pd.Series | None = None,
) -> dict:
    """Health indicators of the model from the full-model backtest and today's target."""
    log = run["log"]
    turn = weight_turnover(run["weights"])
    pvr = predicted_vs_realised(run["weights"], r, run["returns"])
    bc = binding_constraints(target, cfg, risk, vol_scale)
    status = log["status"].value_counts() if not log.empty else pd.Series(dtype=int)
    n = int(status.sum()) if len(status) else 0
    relaxed = int(status.drop("optimal", errors="ignore").sum()) if n else 0
    last52 = log.iloc[-52:]["status"] if not log.empty else pd.Series(dtype=str)
    return {
        "turnover": turn,
        "turnover last 13 rebalances": float(turn.iloc[-13:].mean()) if len(turn) else np.nan,
        "turnover all history": float(turn.mean()) if len(turn) else np.nan,
        "predicted vs realised": pvr,
        "vol bias ratio": float(pvr["ratio"].median()) if not pvr.empty else np.nan,
        "binding": bc,
        "status counts": status,
        "relaxed share": relaxed / n if n else np.nan,
        "relaxed last 52": int((last52 != "optimal").sum()),
        "target status": target_status,
        "paper vs backtest": paper_vs_backtest(paper_nav, run["returns"]) if paper_nav is not None else {},
    }
