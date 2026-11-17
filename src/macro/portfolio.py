"""Systematic multi-asset alternative fund: macro and micro signals into a long/short allocation
benchmarked on 60/40 (version 0.3: weekly, gross ≤ 160%, tracking error ≤ 8%; the steps below
describe the construction, config/portfolio.yaml holds the current parameters).

A model portfolio tracked on paper (config/portfolio.yaml); it places no orders. Pure functions:
prices in, weights and diagnostics out.

Construction, at each monthly rebalance t, using only data available at t:

1. Weekly USD total returns (Korean shares converted at the KRW rate; weekly sampling because
   Seoul and New York closes are not synchronous).
2. Covariance: Ledoit-Wolf (2004) shrinkage of the correlation matrix towards the identity, on the
   last 156 weeks, rescaled by each asset's own volatility.
3. Equilibrium: reverse optimisation on the benchmark mapped onto the universe, π = δ Σ w_eq
   (He and Litterman, 1999).
4. Views, each a score s in [-1, 1] turned into an expected excess return π_i + κ σ_i s with a
   confidence per family (Idzorek-style Ω = τ σ² (1 − c) / c):
   - trend: time-series momentum, 12-month return skipping the last month over its volatility
     (Moskowitz, Ooi and Pedersen, 2012);
   - macro: recession risk (excess bond premium, Gilchrist-Zakrajšek), inflation (core CPI
     3-month annualised against 2.5%) and market stress (the monitor's stress index), mapped to
     asset classes with fixed signs;
   - micro, semiconductor names: cross-sectional momentum and low volatility, and the memory
     cycle (acceleration of Micron's trailing revenue growth, dated at the SEC filing) for the
     memory makers;
   - news: GDELT tone, weight 0 until it passes an out-of-sample test (research log H30).
5. Black-Litterman posterior, then mean-variance with constraints: long only, position bounds,
   semiconductor sleeve 5-15%, total equity within ±15 pp of 60%, ex-ante volatility at most the
   benchmark's (times the drawdown-overlay scale), tracking error at most 5%.
6. Trades below 0.5 pp are skipped; costs per asset (Korean sales pay the transaction tax).

Overlay: when the portfolio's drawdown from its peak passes 8% (15%), the volatility cap is cut to
75% (50%) of the benchmark's; it is released when the drawdown is back below half the threshold.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yaml
from scipy import stats

from macro.config import ROOT

PATH = ROOT / "config" / "portfolio.yaml"
WEEKS = 52
FAMILIES = ("trend", "macro", "regime", "value", "carry", "micro", "house", "news")
MEMORY_BASKET = ("HYNIX", "SAMSUNG", "MU")


def load_config(path=PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ------------------------------------------------------------------ data
def usd_prices(get: Callable[[str], pd.Series | None], cfg: dict) -> pd.DataFrame:
    """Daily USD prices for the universe and the benchmark building blocks."""
    ids = list(cfg["universe"]) + ["ACWI", "AGG", "SPY", "EFA", "EEM"]
    out = {}
    for i in dict.fromkeys(ids):
        s = get(i)
        if s is None or s.dropna().empty:
            continue
        s = s.dropna()
        fx_id = cfg.get("fx", {}).get(i)
        if fx_id:
            fx = get(fx_id)
            if fx is None or fx.dropna().empty:
                continue
            s = s / fx.dropna().reindex(s.index, method="ffill")
        out[i] = s
    return pd.DataFrame(out).sort_index()


def weekly_returns(px: pd.DataFrame, cash_yield: pd.Series | None = None) -> pd.DataFrame:
    """Friday-to-Friday simple returns. Before BIL exists, cash earns the 3-month bill yield."""
    w = px.resample("W-FRI").last()
    r = w.pct_change(fill_method=None)
    r = r.where(w.notna() & w.shift(1).notna())
    if cash_yield is not None and "BIL" in r:
        y = cash_yield.dropna().resample("W-FRI").last().reindex(r.index).ffill()
        proxy = (1 + y / 100) ** (1 / WEEKS) - 1
        r["BIL"] = r["BIL"].fillna(proxy.where(r["BIL"].isna()))
    return r.iloc[1:]


def benchmark_returns(r: pd.DataFrame, cfg: dict) -> pd.Series:
    """60/40 ACWI/AGG; before ACWI exists, ACWI is 0.66 SPY + 0.21 EFA + 0.13 EEM."""
    proxy = 0.66 * r["SPY"] + 0.21 * r["EFA"] + 0.13 * r["EEM"]
    eq = r["ACWI"].fillna(proxy) if "ACWI" in r else proxy
    b = cfg["benchmark"]
    return (b["ACWI"] * eq + b["AGG"] * r["AGG"]).dropna()


# ------------------------------------------------------------------ risk model
def ledoit_wolf_corr(x: np.ndarray) -> tuple[np.ndarray, float]:
    """Ledoit-Wolf (2004) shrinkage of the sample correlation towards the identity. x: n × p
    standardised returns. Returns the shrunk correlation and the shrinkage intensity."""
    n, p = x.shape
    x = x - x.mean(0)
    s = x.T @ x / n
    mu = np.trace(s) / p
    d2 = np.sum((s - mu * np.eye(p)) ** 2) / p
    b2 = sum(np.sum((np.outer(r, r) - s) ** 2) for r in x) / n**2 / p
    delta = 0.0 if d2 == 0 else min(b2, d2) / d2
    c = delta * mu * np.eye(p) + (1 - delta) * s
    d = np.sqrt(np.diag(c))
    return c / np.outer(d, d), float(delta)


def covariance(r: pd.DataFrame, window: int, min_weeks: int, halflife: float | None = None) -> pd.DataFrame:
    """Annualised covariance of the assets with at least `min_weeks` of the last `window` weeks.
    With `halflife` (weeks), volatilities are exponentially weighted (faster reaction, research log
    H36); correlations stay Ledoit-Wolf on the window."""
    h = r.iloc[-window:]
    h = h.loc[:, h.notna().sum() >= min_weeks]
    vol = h.std() * np.sqrt(WEEKS)
    if halflife:
        vol = np.sqrt((h**2).ewm(halflife=halflife, min_periods=min_weeks).mean().iloc[-1] * WEEKS).fillna(
            vol
        )
    z = ((h - h.mean()) / h.std()).fillna(0.0).to_numpy()  # missing weeks: no information
    corr, _ = ledoit_wolf_corr(z)
    cov = corr * np.outer(vol, vol)
    return pd.DataFrame(cov, index=h.columns, columns=h.columns)


# ------------------------------------------------------------------ signals
def _cum(r: pd.DataFrame) -> pd.Series:
    return (1 + r.fillna(0)).prod() - 1


def trend_scores(r: pd.DataFrame, horizons: list[int] | None = None) -> pd.Series:
    """12-month return skipping the last month, over its annual volatility, squashed by tanh.
    With `horizons` (weeks, e.g. [4, 13, 52]), the equal-weight average of each horizon's return over
    its volatility (Hurst, Ooi and Pedersen, 2017; research log H37)."""
    if horizons:
        h = r.iloc[-WEEKS:]
        ok = h.notna().sum() >= 48
        vol = h.std() * np.sqrt(WEEKS)
        parts = [np.tanh(_cum(h.iloc[-k:]) / (vol * np.sqrt(k / WEEKS)).replace(0, np.nan)) for k in horizons]
        return pd.concat(parts, axis=1).mean(axis=1).where(ok).dropna()
    h = r.iloc[-WEEKS:]
    ok = h.notna().sum() >= 48
    r12_1 = _cum(h.iloc[:-4])
    vol = h.std() * np.sqrt(WEEKS)
    return np.tanh(r12_1 / vol.replace(0, np.nan)).where(ok).dropna()


def trend_series(r: pd.Series) -> pd.Series:
    """Weekly trend of one asset (12-month return skipping a month, over its volatility), dated at t."""
    lr = np.log1p(r.fillna(0))
    r12_1 = np.expm1(lr.rolling(48).sum().shift(4))
    vol = r.rolling(WEEKS).std() * np.sqrt(WEEKS)
    return np.tanh(r12_1 / vol)


# macro loadings: score = Σ loading × factor; factors in [-1, 1]
MACRO_LOADINGS = {
    "equity": {"recession": -0.5, "stress": -0.5},
    "style": {"recession": -0.4, "stress": -0.4},
    "sector": {"recession": -0.4, "stress": -0.4},
    "semis": {"recession": -0.5, "stress": -0.5},
    "USMV": {"recession": 0.2, "stress": 0.2},
    "QUAL": {"recession": 0.1, "stress": 0.1},
    "VLUE": {"inflation": 0.3, "recession": -0.3},
    "XLE": {"inflation": 0.5, "recession": -0.3},
    "XLU": {"recession": 0.3, "inflation": -0.2},
    "XLV": {"recession": 0.3},
    "XLF": {"recession": -0.5, "stress": -0.4},
    "ITA": {"stress": 0.1},
    "LQD": {"recession": -0.4, "stress": -0.4},
    "HYG": {"recession": -0.6, "stress": -0.6},
    "EMB": {"recession": -0.4, "stress": -0.5},
    "EMLC": {"recession": -0.4, "stress": -0.5},
    "AGG": {"recession": 0.3, "inflation": -0.3},
    "SHY": {"recession": 0.2},
    "IEF": {"recession": 0.5, "inflation": -0.4},
    "TLT": {"recession": 0.5, "inflation": -0.5},
    "BWX": {"recession": 0.2, "inflation": -0.2},
    "TIP": {"inflation": 0.5},
    "GLD": {"inflation": 0.3, "stress": 0.3},
    "SLV": {"inflation": 0.3, "recession": -0.2},
    "DBC": {"inflation": 0.5, "recession": -0.3},
    "CPER": {"recession": -0.5, "inflation": 0.2},
    "BNO": {"inflation": 0.5, "recession": -0.4},
    "VNQ": {"recession": -0.4, "inflation": -0.2},
    "IGF": {"inflation": 0.2},
    "alt": {"stress": 0.4, "recession": 0.2},
    "TAIL": {"stress": 0.6, "recession": 0.4},
    "UUP": {"stress": 0.3, "recession": 0.2},
    "FXY": {"stress": 0.5, "recession": 0.3},
    "FXF": {"stress": 0.4},
    "FXE": {"stress": -0.2},
}


def expanding_z(s: pd.Series, min_obs: int) -> pd.Series:
    m = s.expanding(min_obs).mean()
    sd = s.expanding(min_obs).std()
    return (s - m) / sd


def macro_factors(
    ebp: pd.Series | None, core_cpi: pd.Series | None, stress: pd.Series | None
) -> pd.DataFrame:
    """Weekly macro factors in [-1, 1], each lagged for publication: EBP (monthly, +1 month),
    core CPI 3-month annualised (monthly, +1 month), stress index (daily z, +1 week)."""
    cols = {}
    if ebp is not None and not ebp.dropna().empty:
        e = ebp.dropna().resample("MS").last()
        e.index = e.index + pd.DateOffset(months=2) - pd.Timedelta(days=1)  # month t known end of t+1
        cols["recession"] = np.tanh(expanding_z(e, 60))
    if core_cpi is not None and not core_cpi.dropna().empty:
        c = core_cpi.dropna().resample("MS").last()
        a3 = 100 * ((c / c.shift(3)) ** 4 - 1)
        a3.index = a3.index + pd.DateOffset(months=2) - pd.Timedelta(days=1)
        cols["inflation"] = np.tanh((a3 - 2.5) / 1.5)
    if stress is not None and not stress.dropna().empty:
        s = stress.dropna().resample("W-FRI").last().shift(1)
        cols["stress"] = np.tanh(s / 1.5)
    if not cols:
        return pd.DataFrame()
    df = pd.DataFrame({k: v.resample("W-FRI").last() for k, v in cols.items()})
    return df.ffill()


def macro_scores(f: pd.Series, assets: list[str], cfg: dict) -> pd.Series:
    out = {}
    for a in assets:
        sleeve = cfg["universe"][a]["sleeve"]
        load = MACRO_LOADINGS.get(a) or MACRO_LOADINGS.get(sleeve)
        if not load:
            continue
        vals = [w * f[k] for k, w in load.items() if k in f and f[k] == f[k]]
        if vals:
            out[a] = float(np.clip(sum(vals), -1, 1))
    return pd.Series(out, dtype=float)


def memory_cycle(revenue: pd.Series | None) -> pd.Series:
    """Acceleration of trailing-12-month revenue growth, dated at each filing: TTM y/y growth now
    minus one quarter ago. Positive: the cycle is turning up."""
    if revenue is None or len(revenue.dropna()) < 9:
        return pd.Series(dtype=float)
    q = revenue.dropna()
    ttm = q.rolling(4).sum()
    g = ttm / ttm.shift(4) - 1
    return (g - g.shift(1)).dropna()


def _rank(s: pd.Series) -> pd.Series:
    """Cross-sectional rank scaled to [-1, 1]."""
    if len(s) < 2:
        return s * 0
    return 2 * (s.rank() - 1) / (len(s) - 1) - 1


def micro_table(r: pd.DataFrame, names: list[str], fundamentals: dict[str, pd.Series], t) -> pd.DataFrame:
    """Semiconductor names, one column per component in [-1, 1]: momentum and low-volatility ranks
    within the sleeve, the memory cycle for the memory makers and trailing revenue growth for US
    filers (data filed by t only)."""
    h = r[names].iloc[-WEEKS:]
    ok = [n for n in names if h[n].notna().sum() >= 48]
    if not ok:
        return pd.DataFrame()
    cols = {"momentum": _rank(_cum(h[ok].iloc[:-4])), "low volatility": -_rank(h[ok].std())}
    cyc = memory_cycle(fundamentals.get("MU_REV")).loc[:t]
    if not cyc.empty and cyc.index[-1] > t - pd.Timedelta(days=200):
        c = float(np.tanh(cyc.iloc[-1] / 0.10))
        cols["memory cycle"] = pd.Series({n: c for n in ok if n in MEMORY_BASKET})
    rg = {}
    for co in ("MU", "NVDA"):
        rev = fundamentals.get(f"{co}_REV")
        if co in ok and rev is not None:
            rv = rev.loc[:t].dropna()
            if len(rv) >= 8:
                ttm = rv.rolling(4).sum()
                rg[co] = float(np.tanh((ttm.iloc[-1] / ttm.iloc[-5] - 1) / 0.3))
    if rg:
        cols["revenue growth"] = pd.Series(rg)
    return pd.DataFrame(cols).reindex(ok)


def micro_scores(r: pd.DataFrame, names: list[str], fundamentals: dict[str, pd.Series], t) -> pd.Series:
    """Average of the available micro components per name."""
    tab = micro_table(r, names, fundamentals, t)
    return tab.mean(axis=1).clip(-1, 1) if not tab.empty else pd.Series(dtype=float)


NEWS_TONE_OF = {
    "HYNIX": "NEWS_TONE_HYNIX",
    "SAMSUNG": "NEWS_TONE_SAMSUNG",
    "MU": "NEWS_TONE_MICRON",
    "TSM": "NEWS_TONE_TSMC",
    "NVDA": "NEWS_TONE_NVIDIA",
    "ASML": "NEWS_TONE_ASML",
}


def tone_signal(tone: pd.Series | None) -> pd.Series:
    """Weekly news signal: 4-week average tone z-scored against the previous 52 weeks (tanh-squashed).
    Dated at the week it is known."""
    if tone is None or tone.dropna().empty:
        return pd.Series(dtype=float)
    w = tone.dropna().resample("W-FRI").mean()
    recent = w.rolling(4).mean()
    base = w.shift(4).rolling(WEEKS, min_periods=40)
    return np.tanh((recent - base.mean()) / base.std()).dropna()


def news_scores(tone: dict[str, pd.Series], t, assets: list[str], cfg: dict) -> pd.Series:
    """Company tone for the semiconductor names (memory-chip tone when a name has none); half the
    recession-news signal for the other equities (a darker tone lowers the score)."""
    out = {}
    rec = tone_signal(tone.get("NEWS_TONE_RECESSION")).loc[:t]
    mem = tone_signal(tone.get("NEWS_TONE_MEMORY")).loc[:t]
    for a in assets:
        sl = cfg["universe"][a]["sleeve"]
        own = tone_signal(tone.get(NEWS_TONE_OF.get(a, ""))).loc[:t]
        if sl == "semis" and not own.empty:
            out[a] = float(own.iloc[-1])
        elif sl == "semis" and a in MEMORY_BASKET and not mem.empty:
            out[a] = float(mem.iloc[-1])
        elif sl in ("equity", "semis") and not rec.empty:
            out[a] = 0.5 * float(rec.iloc[-1])
    return pd.Series(out, dtype=float).dropna()


def news_test(r: pd.DataFrame, tone: dict[str, pd.Series], bench: str = "SOX") -> dict:
    """Research log H32: pooled IC of the company news signal for the next 4 weeks' return relative to
    the semiconductor index, non-overlapping 4-week steps, second half of the sample."""
    rows = []
    if bench not in r:
        return {"IC": np.nan, "t": np.nan, "n": 0}
    for a, tid in NEWS_TONE_OF.items():
        if a not in r or tid not in tone:
            continue
        sig = tone_signal(tone[tid])
        rel = r[a] - r[bench]
        fwd = (1 + rel).rolling(4).apply(np.prod, raw=True).shift(-4) - 1
        d = pd.concat([sig, fwd.reindex(sig.index)], axis=1, keys=["s", "f"]).dropna().iloc[::4]
        rows.append(d)
    if not rows:
        return {"IC": np.nan, "t": np.nan, "n": 0}
    pool = pd.concat(rows)
    half = pool[pool.index >= pool.index.sort_values()[len(pool) // 2]]
    return information_coefficient(half["s"], half["f"])


def news_confidence(test: dict) -> float:
    """The pre-registered gate (H32): 0.10 if the second-half IC is positive with t > 2, else 0."""
    return 0.10 if test.get("n", 0) >= 30 and test.get("IC", 0) > 0 and test.get("t", 0) > 2 else 0.0


# ------------------------------------------------------------------ regime, value, carry, house views
def regime_series(indpro: pd.Series | None, cpi: pd.Series | None) -> pd.Series:
    """Weekly macro quadrant from growth (industrial production y/y) and inflation (CPI y/y), each
    'up' when its 3-month change is positive; known two months after the reference month."""
    if indpro is None or cpi is None or indpro.dropna().empty or cpi.dropna().empty:
        return pd.Series(dtype=object)
    out = {}
    for k, x in (("growth", indpro), ("inflation", cpi)):
        mth = x.dropna().resample("MS").last()
        yoy = 100 * (mth / mth.shift(12) - 1)
        up = (yoy - yoy.shift(3)) > 0
        up.index = up.index + pd.DateOffset(months=3) - pd.Timedelta(days=1)  # published ~6 weeks later
        out[k] = up.where(yoy.notna() & yoy.shift(3).notna())
    df = pd.DataFrame(out).dropna()
    lab = (
        df["growth"].map({True: "growth up", False: "growth down"})
        + ", "
        + df["inflation"].map({True: "inflation up", False: "inflation down"})
    )
    return lab.resample("W-FRI").last().ffill()


def regime_scores(r: pd.DataFrame, regime: pd.Series, t, shrink_weeks: int = 260) -> pd.Series:
    """Empirical regime view: each asset's average weekly return in the current quadrant minus its
    average in all weeks, both on data up to t, shrunk towards zero by n / (n + 260), in Sharpe units."""
    if regime.empty:
        return pd.Series(dtype=float)
    reg = regime.loc[:t]
    if reg.empty:
        return pd.Series(dtype=float)
    now = reg.iloc[-1]
    h = r.loc[:t]
    lab = reg.reindex(h.index, method="ffill")
    out = {}
    for a in h.columns:
        x = h[a].dropna()
        if len(x) < 156:
            continue
        inr = x[lab.reindex(x.index) == now]
        if len(inr) < 52:
            continue
        sd = x.std()
        diff = (inr.mean() - x.mean()) / sd * np.sqrt(WEEKS) if sd > 0 else 0.0
        out[a] = float(np.tanh(diff * len(inr) / (len(inr) + shrink_weeks) / 0.5))
    return pd.Series(out, dtype=float)


def value_scores(r: pd.DataFrame, cfg: dict) -> pd.Series:
    """Value as 5-year reversal (Asness, Moskowitz and Pedersen, 2013, for asset classes): within
    each peer group, the assets with the weakest returns from 5 years to 1 year ago score highest."""
    h = r.iloc[-5 * WEEKS :]
    out = {}
    groups: dict[str, list[str]] = {}
    for a in h.columns:
        g = cfg["universe"].get(a, {}).get("group")
        if g and h[a].notna().sum() >= 4.5 * WEEKS:
            groups.setdefault(g, []).append(a)
    for _g, names in groups.items():
        if len(names) < 3:
            continue
        past = np.log1p(h[names].iloc[:-WEEKS].fillna(0)).sum()
        out.update((-_rank(past)).to_dict())
    return pd.Series(out, dtype=float)


def carry_frame(get: Callable[[str], pd.Series | None]) -> pd.DataFrame:
    """Weekly carry proxies in percentage points a year: term spreads for Treasuries, the real
    yield for TIPS, credit spreads, and short-rate differentials for currencies against the dollar."""

    def w(sid):
        s = get(sid)
        return None if s is None or s.dropna().empty else s.dropna().resample("W-FRI").last()

    c3, d2, d10, d30 = w("DGS3MO"), w("DGS2"), w("DGS10"), w("DGS30")
    cols = {}
    if c3 is not None:
        if d2 is not None:
            cols["SHY"] = d2 - c3
        if d10 is not None:
            cols["IEF"] = d10 - c3
            cols["AGG"] = d10 - c3
        if d30 is not None:
            cols["TLT"] = d30 - c3
    if (ry := w("DFII10")) is not None:
        cols["TIP"] = ry - 1.0
    if (hy := w("BAMLH0A0HYM2")) is not None:
        cols["HYG"] = hy - hy.rolling(260, min_periods=104).mean()
    if (ig := w("BAMLC0A0CM")) is not None:
        cols["LQD"] = ig - ig.rolling(260, min_periods=104).mean()
    sofr = w("SOFR")
    usd3 = sofr if sofr is not None else c3
    if usd3 is not None:
        if (jp := w("JP_CALL_D")) is not None:
            cols["FXY"] = jp - usd3
        if (eu := w("EA_ESTR")) is not None:
            cols["FXE"] = eu - usd3
            cols["UUP"] = usd3 - eu
    if not cols:
        return pd.DataFrame()
    return pd.DataFrame(cols).shift(1).ffill(limit=8)  # known with a one-week lag


def carry_scores(carry: pd.DataFrame, t) -> pd.Series:
    if carry.empty:
        return pd.Series(dtype=float)
    c = carry.loc[:t]
    if c.empty:
        return pd.Series(dtype=float)
    return np.tanh(c.iloc[-1].dropna() / 1.5)


def load_house_views(path=None) -> list[dict]:
    """Dated, sourced stances of banks and asset managers (config/house_views.yaml)."""
    p = path or (ROOT / "config" / "house_views.yaml")
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh).get("views", [])


def house_scores(views: list[dict], t, assets: list[str], max_age_days: int = 180) -> pd.Series:
    """Average stance (+1 overweight, 0 neutral, −1 underweight) of the views published by t and less
    than six months old, per asset. Not backtestable: before the first view there is no score."""
    acc: dict[str, list[float]] = {}
    t = pd.Timestamp(t)
    for v in views:
        d = pd.Timestamp(v["date"])
        if d > t or (t - d).days > max_age_days:
            continue
        for a, st in v.get("stances", {}).items():
            if a in assets:
                acc.setdefault(a, []).append(float(st))
    return pd.Series({a: float(np.clip(np.mean(x), -1, 1)) for a, x in acc.items()}, dtype=float)


# ------------------------------------------------------------------ tail hedge (synthetic puts)
def bs_put(s: float, k: float, t: float, r: float, vol: float) -> float:
    """Black-Scholes European put price."""
    if t <= 0 or vol <= 0:
        return max(k - s, 0.0)
    d1 = (np.log(s / k) + (r + vol**2 / 2) * t) / (vol * np.sqrt(t))
    d2 = d1 - vol * np.sqrt(t)
    return float(k * np.exp(-r * t) * stats.norm.cdf(-d2) - s * stats.norm.cdf(-d1))


def hedge_ratio(stress: float, trend_us: float, cfg: dict) -> float:
    """Share of net equity exposure to hedge (H34): a base, more when US trend is negative, and more
    again when volatility is cheap (stress index below 0) while the trend is negative."""
    th = cfg["model"]["tail_hedge"]
    h = th["base_ratio"]
    if trend_us < 0:
        h += th["trend_ratio"]
        if stress < 0:
            h += th["added_ratio"]
    return float(min(h, 1.0))


# ------------------------------------------------------------------ Black-Litterman
def equilibrium_weights(assets: list[str], cfg: dict) -> pd.Series:
    """Benchmark mapped on the available assets; a missing equity region's weight goes to SPY,
    a missing bond to AGG."""
    w = pd.Series(cfg["equilibrium"], dtype=float)
    out = pd.Series(0.0, index=assets)
    for a, v in w.items():
        if a in out.index:
            out[a] += v
        elif a in ("MCHI", "INDA", "EWT", "EWY", "EWZ") and "EEM" in out.index:
            out["EEM"] += v
        elif cfg["universe"][a]["sleeve"] == "equity" and "SPY" in out.index:
            out["SPY"] += v
        elif "AGG" in out.index:
            out["AGG"] += v
    return out / out.sum()


def black_litterman(
    cov: pd.DataFrame, w_eq: pd.Series, views: dict[str, pd.Series], cfg: dict
) -> tuple[pd.Series, pd.Series]:
    """Posterior expected excess returns and the equilibrium π. views: family → scores."""
    m = cfg["model"]
    delta, tau, kappa = m["risk_aversion"], m["tau"], m["view_scale"]
    S = cov.to_numpy()
    pi = delta * S @ w_eq.to_numpy()
    sig = np.sqrt(np.diag(S))
    rows, q, om, blocks = [], [], [], []
    correlated = m.get("omega") == "correlated"  # research log H38
    for fam, sc in views.items():
        c = float(m["confidence"].get(fam, 0.0))
        if c <= 0:
            continue
        idx = []
        for a, s in sc.items():
            if a not in cov.index or s != s:
                continue
            i = cov.index.get_loc(a)
            p = np.zeros(len(cov))
            p[i] = 1.0
            rows.append(p)
            q.append(pi[i] + kappa * sig[i] * s)
            om.append(tau * sig[i] ** 2 * (1 - c) / c)
            idx.append(i)
        blocks.append((idx, c))
    if not rows:
        return pd.Series(pi, index=cov.index), pd.Series(pi, index=cov.index)
    P, Q, Om = np.array(rows), np.array(q), np.diag(om)
    if correlated:  # Ω = (1 − c)/c · P τΣ Pᵀ within each family: correlated views count once, not n times
        Om = np.zeros((len(rows), len(rows)))
        k = 0
        for idx, c in blocks:
            n = len(idx)
            Om[k : k + n, k : k + n] = tau * S[np.ix_(idx, idx)] * (1 - c) / c
            k += n
        Om += np.eye(len(rows)) * 1e-10
    ts_inv = np.linalg.inv(tau * S)
    A = ts_inv + P.T @ np.linalg.inv(Om) @ P
    b = ts_inv @ pi + P.T @ np.linalg.inv(Om) @ Q
    mu = np.linalg.solve(A, b)
    return pd.Series(mu, index=cov.index), pd.Series(pi, index=cov.index)


# ------------------------------------------------------------------ optimiser
EQUITY_SLEEVES = ("equity", "style", "sector", "semis")


def _psd_root(S: np.ndarray) -> np.ndarray:
    """A matrix L with L Lᵀ = S (eigen-decomposition; tolerates a singular S)."""
    vals, vecs = np.linalg.eigh((S + S.T) / 2)
    return vecs * np.sqrt(np.clip(vals, 0, None))


def optimise(
    mu: pd.Series,
    cov: pd.DataFrame,
    w_eq: pd.Series,
    cfg: dict,
    vol_scale: float = 1.0,
    w_prev: pd.Series | None = None,
    long_only: bool = False,
) -> tuple[pd.Series, str]:
    """Mean-variance weights (`_optimise`), or their resampled average when `model.resample` is set
    (Michaud, 1998; research log H47): draws of μ ~ N(μ_BL, τΣ) and Σ ~ Wishart(T, Σ/T), T the
    covariance window in weeks; the weights of each draw are averaged and the average is projected
    back onto the constraints (closest feasible point in the least-squares sense)."""
    rs = cfg["model"].get("resample") or {}
    draws = int(rs.get("draws", 0))
    if draws <= 0:
        return _optimise(mu, cov, w_eq, cfg, vol_scale, w_prev, long_only)
    rng = np.random.default_rng(int(rs.get("seed", 0)))
    S = cov.to_numpy()
    n = len(S)
    T = int(cfg["model"]["cov_window_weeks"])
    tau = float(cfg["model"]["tau"])
    Lm = _psd_root(tau * S)
    Ls = _psd_root(S / T)
    ws = []
    for _ in range(draws):
        m_d = mu.to_numpy() + Lm @ rng.standard_normal(n)
        z = Ls @ rng.standard_normal((n, T))  # Wishart(T, Σ/T) as a sum of T outer products
        S_d = pd.DataFrame(z @ z.T, index=cov.index, columns=cov.index)
        w_d, st_d = _optimise(pd.Series(m_d, index=cov.index), S_d, w_eq, cfg, vol_scale, w_prev, long_only)
        if not st_d.startswith("fallback"):
            ws.append(w_d.to_numpy())
    if not ws:
        return _optimise(mu, cov, w_eq, cfg, vol_scale, w_prev, long_only)
    w, status = _optimise(mu, cov, w_eq, cfg, vol_scale, w_prev, long_only, project=np.mean(ws, axis=0))
    return w, f"resampled ({len(ws)} draws), {status}"


def _optimise(
    mu: pd.Series,
    cov: pd.DataFrame,
    w_eq: pd.Series,
    cfg: dict,
    vol_scale: float = 1.0,
    w_prev: pd.Series | None = None,
    long_only: bool = False,
    project: np.ndarray | None = None,
) -> tuple[pd.Series, str]:
    """Long/short mean-variance with costs, as a convex program (cvxpy, Clarabel solver):

        max  μ'w − δ/2 w'Σw − borrow'·max(−w, 0) − k·cost'·|w − w_prev|
        s.t. Σw = 1; bounds per line; Σ|w| ≤ gross; semiconductors net in [5%, 15%]; net equity in
             [20% × scale, 90%]; alternatives ≤ 15%; currency gross ≤ 20%; cash ≤ 10% outside the
             overlay; σ(w) ≤ σ(benchmark) × scale; tracking error ≤ 8%.

    If infeasible, the tracking-error cap, then the volatility cap are dropped (status says which).
    With `project`, the objective is instead the squared distance to those weights (same constraints)."""
    import cvxpy as cp

    m, uni, sl = cfg["model"], cfg["universe"], cfg["sleeves"]
    a = list(cov.index)
    n = len(a)
    S = cov.to_numpy()
    L = _psd_root(S)
    we = w_eq.reindex(a).fillna(0).to_numpy()
    w0 = w_prev.reindex(a).fillna(0).to_numpy() if w_prev is not None else we
    sleeve = np.array([uni[x]["sleeve"] for x in a])
    lo = np.array([float(uni[x].get("min", 0.0)) for x in a])
    hi = np.array([float(uni[x]["max"]) for x in a])
    if long_only:
        lo = np.maximum(lo, 0.0)
    if vol_scale >= 1.0:  # cash is a de-risking tool, not a default holding
        hi = np.where(sleeve == "cash", np.minimum(hi, sl.get("cash_max", 1.0)), hi)
    borrow = np.array([uni[x].get("borrow_bp", 0) / 1e4 for x in a])
    tc = np.array([uni[x]["cost_bp"] / 1e4 for x in a]) * m.get("turnover_aversion", 1.0)
    eqm = np.isin(sleeve, EQUITY_SLEEVES).astype(float)
    semis = (sleeve == "semis").astype(float)
    alt = (sleeve == "alt").astype(float)
    fx = sleeve == "fx"
    vol_b = float(np.linalg.norm(L.T @ we))
    vol_cap = m["vol_cap_vs_benchmark"] * vol_scale * vol_b

    w = cp.Variable(n)
    short = cp.Variable(n, nonneg=True)
    obj: cp.Minimize | cp.Maximize
    if project is not None:  # closest feasible point to resampled weights
        obj = cp.Minimize(cp.sum_squares(w - project))
    else:
        obj = cp.Maximize(
            mu.to_numpy() @ w
            - m["risk_aversion"] / 2 * cp.sum_squares(L.T @ w)
            - borrow @ short
            - tc @ cp.abs(w - w0)
        )
    # the cash cap and the equity floor are the two limits a forced de-risking may lift (H44)
    soft = [w <= hi, eqm @ w >= sl["equity_net"]["min"] * vol_scale]
    base = [
        cp.sum(w) == 1,
        w >= lo,
        short >= -w,
        cp.norm1(w) <= sl.get("gross_max", 1.0),
        eqm @ w <= sl["equity_net"]["max"],
    ]
    if semis.sum():
        s_lo = min(sl["semis"]["min"], float(hi @ semis))
        base += [semis @ w >= s_lo, semis @ w <= sl["semis"]["max"]]
    if alt.sum():
        base.append(alt @ w <= sl.get("alt_max", 1.0))
    if fx.any():
        base.append(cp.norm1(w[np.where(fx)[0]]) <= sl.get("fx_gross_max", 1.0))
    vol_c = cp.norm(L.T @ w) <= vol_cap
    te_c = cp.norm(L.T @ (w - we)) <= m["tracking_error_max"]
    fallbacks = [("tracking error relaxed", [*soft, vol_c]), ("vol cap relaxed", soft)]
    if m.get("on_infeasible") == "cash":  # research log H44: de-risk into cash rather than drop a limit
        relaxed_soft = [w <= np.where(sleeve == "cash", 1.0, hi), eqm @ w >= 0]
        fallbacks = [
            ("forced cash", [*relaxed_soft, vol_c, te_c]),
            ("forced cash, TE relaxed", [*relaxed_soft, vol_c]),
        ]
    for status, extra in (("optimal", [*soft, vol_c, te_c]), *fallbacks):
        prob = cp.Problem(obj, base + extra)
        try:
            prob.solve(solver=cp.CLARABEL)
        except cp.SolverError:
            continue
        if prob.status in ("optimal", "optimal_inaccurate") and w.value is not None:
            x = np.where(np.abs(w.value) < 1e-6, 0.0, w.value)
            return pd.Series(x / x.sum(), index=a), status
    x = np.clip(we, lo, hi)
    return pd.Series(x / x.sum(), index=a), "fallback: equilibrium"


def apply_band(target: pd.Series, current: pd.Series, band: float, cash: str = "BIL") -> pd.Series:
    """Skip trades smaller than `band`; the cash line absorbs the difference."""
    cur = current.reindex(target.index).fillna(0.0)
    out = target.where((target - cur).abs() >= band, cur)
    if cash in out.index:
        out[cash] = max(0.0, out[cash] + 1 - out.sum())
    return out / out.sum()


def overlay_scale(drawdown: float, state: int, cfg: dict) -> int:
    """Drawdown overlay state machine. state: number of levels engaged (0 = full risk)."""
    od = cfg["model"]["drawdown_overlay"]
    levels, rec = od["levels"], od["recover_at"]
    new = state
    for k, lv in enumerate(levels, start=1):
        if drawdown >= lv["drawdown"]:
            new = max(new, k)
    while new > 0 and drawdown < rec * levels[new - 1]["drawdown"]:
        new -= 1
    return new


def scale_of(state: int, cfg: dict) -> float:
    lv = cfg["model"]["drawdown_overlay"]["levels"]
    return 1.0 if state == 0 else float(lv[state - 1]["scale"])


# ------------------------------------------------------------------ one rebalance
@dataclass
class Inputs:
    r: pd.DataFrame  # weekly USD returns
    macro: pd.DataFrame  # weekly macro factors
    fundamentals: dict[str, pd.Series] = field(default_factory=dict)
    tone: dict[str, pd.Series] = field(default_factory=dict)
    regime: pd.Series = field(default_factory=lambda: pd.Series(dtype=object))
    carry: pd.DataFrame = field(default_factory=pd.DataFrame)
    house: list = field(default_factory=list)
    hedge: pd.DataFrame = field(default_factory=pd.DataFrame)  # weekly SPY price, VIX, cash yield (%)
    cache: dict = field(default_factory=dict, repr=False)  # covariance and views by date, shared by variants


def views_at(inp: Inputs, t, assets: list[str], cfg: dict) -> dict[str, pd.Series]:
    r = inp.r.loc[:t, assets]
    v = {"trend": trend_scores(r, cfg["model"].get("trend_horizons"))}
    if not inp.macro.empty:
        f = inp.macro.loc[:t]
        if not f.empty:
            v["macro"] = macro_scores(f.iloc[-1], assets, cfg)
    v["regime"] = regime_scores(r, inp.regime, t)
    v["value"] = value_scores(r, cfg)
    v["carry"] = carry_scores(inp.carry, t).reindex([a for a in assets if a in inp.carry]).dropna()
    semis = [a for a in assets if cfg["universe"][a]["sleeve"] == "semis"]
    if semis:
        v["micro"] = micro_scores(r, semis, inp.fundamentals, t)
    v["house"] = house_scores(inp.house, t, assets)
    v["news"] = news_scores(inp.tone, t, assets, cfg)
    return v


def target_at(
    inp: Inputs,
    t,
    cfg: dict,
    families=FAMILIES,
    vol_scale: float = 1.0,
    w_prev: pd.Series | None = None,
    long_only: bool = False,
) -> dict:
    m = cfg["model"]
    key = (t, m.get("cov_halflife_weeks"), tuple(m.get("trend_horizons") or ()), tuple(cfg["universe"]))
    if key not in inp.cache:
        assets = [a for a in cfg["universe"] if a in inp.r.columns]
        c = covariance(
            inp.r.loc[:t, assets], m["cov_window_weeks"], m["cov_min_weeks"], m.get("cov_halflife_weeks")
        )
        inp.cache[key] = (c, views_at(inp, t, list(c.index), cfg))
    cov, all_views = inp.cache[key]
    w_eq = equilibrium_weights(list(cov.index), cfg)
    views = {k: v for k, v in all_views.items() if k in families}
    mu, pi = black_litterman(cov, w_eq, views, cfg)
    w, status = optimise(mu, cov, w_eq, cfg, vol_scale, w_prev, long_only)
    return {"weights": w, "status": status, "mu": mu, "pi": pi, "cov": cov, "w_eq": w_eq, "views": views}


# ------------------------------------------------------------------ backtest
def _costs(cfg: dict, assets) -> pd.Series:
    return pd.Series({a: cfg["universe"][a]["cost_bp"] / 1e4 for a in assets})


def backtest(
    inp: Inputs,
    cfg: dict,
    start: str | None = None,
    families=FAMILIES,
    overlay: bool = True,
    views: bool = True,
    long_only: bool = False,
    tail_hedge: bool = True,
    rebalance: str | None = None,
) -> dict:
    """Walk-forward simulation. Rebalance every week (or the first week of each month with
    rebalance='monthly'), and whenever the drawdown overlay changes state; weights drift in between;
    trading costs on every trade, borrow costs on shorts, and the tail-hedge puts' premium and payoff."""
    r = inp.r
    start = pd.Timestamp(start or cfg["backtest"]["start"])
    weeks = r.loc[start:].index
    fam = families if views else ()
    freq = rebalance or cfg["model"].get("rebalance", "monthly")
    uni = cfg["universe"]
    borrow = pd.Series({a: uni[a].get("borrow_bp", 0) / 1e4 / WEEKS for a in uni})
    eq_names = [a for a in uni if uni[a]["sleeve"] in EQUITY_SLEEVES]
    semis_names = [a for a in uni if uni[a]["sleeve"] == "semis"]
    th = cfg["model"].get("tail_hedge")
    hedge_on = tail_hedge and th is not None and not inp.hedge.empty
    w = pd.Series(dtype=float)
    nav, peak, state = 1.0, 1.0, 0
    rets, hist, log, hedges = [], {}, [], []
    prev_month = None
    put = None  # (notional share of NAV, strike/spot, spot at purchase, premium as share of spot)
    for t in weeks[:-1]:
        nxt = r.index[r.index.get_loc(t) + 1]
        dd = 1 - nav / peak
        new_state = overlay_scale(dd, state, cfg) if overlay else 0
        new_month = t.month != prev_month
        due = freq == "weekly" or new_month
        cost, hedge_pnl = 0.0, 0.0
        if due or new_state != state or w.empty:
            tg = target_at(inp, t, cfg, fam, scale_of(new_state, cfg), w if not w.empty else None, long_only)
            target = tg["weights"]
            if not w.empty:
                target = apply_band(target, w, cfg["model"]["no_trade_band"])
            cur = w.reindex(target.index.union(w.index)).fillna(0.0)
            tgt = target.reindex(cur.index).fillna(0.0)
            cost = float(((tgt - cur).abs() * _costs(cfg, cur.index)).sum())
            turnover = float((tgt - cur).abs().sum() / 2)
            w = tgt[tgt.abs() > 1e-6]
            hist[t] = w
            log.append(
                {"date": t, "status": tg["status"], "overlay": new_state, "turnover": turnover, "cost": cost}
            )
            state = new_state
        if hedge_on and new_month and t in inp.hedge.index:
            hx = inp.hedge.loc[t]
            sox = th.get("underlying") == "SOX" and "sox_spot" in hx and hx["sox_spot"] == hx["sox_spot"]
            spot = float(hx["sox_spot"]) if sox else float(hx["spot"])
            if put is not None:  # the previous month's put expires: payoff
                hedge_pnl += put[0] * max(put[1] - spot / put[2], 0.0)
            ratio = hedge_ratio(float(hx.get("stress", 0.0)), float(hx.get("trend", 0.0)), cfg)
            names = semis_names if sox else eq_names
            eq_net = max(float(w.reindex(names).fillna(0).sum()), 0.0)
            vol = (
                float(hx["vix"])
                / 100
                * (1 + th["skew_premium"])
                * (float(hx["sox_vol_ratio"]) if sox else 1.0)
            )
            k = th["moneyness"]
            prem = bs_put(1.0, k, 4 / WEEKS, float(hx["rate"]) / 100, vol)
            notional = ratio * eq_net
            hedge_pnl -= notional * prem
            put = (notional, k, spot, prem)
            hedges.append({"date": t, "hedged share of NAV": notional, "premium (% of NAV)": notional * prem})
        if new_month:
            prev_month = t.month
        rn = r.loc[nxt, w.index].fillna(0.0)
        gross = float((w * rn).sum())
        carry_cost = float((w.clip(upper=0).abs() * borrow.reindex(w.index).fillna(0)).sum())
        net = (1 - cost) * (1 + gross) - 1 - carry_cost + hedge_pnl
        w = w * (1 + rn) / (1 + gross)
        nav *= 1 + net
        peak = max(peak, nav)
        rets.append((nxt, net))
    ret = pd.Series(dict(rets)).sort_index()
    return {
        "returns": ret,
        "weights": pd.DataFrame(hist).T.fillna(0.0),
        "log": pd.DataFrame(log).set_index("date"),
        "hedges": pd.DataFrame(hedges).set_index("date") if hedges else pd.DataFrame(),
        "final_weights": w,
        "overlay_state": state,
    }


def factor_exposures(w: pd.Series, r: pd.DataFrame, factors=("SPY", "IEF", "UUP", "DBC", "GLD")) -> pd.Series:
    """Betas of today's weights to the main risk factors, by regression of the portfolio's weekly
    returns over the last three years on factor returns."""
    a = [x for x in w.index if x in r]
    f = [x for x in factors if x in r]
    h = r.iloc[-156:]
    y = (h[a].fillna(0) @ w.reindex(a).fillna(0)).to_numpy()
    X = h[f].fillna(0).to_numpy()
    X1 = np.column_stack([np.ones(len(X)), X])
    coef, *_ = np.linalg.lstsq(X1, y, rcond=None)
    return pd.Series(coef[1:], index=f)


# ------------------------------------------------------------------ metrics
def drawdown(ret: pd.Series) -> pd.Series:
    nav = (1 + ret).cumprod()
    return nav / nav.cummax() - 1


def metrics(ret: pd.Series, cash: pd.Series, bench: pd.Series | None = None) -> dict:
    ret = ret.dropna()
    c = cash.reindex(ret.index).fillna(0.0)
    n = len(ret)
    nav = (1 + ret).prod()
    ex = ret - c
    out = {
        "annual return": nav ** (WEEKS / n) - 1,
        "volatility": ret.std() * np.sqrt(WEEKS),
        "Sharpe": ex.mean() / ret.std() * np.sqrt(WEEKS),
        "max drawdown": float(drawdown(ret).min()),
        "worst 52 weeks": float(((1 + ret).rolling(WEEKS).apply(np.prod, raw=True) - 1).min()),
    }
    out["Calmar"] = out["annual return"] / abs(out["max drawdown"]) if out["max drawdown"] else np.nan
    if bench is not None:
        a = (ret - bench.reindex(ret.index)).dropna()
        out["tracking error"] = a.std() * np.sqrt(WEEKS)
        out["information ratio"] = a.mean() / a.std() * np.sqrt(WEEKS) if a.std() > 0 else np.nan
        b = bench.reindex(ret.index)
        out["beta to benchmark"] = float(np.cov(ret, b.fillna(0))[0, 1] / b.var())
    return out


def deflated_sharpe(ret: pd.Series, trial_sharpes: list[float]) -> float:
    """Bailey and López de Prado (2014): probability that the true Sharpe ratio exceeds the
    expected maximum of `len(trial_sharpes)` unskilled trials. Per-period Sharpe ratios."""
    r = ret.dropna()
    t = len(r)
    sr = r.mean() / r.std()
    n = max(len(trial_sharpes), 1)
    v = np.var(trial_sharpes, ddof=1) if n > 1 else 0.0
    g = 0.5772156649
    sr0 = (
        np.sqrt(v) * ((1 - g) * stats.norm.ppf(1 - 1 / n) + g * stats.norm.ppf(1 - 1 / (n * np.e)))
        if n > 1
        else 0.0
    )
    sk, ku = stats.skew(r), stats.kurtosis(r, fisher=False)
    den = np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr**2)
    return float(stats.norm.cdf((sr - sr0) * np.sqrt(t - 1) / den))


def risk_report(w: pd.Series, cov: pd.DataFrame, w_eq: pd.Series, r: pd.DataFrame) -> dict:
    """Ex-ante risk of a weight vector: volatility, tracking error, contributions, and weekly
    VaR / expected shortfall at 95% by historical simulation on the last three years."""
    a = [x for x in w.index if x in cov.index]
    wv = w.reindex(a).fillna(0).to_numpy()
    S = cov.loc[a, a].to_numpy()
    we = w_eq.reindex(a).fillna(0).to_numpy()
    var = wv @ S @ wv
    rc = pd.Series(wv * (S @ wv) / var, index=a)
    h = (r[a].iloc[-156:].fillna(0) @ wv).dropna()
    q = float(np.quantile(h, 0.05))
    return {
        "volatility": float(np.sqrt(var)),
        "benchmark volatility": float(np.sqrt(we @ S @ we)),
        "tracking error": float(np.sqrt((wv - we) @ S @ (wv - we))),
        "risk contribution": rc,
        "VaR 95% (1 week)": -q,
        "expected shortfall 95% (1 week)": float(-h[h <= q].mean()),
    }


# Return sources for the risk budget, by sleeve; `risk_sources` in config/portfolio.yaml overrides
# single instruments whose sleeve is ambiguous (inflation-linked bonds, the semiconductor index...).
SOURCE_OF_SLEEVE = {
    "equity": "equity",
    "style": "equity",
    "sector": "equity",
    "semis": "semis",
    "bond": "rates (duration)",
    "cash": "rates (duration)",
    "credit": "credit",
    "real": "commodities",
    "alt": "alternatives",
    "fx": "FX",
}


def risk_source(asset: str, cfg: dict) -> str:
    over = cfg.get("risk_sources") or {}
    if asset in over:
        return over[asset]
    return SOURCE_OF_SLEEVE.get(cfg["universe"].get(asset, {}).get("sleeve", ""), "other")


def risk_budget(
    w: pd.Series, cov: pd.DataFrame, r: pd.DataFrame, cfg: dict, weeks: int = 156
) -> pd.DataFrame:
    """Share of variance by return source (equity, rates, inflation, credit, FX, semis, commodities,
    alternatives): Euler contributions w_i (Σw)_i / w'Σw summed by source, so the shares sum to 1
    (negative when a source hedges the rest). Ex ante with the model covariance, and realised with
    the sample covariance of the last `weeks` weekly returns; with net and gross weight per source."""
    a = [x for x in w.index if x in cov.index and abs(w[x]) > 1e-9]
    wv = w.reindex(a).to_numpy()
    src = pd.Series({x: risk_source(x, cfg) for x in a})

    def shares(S: np.ndarray) -> pd.Series:
        v = wv @ S @ wv
        return pd.Series(wv * (S @ wv) / v, index=a).groupby(src).sum() if v > 0 else pd.Series(dtype=float)

    ex = shares(cov.loc[a, a].to_numpy())
    h = r.reindex(columns=a).iloc[-weeks:].fillna(0.0)
    real = shares(h.cov().to_numpy() * WEEKS) if len(h) > 10 else pd.Series(dtype=float)
    out = pd.DataFrame(
        {
            "ex-ante share": ex,
            "realised share (3y)": real,
            "net weight": pd.Series(wv, index=a).groupby(src).sum(),
            "gross weight": pd.Series(np.abs(wv), index=a).groupby(src).sum(),
        }
    )
    return out.sort_values("ex-ante share", ascending=False)


STYLE_FACTORS = {
    "market": ("SPY", "BIL"),
    "value": ("VLUE", "SPY"),
    "momentum": ("MTUM", "SPY"),
    "quality": ("QUAL", "SPY"),
    "size (equal weight)": ("RSP", "SPY"),
    "min vol": ("USMV", "SPY"),
}


def _style_regression(y: pd.Series, r: pd.DataFrame, lags: int = 4) -> dict:
    """OLS of weekly returns y on long-short style factors, Newey-West (HAC) t-statistics.
    Alpha is annualised (52 weeks); factors whose ETFs are missing are left out."""
    import statsmodels.api as sm

    f = pd.DataFrame({k: r[a] - r[b] for k, (a, b) in STYLE_FACTORS.items() if a in r and b in r})
    d = pd.concat([y.rename("y"), f], axis=1).dropna()
    if len(d) < 30 or f.empty:
        return {
            "loadings": pd.DataFrame(),
            "alpha (annual)": np.nan,
            "alpha t": np.nan,
            "R²": np.nan,
            "weeks": len(d),
        }
    fit = sm.OLS(d["y"], sm.add_constant(d.drop(columns="y"))).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    lo = pd.DataFrame({"loading": fit.params, "t-stat": fit.tvalues}).drop(index="const")
    return {
        "loadings": lo,
        "alpha (annual)": float(fit.params["const"] * WEEKS),
        "alpha t": float(fit.tvalues["const"]),
        "R²": float(fit.rsquared),
        "weeks": len(d),
    }


def style_exposures(w: pd.Series, r: pd.DataFrame, weeks: int = 156) -> dict:
    """Style exposures of today's weights: their simulated weekly excess return over the last
    `weeks` (excess of T-bills) regressed on market, value, momentum, quality, size and min-vol."""
    a = [x for x in w.index if x in r.columns]
    h = r[a].iloc[-weeks:]
    y = h.fillna(0.0) @ w.reindex(a).fillna(0.0)
    if "BIL" in r:
        y = y - r["BIL"].reindex(y.index).fillna(0.0)
    return _style_regression(y, r.loc[h.index])


def alpha_decomposition(ret: pd.Series, r: pd.DataFrame, bench: pd.Series | None = None) -> dict:
    """The backtest's active return (over `bench`, else over T-bills) regressed on the style
    factors: what is left (alpha) is not explained by exposures one could buy as ETFs (H46)."""
    base = bench if bench is not None else r.get("BIL", pd.Series(0.0, index=ret.index))
    y = (ret - base.reindex(ret.index)).dropna()
    return _style_regression(y, r.reindex(y.index))


def information_coefficient(signal: pd.Series, fwd: pd.Series) -> dict:
    """Spearman correlation between a signal and the forward return, and its t-statistic on the
    paired observations (callers pass non-overlapping samples)."""
    d = pd.concat([signal, fwd], axis=1).dropna()
    n = len(d)
    if n < 8:
        return {"IC": np.nan, "t": np.nan, "n": n}
    ic = float(stats.spearmanr(d.iloc[:, 0], d.iloc[:, 1])[0])
    return {"IC": ic, "t": ic * np.sqrt((n - 2) / max(1e-12, 1 - ic**2)), "n": n}


# ------------------------------------------------------------------ alternative constructions
def min_variance(cov: pd.DataFrame) -> pd.Series:
    """Long-only minimum variance (convex program)."""
    import cvxpy as cp

    L = _psd_root(cov.to_numpy())
    w = cp.Variable(len(cov))
    cp.Problem(cp.Minimize(cp.sum_squares(L.T @ w)), [cp.sum(w) == 1, w >= 0]).solve(solver=cp.CLARABEL)
    x = np.clip(w.value, 0, None)
    return pd.Series(x / x.sum(), index=cov.index)


def equal_risk_contribution(cov: pd.DataFrame, iters: int = 500) -> pd.Series:
    """Equal risk contribution (Maillard, Roncalli and Teïletche, 2010) by cyclical coordinate descent."""
    S = cov.to_numpy()
    n = len(S)
    w = 1 / np.sqrt(np.diag(S))
    w /= w.sum()
    for _ in range(iters):  # unnormalised fixed point w_i (Σw)_i = 1/n, normalised at the end
        for i in range(n):
            a = S[i, i]
            b = S[i] @ w - a * w[i]
            w[i] = (-b + np.sqrt(b * b + 4 * a / n)) / (2 * a)
    return pd.Series(w / w.sum(), index=cov.index)


def hierarchical_risk_parity(cov: pd.DataFrame) -> pd.Series:
    """López de Prado (2016): cluster on correlation distance, order the matrix, split the budget
    by inverse variance between clusters, recursively."""
    from scipy.cluster.hierarchy import leaves_list, linkage
    from scipy.spatial.distance import squareform

    sd = np.sqrt(np.diag(cov))
    corr = cov.to_numpy() / np.outer(sd, sd)
    dist = np.sqrt(np.clip(0.5 * (1 - corr), 0, None))
    np.fill_diagonal(dist, 0)
    order = list(leaves_list(linkage(squareform(dist, checks=False), "single")))
    w = np.ones(len(cov))
    S = cov.to_numpy()

    def cvar(idx):
        sub = S[np.ix_(idx, idx)]
        ivp = 1 / np.diag(sub)
        ivp /= ivp.sum()
        return ivp @ sub @ ivp

    stack = [order]
    while stack:
        c = stack.pop()
        if len(c) < 2:
            continue
        a, b = c[: len(c) // 2], c[len(c) // 2 :]
        va, vb = cvar(a), cvar(b)
        alpha = 1 - va / (va + vb)
        w[a] *= alpha
        w[b] *= 1 - alpha
        stack += [a, b]
    return pd.Series(w / w.sum(), index=cov.index)


ALTERNATIVES = {
    "equal weight": lambda cov: pd.Series(1 / len(cov), index=cov.index),
    "minimum variance": min_variance,
    "equal risk contribution": equal_risk_contribution,
    "hierarchical risk parity": hierarchical_risk_parity,
}


def backtest_rule(
    inp: Inputs, cfg: dict, rule: Callable[[pd.DataFrame], pd.Series], start: str | None = None
) -> pd.Series:
    """Monthly rebalance into `rule(covariance)` on the same universe and costs, no views, no overlay,
    no constraints beyond long-only: the textbook constructions the model is compared with."""
    r = inp.r
    start_t = pd.Timestamp(start or cfg["backtest"]["start"])
    weeks = r.loc[start_t:].index
    w = pd.Series(dtype=float)
    rets, prev_month = [], None
    m = cfg["model"]
    assets = [a for a in cfg["universe"] if a in r.columns]
    for t in weeks[:-1]:
        nxt = r.index[r.index.get_loc(t) + 1]
        cost = 0.0
        if t.month != prev_month:
            cov = covariance(r.loc[:t, assets], m["cov_window_weeks"], m["cov_min_weeks"])
            tgt = rule(cov)
            cur = w.reindex(tgt.index.union(w.index)).fillna(0.0)
            tg = tgt.reindex(cur.index).fillna(0.0)
            cost = float(((tg - cur).abs() * _costs(cfg, cur.index)).sum())
            w, prev_month = tg[tg > 1e-6], t.month
        rn = r.loc[nxt, w.index].fillna(0.0)
        g = float((w * rn).sum())
        w = w * (1 + rn) / (1 + g)
        rets.append((nxt, (1 - cost) * (1 + g) - 1))
    return pd.Series(dict(rets)).sort_index()
