"""Synthetic data generator for MACRO_MODE=demo (tests, CI, offline use).

A small, coherent monthly macro simulator for the US, the euro area and Japan, then mapped to
every id in `config/series.yaml` at its native frequency. Numbers are SIMULATED: they carry no
information about real markets and must never be published (export scripts refuse demo mode).

Structure (monthly, t = month):
  oil        o_t = o_{t-1} + 0.003 + 0.07 e_t + scripted supply shocks             (log level)
  GSCPI      g_t = 0.85 g_{t-1} + 0.35 e_t + scripted supply-chain episode
  gap        x_t = 1.25 x_{t-1} - 0.35 x_{t-2} - 0.06 (r_{t-3} - r*_t) + 0.3 d_t + e_t + crises
  unemp.     u_t = u*_t - 0.45 x_t + e_t                                            (Okun)
  core trend tau_t = 0.9 tau_{t-1} + 0.1 pi^e_t + 0.05 x_{t-1} + 0.10 g_t + e_t     (Phillips)
  expect.    pi^e_t = 0.97 pi^e_{t-1} + 0.03*2 + 0.01 (pi_{t-1}^{yoy} - 2) + e_t
  policy     i*_t = r*_t + pi^{core,yoy}_t + 0.5 (pi^{core,yoy}_t - 2) + 0.5 x_t
             i_t  = 0.93 i_{t-1} + 0.07 i*_t, moved only in meeting months, 25bp steps
  yields     y^n_t = avg_{h<=n} E_t[i_{t+h}] + tp^n_t,  E_t[i_{t+h}] = LR + 0.97^h (i_t - LR)
  stress     two-state Markov chain (calm/stress), forced into stress in scripted crises
  equities   r_t = mu(stress) - beta_r * d(real 10y) + 0.004 d(x) + sigma(stress) e_t
"""

from __future__ import annotations

import os
from functools import lru_cache

import numpy as np
import pandas as pd

from macro.config import catalogue
from macro.utils import SEED

DEMO_START = "1990-01-01"
DEMO_END = os.environ.get("MACRO_DEMO_END", "2026-09-30")  # fixed => deterministic outputs

MEETINGS = {
    "US": [1, 3, 5, 6, 7, 9, 11, 12],
    "EA": [1, 3, 4, 6, 7, 9, 10, 12],
    "JP": [1, 3, 4, 6, 7, 9, 10, 12],
}


def _months() -> pd.DatetimeIndex:
    return pd.date_range(DEMO_START, DEMO_END, freq="MS")


def _episode(idx: pd.DatetimeIndex, start: str, values: list[float]) -> np.ndarray:
    out = np.zeros(len(idx))
    k0 = idx.get_indexer([pd.Timestamp(start)])[0]
    if k0 >= 0:
        n = min(len(values), len(idx) - k0)
        out[k0 : k0 + n] = values[:n]
    return out


def _ar1(n: int, phi: float, sd: float, gen: np.random.Generator, mean: float = 0.0) -> np.ndarray:
    x = np.zeros(n)
    x[0] = mean
    e = gen.normal(0, sd, n)
    for t in range(1, n):
        x[t] = mean + phi * (x[t - 1] - mean) + e[t]
    return x


def _yoy(level: np.ndarray, k: int = 12) -> np.ndarray:
    out = np.full(len(level), np.nan)
    out[k:] = 100 * (level[k:] / level[:-k] - 1)
    return out


def _index_from_rates(rates_ann: np.ndarray, base: float = 100.0) -> np.ndarray:
    return base * np.cumprod(1 + rates_ann / 1200.0)


def _expected_avg(i: np.ndarray, lr: np.ndarray, n_months: int, phi: float = 0.97) -> np.ndarray:
    """Average expected short rate over the next n months under an AR(1) toward `lr`."""
    h = np.arange(1, n_months + 1)
    w = (phi**h).mean()
    return lr + w * (i - lr)


def _region_block(
    months: pd.DatetimeIndex,
    gen: np.random.Generator,
    common_gap: np.ndarray,
    oil: np.ndarray,
    gscpi: np.ndarray,
    stress: np.ndarray,
    p: dict,
) -> dict[str, np.ndarray]:
    n = len(months)
    t = np.arange(n)
    rstar = (
        p["rstar0"] + (p["rstar1"] - p["rstar0"]) * np.clip(t / (n * 0.65), 0, 1) + _ar1(n, 0.98, 0.03, gen)
    )
    ustar = p["ustar0"] + (p["ustar1"] - p["ustar0"]) * t / n
    crises = p["crises"]
    gap = np.zeros(n)
    tau = np.full(n, p["pi0"])
    pie = np.full(n, p["pie0"])
    i = np.full(n, p["i0"])
    head_lvl = np.full(n, 100.0)
    core_lvl = np.full(n, 100.0)
    serv = np.zeros(n)
    goods = np.zeros(n)
    core = np.zeros(n)
    energy = np.zeros(n)
    food = np.zeros(n)
    head = np.zeros(n)
    doil = np.r_[0.0, np.diff(oil)] * 100  # % change of local-currency oil
    e_gap = gen.normal(0, 0.15, n)
    e_tau = gen.normal(0, 0.12, n)
    e_pie = gen.normal(0, 0.015, n)
    shadow = p["i0"]
    step_max = 0.75
    for k in range(2, n):
        core_yoy_prev = 100 * (core_lvl[k - 1] / core_lvl[k - 13] - 1) if k > 13 else p["pi0"]
        head_yoy_prev = 100 * (head_lvl[k - 1] / head_lvl[k - 13] - 1) if k > 13 else p["pi0"]
        # real policy rate averaged over lags 3-12: monetary policy works with long lags
        rr = i[max(k - 12, 0) : max(k - 2, 1)].mean() - core_yoy_prev
        gap[k] = (
            1.25 * gap[k - 1]
            - 0.35 * gap[k - 2]
            - 0.14 * (rr - rstar[k])
            + p["beta_common"] * common_gap[k]
            - 0.4 * stress[k]
            + e_gap[k]
            + crises[k]
        )
        pie[k] = 0.97 * pie[k - 1] + 0.03 * 2.0 + 0.01 * (head_yoy_prev - 2.0) + e_pie[k]
        tau[k] = 0.9 * tau[k - 1] + 0.1 * pie[k] + 0.05 * gap[k - 1] + 0.10 * gscpi[k] + e_tau[k]
        serv[k] = tau[k] + 0.8 + gen.normal(0, 1.0)
        goods[k] = tau[k] - 1.9 + 1.2 * gscpi[k] + gen.normal(0, 2.2)
        core[k] = 0.7 * serv[k] + 0.3 * goods[k]
        energy[k] = 12 * 0.35 * doil[k] + gen.normal(0, 6.0)
        food[k] = 0.6 * tau[k] + 0.4 * 2.5 + 0.8 * gscpi[k] + 0.05 * energy[k] + gen.normal(0, 1.5)
        head[k] = 0.78 * core[k] + 0.08 * energy[k] + 0.14 * food[k]
        core_lvl[k] = core_lvl[k - 1] * (1 + core[k] / 1200)
        head_lvl[k] = head_lvl[k - 1] * (1 + head[k] / 1200)
        # inertial Taylor rule, moved only at meetings in 25bp steps
        target = rstar[k] + core_yoy_prev + 0.5 * (core_yoy_prev - 2.0) + 0.5 * gap[k]
        shadow = 0.93 * shadow + 0.07 * target
        if months[k].month in MEETINGS[p["region"]]:
            step = np.clip(round((max(p["floor"], shadow) - i[k - 1]) * 4) / 4, -step_max, step_max)
            i[k] = max(p["floor"], i[k - 1] + step)
        else:
            i[k] = i[k - 1]
    pol = i
    unemp = ustar - 0.45 * gap + _ar1(n, 0.6, 0.08, gen)
    lr = rstar + 2.0
    tp10 = _ar1(n, 0.97, 0.08, gen, mean=0.0) + np.linspace(p["tp0"], p["tp1"], n) + 0.3 * stress
    yields = {}
    for name, m in (("3M", 3), ("2Y", 24), ("5Y", 60), ("10Y", 120), ("30Y", 360)):
        tp = tp10 * (m / 120) ** 0.7
        yields[name] = _expected_avg(pol, lr, m) + tp + gen.normal(0, 0.04, n)
    be10 = pie + 0.15 + 0.08 * (_yoy(head_lvl) - 2.0).clip(-3, 5) + gen.normal(0, 0.05, n)
    be10[:12] = pie[:12] + 0.15
    return {
        "rstar": rstar,
        "ustar": ustar,
        "gap": gap,
        "tau": tau,
        "pie": pie,
        "pol": pol,
        "unemp": unemp,
        "serv": serv,
        "goods": goods,
        "core": core,
        "energy": energy,
        "food": food,
        "head": head,
        "core_lvl": core_lvl,
        "head_lvl": head_lvl,
        "tp10": tp10,
        "be10": be10,
        **{f"y{k}": v for k, v in yields.items()},
    }


def _bdays() -> pd.DatetimeIndex:
    return pd.bdate_range(DEMO_START, DEMO_END)


def _daily_level(
    monthly: pd.Series, gen: np.random.Generator, noise_sd: float, phi: float = 0.9
) -> pd.Series:
    """Monthly path interpolated to business days (anchored mid-month) plus OU noise."""
    days = _bdays()
    anchor = monthly.copy()
    anchor.index = anchor.index + pd.Timedelta(days=14)
    s = anchor.reindex(anchor.index.union(days)).interpolate("time").ffill().bfill().reindex(days)
    return s + _ar1(len(days), phi, noise_sd * np.sqrt(1 - phi**2), gen)


def _daily_price(
    monthly_logret: pd.Series, gen: np.random.Generator, start: float, daily_sd: float
) -> pd.Series:
    """Brownian bridge: daily log returns that add up to each month's simulated log return."""
    days = _bdays()
    month_of = days.to_period("M")
    out = np.zeros(len(days))
    for per, r in monthly_logret.items():
        mask = month_of == pd.Timestamp(per).to_period("M")
        k = int(mask.sum())
        if k == 0:
            continue
        z = gen.normal(0, daily_sd, k)
        z = z - z.mean() + r / k
        out[mask] = z
    return pd.Series(start * np.exp(np.cumsum(out)), index=days)


def _policy_daily(monthly_rate: pd.Series, region: str) -> pd.Series:
    """Step function: the rate changes on the 15th (or next business day) of the meeting month."""
    days = _bdays()
    s = pd.Series(np.nan, index=days)
    prev = None
    for m, v in monthly_rate.items():
        if prev is None or v != prev:
            d = (
                days[days.searchsorted(m + pd.Timedelta(days=14))]
                if (m + pd.Timedelta(days=14)) <= days[-1]
                else None
            )
            if d is not None:
                s.loc[d] = v
            prev = v
    s.iloc[0] = monthly_rate.iloc[0]
    return s.ffill()


def _weekly(daily: pd.Series, rule: str) -> pd.Series:
    return daily.resample(rule).mean().dropna()


def _quarterly(monthly: pd.Series, how: str = "mean") -> pd.Series:
    q = monthly.resample("QS")
    return (q.mean() if how == "mean" else q.last()).dropna()


@lru_cache(maxsize=2)
def generate(seed: int = SEED) -> dict[str, pd.Series]:
    """Return {series_id: pd.Series} for every id in the catalogue (deterministic for a seed)."""
    gen = np.random.default_rng(seed)
    months = _months()
    n = len(months)

    # ---------------------------------------------------------------- global block
    oil_shock = (
        _episode(months, "1990-08-01", [0.25, 0.15, 0.05, -0.1, -0.15, -0.1])
        + _episode(months, "2007-06-01", [0.05] * 12 + [-0.2, -0.25, -0.2, -0.1])
        + _episode(months, "2014-07-01", [-0.08] * 7)
        + _episode(months, "2020-03-01", [-0.35, -0.2, 0.25, 0.15])
        + _episode(months, "2021-01-01", [0.04] * 14 + [0.12, 0.08, -0.05, -0.08, -0.06])
        + _episode(months, "2026-02-01", [0.07] * 6)  # scripted 2026 energy supply shock (demo storyline)
    )
    oil = np.log(20.0) + np.cumsum(0.003 + gen.normal(0, 0.07, n) + oil_shock)
    gscpi_ep = _episode(
        months,
        "2020-04-01",
        [
            1.0,
            0.6,
            0.2,
            0.2,
            0.3,
            0.3,
            0.4,
            0.4,
            0.4,
            0.4,
            0.3,
            0.2,
            0.2,
            0.1,
            0.0,
            -0.2,
            -0.3,
            -0.4,
            -0.4,
            -0.4,
        ],
    )
    gscpi = np.zeros(n)
    e_g = gen.normal(0, 0.35, n)
    for k in range(1, n):
        gscpi[k] = 0.85 * gscpi[k - 1] + e_g[k] * 0.6 + gscpi_ep[k]
    common = _ar1(n, 0.9, 0.15, gen)

    # stress regime: Markov chain + forced crises
    stress = np.zeros(n)
    for k in range(1, n):
        p_stay = 0.85 if stress[k - 1] else 0.985
        stress[k] = stress[k - 1] if gen.random() < p_stay else 1 - stress[k - 1]
    for start, length in (("2008-09-01", 8), ("2020-03-01", 3), ("2011-08-01", 4), ("2001-09-01", 3)):
        stress += _episode(months, start, [1.0] * length)
    stress = np.clip(stress, 0, 1)
    # scripted demand upswing 2024-2026 so the demo ends inside a tightening cycle
    upswing = _episode(months, "2024-09-01", [0.5] * 24)

    us_crises = (
        _episode(months, "2001-03-01", [-0.4] * 6)
        + _episode(months, "2008-06-01", [-0.6] * 10)
        + _episode(months, "2020-03-01", [-5.0, -2.0, 3.0, 2.0, 1.0])
        + upswing
    )
    ea_crises = (
        _episode(months, "2008-09-01", [-0.6] * 8)
        + _episode(months, "2011-10-01", [-0.3] * 12)
        + _episode(months, "2020-03-01", [-6.0, -2.0, 3.5, 2.5, 1.0])
        + 0.6 * upswing
    )
    jp_crises = (
        _episode(months, "2008-10-01", [-0.8] * 6)
        + _episode(months, "2011-03-01", [-1.5, 0.8])
        + _episode(months, "2020-04-01", [-3.0, 1.0, 1.0, 0.5])
        + 0.5 * upswing
    )

    us = _region_block(
        months,
        gen,
        common,
        oil,
        gscpi,
        stress,
        {
            "region": "US",
            "rstar0": 2.5,
            "rstar1": 0.7,
            "ustar0": 5.6,
            "ustar1": 4.3,
            "pi0": 3.5,
            "pie0": 3.0,
            "i0": 7.5,
            "floor": 0.125,
            "tp0": 1.6,
            "tp1": 0.2,
            "beta_common": 0.3,
            "crises": us_crises,
        },
    )
    usd_eur = _ar1(n, 0.985, 0.02, gen, mean=np.log(1.15))
    us_eur_oil = oil - usd_eur  # oil in EUR: weaker euro means dearer oil
    ea = _region_block(
        months,
        gen,
        common,
        us_eur_oil,
        gscpi,
        stress,
        {
            "region": "EA",
            "rstar0": 2.0,
            "rstar1": -0.2,
            "ustar0": 9.5,
            "ustar1": 7.0,
            "pi0": 2.5,
            "pie0": 2.2,
            "i0": 4.0,
            "floor": -0.5,
            "tp0": 1.4,
            "tp1": 0.1,
            "beta_common": 0.2,
            "crises": ea_crises,
        },
    )
    jp = _region_block(
        months,
        gen,
        common,
        oil + np.cumsum(gen.normal(0, 0.025, n)),
        0.6 * gscpi,
        stress,
        {
            "region": "JP",
            "rstar0": 1.0,
            "rstar1": -0.5,
            "ustar0": 2.5,
            "ustar1": 2.6,
            "pi0": 1.5,
            "pie0": 1.2,
            "i0": 4.0,
            "floor": -0.1,
            "tp0": 1.0,
            "tp1": 0.3,
            "beta_common": 0.15,
            "crises": jp_crises,
        },
    )

    M = lambda a: pd.Series(np.asarray(a, dtype=float), index=months)  # noqa: E731
    out: dict[str, pd.Series] = {}

    # ---------------------------------------------------------------- US policy & rates (daily)
    us_pol_m = M(us["pol"])
    target_upper = _policy_daily(us_pol_m + 0.125, "US")
    out["DFEDTARU"] = target_upper
    out["DFF"] = target_upper - 0.17 + _ar1(len(target_upper), 0.5, 0.01, gen)
    # policy surprise on decision days: 2Y jumps by part of the move, decays over ~2 months
    days = _bdays()
    dtarget = target_upper.diff().fillna(0.0)
    surprise = np.where(
        dtarget.to_numpy() != 0, 0.35 * dtarget.to_numpy() + gen.normal(0, 0.05, len(days)), 0.0
    )
    decay = 0.5 ** (1 / 40)  # half-life of ~2 months of business days
    sp = np.zeros(len(days))
    for k in range(1, len(days)):
        sp[k] = decay * sp[k - 1] + surprise[k]
    surprise_path = pd.Series(sp, index=days)
    out["DGS3MO"] = _daily_level(M(us["y3M"]), gen, 0.03).clip(lower=0.0)
    out["DGS2"] = (_daily_level(M(us["y2Y"]), gen, 0.05) + 0.6 * surprise_path).clip(lower=0.05)
    out["DGS5"] = (_daily_level(M(us["y5Y"]), gen, 0.06) + 0.4 * surprise_path).clip(lower=0.1)
    out["DGS10"] = (_daily_level(M(us["y10Y"]), gen, 0.06) + 0.25 * surprise_path).clip(lower=0.3)
    out["DGS30"] = (_daily_level(M(us["y30Y"]), gen, 0.06) + 0.15 * surprise_path).clip(lower=0.8)
    out["T10Y2Y"] = out["DGS10"] - out["DGS2"]
    out["T10Y3M"] = out["DGS10"] - out["DGS3MO"]
    be10_d = _daily_level(M(us["be10"]), gen, 0.03)
    out["T10YIE"] = be10_d
    out["T5YIFR"] = _daily_level(M(us["pie"] + 0.25), gen, 0.04)
    out["DFII10"] = out["DGS10"] - be10_d
    tp_d = _daily_level(M(us["tp10"]), gen, 0.03)
    out["THREEFYTP10"] = tp_d + 0.1
    out["ACMTP10"] = tp_d + _ar1(len(tp_d), 0.98, 0.04, gen) - 0.1

    gap_m = M(us["gap"])
    stress_m = M(stress)
    bbb_spread = 1.6 - 0.25 * gap_m + 1.2 * stress_m
    out["BAMLC0A4CBBBEY"] = _daily_level(M(us["y10Y"]) + bbb_spread, gen, 0.05)
    out["BAMLH0A0HYM2"] = _daily_level((4.5 - 0.9 * gap_m + 4.0 * stress_m).clip(lower=2.5), gen, 0.12)
    out["BAMLC0A0CM"] = _daily_level((1.2 - 0.2 * gap_m + 1.0 * stress_m).clip(lower=0.6), gen, 0.03)
    vix_m = (14 - 1.0 * gap_m + 14 * stress_m).clip(lower=9)
    out["VIXCLS"] = _daily_level(vix_m, gen, 1.5, phi=0.8).clip(lower=9)
    rr10_m = M(us["y10Y"] - us["be10"])
    nfci_m = (
        -0.55
        + 1.0 * stress_m
        - 0.05 * gap_m
        + 0.08 * (M(us["pol"]) - M(us["core"]).rolling(12, min_periods=1).mean() - M(us["rstar"]))
    )
    out["NFCI"] = _weekly(_daily_level(nfci_m, gen, 0.03), "W-FRI")
    out["STLFSI4"] = _weekly(_daily_level(-0.4 + 2.5 * stress_m - 0.1 * gap_m, gen, 0.1), "W-FRI")
    mort_m = M(us["y10Y"]) + 1.7 + 0.4 * stress_m
    out["MORTGAGE30US"] = _weekly(_daily_level(mort_m, gen, 0.03), "W-THU")

    # equities / FX / commodities (monthly log returns, then Brownian bridge)
    d_rr = rr10_m.diff().fillna(0)
    d_gap = gap_m.diff().fillna(0)
    mu = np.where(stress == 1, -0.025, 0.009)
    sig = np.where(stress == 1, 0.07, 0.035)
    eq_shock = gen.normal(0, 1, n)
    spx_ret = M(mu - 0.035 * d_rr + 0.004 * d_gap + sig * eq_shock)
    out["SPX"] = _daily_price(spx_ret, gen, 330.0, 0.006)
    sox_ret = M(
        1.5 * (mu - 0.035 * d_rr)
        - 0.04 * d_rr
        + 0.006 * d_gap
        + 1.4 * sig * eq_shock
        + gen.normal(0, 0.04, n)
        + 0.002
    )
    out["SOX"] = _daily_price(sox_ret, gen, 160.0, 0.012)
    out["VIX"] = out["VIXCLS"] * (1 + _ar1(len(days), 0.5, 0.01, gen))
    move_m = (70 + 25 * stress_m + 12 * M(np.abs(np.r_[0, np.diff(us["y2Y"])])) * 10).clip(lower=45)
    out["MOVE"] = _daily_level(move_m, gen, 4.0, phi=0.8)
    hp_ret = 0.003 + 0.0015 * gap_m - 0.004 * mort_m.diff().fillna(0) + gen.normal(0, 0.003, n)
    out["CSUSHPISA"] = M(70 * np.exp(np.cumsum(hp_ret)))

    ea_pol_m = M(ea["pol"])
    jp_pol_m = M(jp["pol"])
    diff_us_ea = M(us["y2Y"] - ea["y2Y"])
    eurusd_m = np.exp(usd_eur) * np.exp(-0.03 * (diff_us_ea - diff_us_ea.iloc[0]).to_numpy())
    out["EURUSD"] = _daily_price(M(np.r_[0, np.diff(np.log(eurusd_m))]), gen, float(eurusd_m[0]), 0.005)
    diff_us_jp = M(us["y10Y"] - jp["y10Y"])
    usdjpy_m = 140 * np.exp(0.06 * (diff_us_jp - diff_us_jp.mean()).to_numpy() + _ar1(n, 0.985, 0.015, gen))
    out["USDJPY"] = _daily_price(M(np.r_[0, np.diff(np.log(usdjpy_m))]), gen, float(usdjpy_m[0]), 0.005)
    broad = 100 * np.exp(
        0.5 * np.log(usdjpy_m / usdjpy_m[0]) * 0.3 - 0.6 * np.log(eurusd_m / eurusd_m[0]) + 0.02 * stress
    )
    out["DTWEXBGS"] = _daily_level(M(broad), gen, 0.15)
    out["DXY"] = out["DTWEXBGS"] * 0.95 + _ar1(len(days), 0.9, 0.1, gen)
    out["DCOILBRENTEU"] = _daily_price(M(np.r_[0, np.diff(oil)]), gen, float(np.exp(oil[0])), 0.018)
    out["BRENT_FUT"] = out["DCOILBRENTEU"] * (1 + _ar1(len(days), 0.8, 0.003, gen))
    gold_ret = M(0.004 - 0.02 * d_rr + 0.01 * stress + gen.normal(0, 0.035, n))
    out["GOLD_FUT"] = _daily_price(gold_ret, gen, 380.0, 0.008)

    # ---------------------------------------------------------------- US prices (monthly)
    out["CPIAUCSL"] = M(130 * us["head_lvl"] / 100)
    out["CPILFESL"] = M(135 * us["core_lvl"] / 100)
    out["CPIENGSL"] = M(_index_from_rates(us["energy"], 95))
    out["CPIUFDSL"] = M(_index_from_rates(us["food"], 135))
    out["CUSR0000SAS"] = M(_index_from_rates(us["serv"], 140))
    out["CUSR0000SACL1E"] = M(_index_from_rates(us["goods"], 125))
    out["PCEPI"] = M(_index_from_rates(us["head"] - 0.4 + gen.normal(0, 0.3, n), 60))
    out["PCEPILFE"] = M(_index_from_rates(us["core"] * 0.85 - 0.1 + gen.normal(0, 0.25, n), 60))
    out["MEDCPIM158SFRBCLE"] = M(us["tau"] + 0.2 + gen.normal(0, 0.6, n))
    out["TRMMEANCPIM158SFRBCLE"] = M(us["tau"] + 0.1 + gen.normal(0, 0.7, n))
    sticky = _index_from_rates(0.85 * us["tau"] + 0.15 * us["serv"] + 0.3, 100)
    out["CORESTICKM159SFRBATL"] = M(_yoy(sticky)).dropna()
    ppi_rates = (
        0.25 * us["energy"] + 0.5 * us["goods"] + 0.25 * us["tau"] + 2.0 * gscpi + gen.normal(0, 2.0, n)
    )
    out["PPIFIS"] = M(_index_from_rates(ppi_rates, 100)).loc["2009-11-01":]
    head_yoy = _yoy(us["head_lvl"])
    head_yoy[:12] = 3.5
    out["MICH"] = M(0.6 + 0.55 * np.nan_to_num(head_yoy, nan=3.0) + 0.35 * us["pie"] + gen.normal(0, 0.2, n))
    out["EXPINF10YR"] = M(us["pie"] + 0.1 + gen.normal(0, 0.03, n))

    # ---------------------------------------------------------------- US activity & labor
    u = M(us["unemp"])
    out["UNRATE"] = u.round(1)
    out["NROU"] = _quarterly(M(us["ustar"]))
    d_u = u.diff().fillna(0)
    out["PAYEMS"] = M(109000 + np.cumsum(110 - 900 * d_u.to_numpy() + gen.normal(0, 70, n)))
    claims_m = (330 + 70 * (u - M(us["ustar"])) + 25 * stress_m) * 1000
    out["ICSA"] = _weekly(_daily_level(claims_m, gen, 12000, phi=0.6), "W-SAT").round(-3)
    pot_growth = np.linspace(2.8, 1.8, n) / 1200  # monthly log growth of potential
    pot = 9000 * np.exp(np.cumsum(pot_growth))
    gdp_m = pot * np.exp(us["gap"] / 100)
    out["GDPPOT"] = _quarterly(M(pot))
    out["GDPC1"] = _quarterly(M(gdp_m))
    out["INDPRO"] = M(
        70
        * np.exp(np.cumsum(0.0015 + np.zeros(n)))
        * np.exp(1.8 * us["gap"] / 100 + _ar1(n, 0.7, 0.004, gen))
    )
    out["RSAFS"] = M(
        180000
        * np.exp(np.cumsum(0.0035 + us["head"] / 1200 * 0))
        * np.exp(1.2 * us["gap"] / 100 + _ar1(n, 0.3, 0.006, gen))
    )
    out["PCEC96"] = M(
        6000 * np.exp(np.cumsum(pot_growth)) * np.exp(0.9 * us["gap"] / 100 + _ar1(n, 0.5, 0.002, gen))
    )
    out["HOUST"] = M(
        (
            1400
            * np.exp(0.06 * us["gap"] - 0.08 * (mort_m.to_numpy() - mort_m.mean()) + _ar1(n, 0.6, 0.05, gen))
        ).clip(400)
    )
    out["BOPTEXP"] = M(
        50000
        * np.exp(np.cumsum(0.004 + np.zeros(n)))
        * np.exp(1.5 * common / 100 * 10 + _ar1(n, 0.6, 0.01, gen))
    )
    out["UMCSENT"] = M(
        88 + 4 * us["gap"] - 2.5 * (np.nan_to_num(head_yoy, nan=3) - 2) - 8 * stress + gen.normal(0, 3, n)
    )
    out["GACDFSA066MSFRBPHI"] = M(5 + 9 * us["gap"] + 25 * np.r_[0, np.diff(us["gap"])] + gen.normal(0, 8, n))
    out["GACDINA066MSFRBNY"] = M(
        3 + 8 * us["gap"] + 20 * np.r_[0, np.diff(us["gap"])] + gen.normal(0, 9, n)
    ).loc["2001-07-01":]
    out["USREC"] = M(_recession_indicator(us["gap"]))

    # ---------------------------------------------------------------- euro area (from 1999)
    ea_start = "1999-01-01"
    out["EA_DFR"] = _policy_daily(ea_pol_m, "EA").loc[ea_start:]
    for sid, comp, base in (
        ("EA_HICP", "head", 80),
        ("EA_HICP_CORE", "core", 82),
        ("EA_HICP_ENERGY", "energy", 60),
        ("EA_HICP_FOOD", "food", 75),
        ("EA_HICP_SERV", "serv", 78),
        ("EA_HICP_NEIG", "goods", 90),
    ):
        out[sid] = M(_index_from_rates(ea[comp], base)).loc[ea_start:]
    out["EA_YC_2Y"] = _daily_level(M(ea["y2Y"]), gen, 0.05).loc["2004-09-06":]
    out["EA_YC_10Y"] = _daily_level(M(ea["y10Y"]), gen, 0.05).loc["2004-09-06":]
    ea_stress = stress_m + M(_episode(months, "2011-06-01", [0.5, 0.8, 1, 1, 1, 1, 1, 0.8, 0.6, 0.4, 0.3]))
    de = M(ea["y10Y"]) - 0.05
    out["DE_10Y"] = (de + gen.normal(0, 0.03, n)).loc[ea_start:]
    out["FR_10Y"] = (de + 0.3 + 0.25 * ea_stress + _ar1(n, 0.95, 0.04, gen)).loc[ea_start:]
    out["IT_10Y"] = (de + 1.2 + 2.5 * ea_stress + _ar1(n, 0.95, 0.12, gen)).loc[ea_start:]
    out["ES_10Y"] = (de + 0.9 + 2.0 * ea_stress + _ar1(n, 0.95, 0.10, gen)).loc[ea_start:]
    out["EA_UNRATE"] = M(ea["unemp"]).round(1).loc[ea_start:]
    out["EUROREC"] = M(_recession_indicator(ea["gap"])).loc[ea_start:]
    ea_ret = M(
        mu
        - 0.03 * M(ea["y10Y"] - ea["be10"]).diff().fillna(0).to_numpy()
        + 0.004 * np.r_[0, np.diff(ea["gap"])]
        + 1.1 * sig * (0.7 * eq_shock + 0.7 * gen.normal(0, 1, n))
    )
    out["SX5E"] = _daily_price(ea_ret, gen, 1500.0, 0.007).loc[ea_start:]

    # ---------------------------------------------------------------- Japan
    out["JP_POLICY"] = jp_pol_m
    out["JP_CPI"] = M(_index_from_rates(jp["head"], 95))
    out["JP_10Y"] = M(jp["y10Y"]).clip(lower=-0.2)
    jp_ret = M(
        mu
        - 0.02 * np.r_[0, np.diff(jp["y10Y"])]
        + 0.003 * np.r_[0, np.diff(jp["gap"])]
        + 1.2 * sig * (0.6 * eq_shock + 0.8 * gen.normal(0, 1, n))
        - 0.002
    )
    out["N225"] = _daily_price(jp_ret, gen, 30000.0, 0.008)

    # ---------------------------------------------------------------- published research series
    q = lambda a: _quarterly(M(a))  # noqa: E731
    out["HLW_RSTAR_US"] = q(us["rstar"] + gen.normal(0, 0.1, n))
    out["HLW_RSTAR_EA"] = q(ea["rstar"] + gen.normal(0, 0.1, n)).loc["1999-01-01":]
    out["LW_RSTAR_US"] = q(us["rstar"] + 0.3 + gen.normal(0, 0.15, n))
    out["GSCPI"] = M(gscpi).loc["1998-01-01":]
    out["CIE"] = q(us["pie"] - 0.1 + gen.normal(0, 0.03, n))
    fcig = (
        0.6 * (M(us["pol"]) - M(us["rstar"]) - M(us["pie"])).diff(12) * 0.2
        + 0.5 * stress_m
        - 0.2 * spx_ret.rolling(12).sum()
    )
    out["FCIG_1Y"] = fcig.dropna()
    spf_cpi = 0.5 * np.nan_to_num(head_yoy, nan=3) + 0.5 * us["pie"] + gen.normal(0, 0.15, n)
    out["SPF_CPI_1Y"] = q(spf_cpi)
    out["SPF_CPI10"] = q(us["pie"] + 0.05 + gen.normal(0, 0.05, n))
    out["SPF_RGDP_1Y"] = q(2.3 + 0.25 * us["gap"] - 0.3 * stress + gen.normal(0, 0.2, n))

    # ---------------------------------------------------------------- positioning (CFTC TFF, Tuesday)
    tues = pd.date_range("2006-06-13", DEMO_END, freq="W-TUE")
    nt = len(tues)
    trend = np.linspace(0, 1, nt)
    us2_w = out["DGS2"].reindex(tues, method="ffill").to_numpy()
    mom = np.r_[np.zeros(13), us2_w[13:] - us2_w[:-13]]
    W = lambda a: pd.Series(np.asarray(a, dtype=float), index=tues)  # noqa: E731
    out["TFF_UST10_LEV"] = W(-150000 - 650000 * trend**2 + _ar1(nt, 0.95, 40000, gen))
    out["TFF_UST10_AM"] = W(250000 + 900000 * trend**2 + _ar1(nt, 0.95, 50000, gen))
    out["TFF_SOFR3M_LEV"] = W(-300000 * np.tanh(3 * mom) + _ar1(nt, 0.9, 60000, gen)).loc["2018-05-08":]
    spx_w = np.log(out["SPX"].reindex(tues, method="ffill").to_numpy())
    eq_mom = np.r_[np.zeros(13), spx_w[13:] - spx_w[:-13]]
    out["TFF_ES_LEV"] = W(-50000 + 400000 * eq_mom + _ar1(nt, 0.93, 40000, gen))
    out["TFF_ES_AM"] = W(600000 + 300000 * trend + 200000 * eq_mom + _ar1(nt, 0.95, 50000, gen))
    eur_w = np.log(out["EURUSD"].reindex(tues, method="ffill").to_numpy())
    out["TFF_EUR_LEV"] = W(
        800000 * np.r_[np.zeros(13), eur_w[13:] - eur_w[:-13]] + _ar1(nt, 0.92, 15000, gen)
    )
    jpy_carry = diff_us_jp.reindex(tues, method="ffill").to_numpy()
    out["TFF_JPY_LEV"] = W(-25000 * (jpy_carry - np.nanmean(jpy_carry)) - 20000 + _ar1(nt, 0.93, 15000, gen))

    for k, s in out.items():
        s.name = k
        s.index.name = "date"
    missing = set(catalogue().ids) - set(out)
    if missing:
        raise RuntimeError(f"demo generator misses catalogue ids: {sorted(missing)}")
    return {k: out[k].astype(float) for k in catalogue().ids}


def _recession_indicator(gap: np.ndarray) -> np.ndarray:
    """1 while the output gap is falling fast and negative; spells shorter than 4 months dropped."""
    g = pd.Series(gap)
    raw = ((g.diff(6) < -0.8) & (g < -0.3)).astype(int).to_numpy()
    out = raw.copy()
    k = 0
    while k < len(raw):
        if raw[k]:
            j = k
            while j < len(raw) and raw[j]:
                j += 1
            if j - k < 4:
                out[k:j] = 0
            k = j
        else:
            k += 1
    return out.astype(float)
