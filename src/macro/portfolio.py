"""Systematic balanced portfolio: macro and micro signals into a 60/40-benchmarked allocation.

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
from scipy import optimize, stats

from macro.config import ROOT

PATH = ROOT / "config" / "portfolio.yaml"
WEEKS = 52
FAMILIES = ("trend", "macro", "micro", "news")
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


def covariance(r: pd.DataFrame, window: int, min_weeks: int) -> pd.DataFrame:
    """Annualised covariance of the assets with at least `min_weeks` of the last `window` weeks."""
    h = r.iloc[-window:]
    h = h.loc[:, h.notna().sum() >= min_weeks]
    vol = h.std() * np.sqrt(WEEKS)
    z = ((h - h.mean()) / h.std()).fillna(0.0).to_numpy()  # missing weeks: no information
    corr, _ = ledoit_wolf_corr(z)
    cov = corr * np.outer(vol, vol)
    return pd.DataFrame(cov, index=h.columns, columns=h.columns)


# ------------------------------------------------------------------ signals
def _cum(r: pd.DataFrame) -> pd.Series:
    return (1 + r.fillna(0)).prod() - 1


def trend_scores(r: pd.DataFrame) -> pd.Series:
    """12-month return skipping the last month, over its annual volatility, squashed by tanh."""
    h = r.iloc[-WEEKS:]
    ok = h.notna().sum() >= 48
    r12_1 = _cum(h.iloc[:-4])
    vol = h.std() * np.sqrt(WEEKS)
    return np.tanh(r12_1 / vol.replace(0, np.nan)).where(ok).dropna()


# macro loadings: score = Σ loading × factor; factors in [-1, 1]
MACRO_LOADINGS = {
    "equity": {"recession": -0.5, "stress": -0.5},
    "semis": {"recession": -0.5, "stress": -0.5},
    "LQD": {"recession": -0.4, "stress": -0.4},
    "AGG": {"recession": 0.3, "inflation": -0.3},
    "IEF": {"recession": 0.5, "inflation": -0.4},
    "TLT": {"recession": 0.5, "inflation": -0.5},
    "TIP": {"inflation": 0.5},
    "GLD": {"inflation": 0.3, "stress": 0.3},
    "DBC": {"inflation": 0.5, "recession": -0.3},
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


def news_scores(tone: dict[str, pd.Series], t, assets: list[str], cfg: dict) -> pd.Series:
    """Tone relative to its last year, z-scored: memory tone for the memory makers, recession tone
    for equities (a darker tone lowers the score)."""

    def z(s):
        if s is None:
            return None
        w = s.dropna().resample("W-FRI").mean().loc[:t]
        if len(w) < 60:
            return None
        h = w.iloc[-WEEKS:]
        return float(np.tanh((w.iloc[-1] - h.mean()) / (h.std() or np.nan)))

    out = {}
    zm, zr = z(tone.get("NEWS_TONE_MEMORY")), z(tone.get("NEWS_TONE_RECESSION"))
    for a in assets:
        sl = cfg["universe"][a]["sleeve"]
        if zm is not None and a in MEMORY_BASKET:
            out[a] = zm
        elif zr is not None and sl in ("equity", "semis"):
            out[a] = 0.5 * zr
    return pd.Series(out, dtype=float).dropna()


# ------------------------------------------------------------------ Black-Litterman
def equilibrium_weights(assets: list[str], cfg: dict) -> pd.Series:
    """Benchmark mapped on the available assets; a missing equity region's weight goes to SPY,
    a missing bond to AGG."""
    w = pd.Series(cfg["equilibrium"], dtype=float)
    out = pd.Series(0.0, index=assets)
    for a, v in w.items():
        if a in out.index:
            out[a] += v
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
    rows, q, om = [], [], []
    for fam, sc in views.items():
        c = float(m["confidence"].get(fam, 0.0))
        if c <= 0:
            continue
        for a, s in sc.items():
            if a not in cov.index or s != s:
                continue
            i = cov.index.get_loc(a)
            p = np.zeros(len(cov))
            p[i] = 1.0
            rows.append(p)
            q.append(pi[i] + kappa * sig[i] * s)
            om.append(tau * sig[i] ** 2 * (1 - c) / c)
    if not rows:
        return pd.Series(pi, index=cov.index), pd.Series(pi, index=cov.index)
    P, Q, Om = np.array(rows), np.array(q), np.diag(om)
    ts_inv = np.linalg.inv(tau * S)
    A = ts_inv + P.T @ np.linalg.inv(Om) @ P
    b = ts_inv @ pi + P.T @ np.linalg.inv(Om) @ Q
    mu = np.linalg.solve(A, b)
    return pd.Series(mu, index=cov.index), pd.Series(pi, index=cov.index)


# ------------------------------------------------------------------ optimiser
def optimise(
    mu: pd.Series,
    cov: pd.DataFrame,
    w_eq: pd.Series,
    cfg: dict,
    vol_scale: float = 1.0,
    w_prev: pd.Series | None = None,
) -> tuple[pd.Series, str]:
    """Mean-variance under the configured constraints. Returns weights and a status: 'optimal',
    or the constraint that had to be relaxed."""
    m, uni, sl = cfg["model"], cfg["universe"], cfg["sleeves"]
    a = list(cov.index)
    S, mv, we = cov.to_numpy(), mu.to_numpy(), w_eq.reindex(a).fillna(0).to_numpy()
    delta = m["risk_aversion"]
    vol_b = float(np.sqrt(we @ S @ we))
    vol_cap = m["vol_cap_vs_benchmark"] * vol_scale * vol_b
    semis = np.array([uni[x]["sleeve"] == "semis" for x in a], float)
    eqmask = np.array([uni[x]["sleeve"] in ("equity", "semis") for x in a], float)
    eq_b = float(we @ eqmask)
    lo = np.array([uni[x].get("min", 0.0) for x in a])
    hi = np.array([uni[x]["max"] for x in a])
    if vol_scale >= 1.0:  # cash is a de-risking tool, not a default holding
        hi = np.where([uni[x]["sleeve"] == "cash" for x in a], np.minimum(hi, sl.get("cash_max", 1.0)), hi)
    has_semis = semis.sum() > 0
    s_lo = min(sl["semis"]["min"], float(hi @ semis)) if has_semis else 0.0
    band = sl["equity_total_band"]

    def cons(with_te: bool, with_vol: bool):
        """Constraints with analytic gradients (finite differences made SLSQP ten times slower)."""
        ones = np.ones(len(a))
        c = [{"type": "eq", "fun": lambda w: w.sum() - 1, "jac": lambda w: ones}]
        if has_semis:
            c += [
                {"type": "ineq", "fun": lambda w: w @ semis - s_lo, "jac": lambda w: semis},
                {"type": "ineq", "fun": lambda w: sl["semis"]["max"] - w @ semis, "jac": lambda w: -semis},
            ]
        c += [
            {
                "type": "ineq",
                "fun": lambda w: w @ eqmask - (eq_b - band) * vol_scale,
                "jac": lambda w: eqmask,
            },
            {"type": "ineq", "fun": lambda w: eq_b + band - w @ eqmask, "jac": lambda w: -eqmask},
        ]
        if with_vol:
            c.append({"type": "ineq", "fun": lambda w: vol_cap**2 - w @ S @ w, "jac": lambda w: -2 * S @ w})
        if with_te:
            te2 = m["tracking_error_max"] ** 2
            c.append(
                {
                    "type": "ineq",
                    "fun": lambda w: te2 - (w - we) @ S @ (w - we),
                    "jac": lambda w: -2 * S @ (w - we),
                }
            )
        return c

    def obj(w):
        return -(w @ mv) + delta / 2 * (w @ S @ w)

    def jac(w):
        return -mv + delta * (S @ w)

    x0 = np.clip(w_prev.reindex(a).fillna(0).to_numpy() if w_prev is not None else we, lo, hi)
    x0 = x0 / x0.sum() if x0.sum() > 0 else np.full(len(a), 1 / len(a))
    for status, te, vol in (
        ("optimal", True, True),
        ("tracking error relaxed", False, True),
        ("vol cap relaxed", False, False),
    ):
        res = optimize.minimize(
            obj,
            x0,
            jac=jac,
            method="SLSQP",
            bounds=list(zip(lo, hi, strict=True)),
            constraints=cons(te, vol),
            options={"maxiter": 300, "ftol": 1e-10},
        )
        if res.success:
            w = np.clip(res.x, 0, None)
            return pd.Series(w / w.sum(), index=a), status
    return pd.Series(np.clip(we, lo, hi) / np.clip(we, lo, hi).sum(), index=a), "fallback: equilibrium"


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
    cache: dict = field(default_factory=dict, repr=False)  # covariance and views by date, shared by variants


def views_at(inp: Inputs, t, assets: list[str], cfg: dict) -> dict[str, pd.Series]:
    r = inp.r.loc[:t, assets]
    v = {"trend": trend_scores(r)}
    if not inp.macro.empty:
        f = inp.macro.loc[:t]
        if not f.empty:
            v["macro"] = macro_scores(f.iloc[-1], assets, cfg)
    semis = [a for a in assets if cfg["universe"][a]["sleeve"] == "semis"]
    if semis:
        v["micro"] = micro_scores(r, semis, inp.fundamentals, t)
    v["news"] = news_scores(inp.tone, t, assets, cfg)
    return v


def target_at(
    inp: Inputs, t, cfg: dict, families=FAMILIES, vol_scale: float = 1.0, w_prev: pd.Series | None = None
) -> dict:
    m = cfg["model"]
    if t not in inp.cache:
        assets = [a for a in cfg["universe"] if a in inp.r.columns]
        c = covariance(inp.r.loc[:t, assets], m["cov_window_weeks"], m["cov_min_weeks"])
        inp.cache[t] = (c, views_at(inp, t, list(c.index), cfg))
    cov, all_views = inp.cache[t]
    w_eq = equilibrium_weights(list(cov.index), cfg)
    views = {k: v for k, v in all_views.items() if k in families}
    mu, pi = black_litterman(cov, w_eq, views, cfg)
    w, status = optimise(mu, cov, w_eq, cfg, vol_scale, w_prev)
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
) -> dict:
    """Walk-forward simulation: monthly rebalance (first Friday of the month, or when the overlay
    state changes), weights drift in between, costs on every trade."""
    r = inp.r
    start = pd.Timestamp(start or cfg["backtest"]["start"])
    weeks = r.loc[start:].index
    fam = families if views else ()
    w = pd.Series(dtype=float)
    nav, peak, state = 1.0, 1.0, 0
    rets, hist, log = [], {}, []
    prev_month = None
    for t in weeks[:-1]:
        nxt = r.index[r.index.get_loc(t) + 1]
        dd = 1 - nav / peak
        new_state = overlay_scale(dd, state, cfg) if overlay else 0
        monthly = t.month != prev_month
        if monthly or new_state != state or w.empty:
            tg = target_at(inp, t, cfg, fam, scale_of(new_state, cfg), w if not w.empty else None)
            target = tg["weights"]
            if not w.empty:
                target = apply_band(target, w, cfg["model"]["no_trade_band"])
            cur = w.reindex(target.index.union(w.index)).fillna(0.0)
            tgt = target.reindex(cur.index).fillna(0.0)
            cost = float(((tgt - cur).abs() * _costs(cfg, cur.index)).sum())
            turnover = float((tgt - cur).abs().sum() / 2)
            w = tgt[tgt > 1e-6]
            hist[t] = w
            log.append(
                {"date": t, "status": tg["status"], "overlay": new_state, "turnover": turnover, "cost": cost}
            )
            state, prev_month = new_state, t.month
        else:
            cost = 0.0
        rn = r.loc[nxt, w.index].fillna(0.0)
        gross = float((w * rn).sum())
        net = (1 - cost) * (1 + gross) - 1
        w = w * (1 + rn) / (1 + gross)
        nav *= 1 + net
        peak = max(peak, nav)
        rets.append((nxt, net))
    ret = pd.Series(dict(rets)).sort_index()
    return {
        "returns": ret,
        "weights": pd.DataFrame(hist).T.fillna(0.0),
        "log": pd.DataFrame(log).set_index("date"),
        "final_weights": w,
        "overlay_state": state,
    }


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


def information_coefficient(signal: pd.Series, fwd: pd.Series) -> dict:
    """Spearman correlation between a signal and the forward return, and its t-statistic on the
    paired observations (callers pass non-overlapping samples)."""
    d = pd.concat([signal, fwd], axis=1).dropna()
    n = len(d)
    if n < 8:
        return {"IC": np.nan, "t": np.nan, "n": n}
    ic = float(stats.spearmanr(d.iloc[:, 0], d.iloc[:, 1])[0])
    return {"IC": ic, "t": ic * np.sqrt((n - 2) / max(1e-12, 1 - ic**2)), "n": n}
