"""Historical tightening cycles across countries and two centuries (Global Macro Database, annual).

Question: how often do tightening cycles end in recession, and does the answer depend on the size of
the cycle, the inflation it fights, and the era?

Definitions (annual data, so deliberately coarse; stated on the page):
- Policy rate: `cbrate`, else `strate` (short-term rate) when the central-bank rate is missing.
- Tightening cycle: from a trough year to the following peak year of the policy rate, with a
  cumulative rise of at least `min_rise` pp. The peak is the highest rate before the rate falls by
  at least `min_fall` pp (or the sample ends; such cycles are 'ongoing').
- Recession after the cycle: real GDP falls in at least one year within `horizon` years after the
  peak year (peak year included).
- Crisis after the cycle: a banking crisis starts within the cycle or `horizon` years after its peak.
Only realised years (<= last_actual_year) are used: the latest GMD release includes projections.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ERAS = [
    (0, 1913, "pre-1914 (gold standard)"),
    (1914, 1945, "1914-1945 (wars, interwar)"),
    (1946, 1972, "1946-1972 (Bretton Woods)"),
    (1973, 1989, "1973-1989 (high inflation)"),
    (1990, 2007, "1990-2007 (inflation targeting)"),
    (2008, 9999, "2008- (post-GFC)"),
]


def policy_rate(panel: pd.DataFrame) -> pd.Series:
    r = panel["cbrate"].where(panel["cbrate"].notna(), panel.get("strate"))
    return r


def era(year: int) -> str:
    return next(lab for lo, hi, lab in ERAS if lo <= year <= hi)


def _cycles_one(rate: pd.Series, min_rise: float, min_fall: float) -> list[tuple[int, int, bool]]:
    """(trough_year, peak_year, completed) for one country's annual rate series (index = year)."""
    r = rate.dropna()
    if len(r) < 5:
        return []
    years, vals = r.index.to_numpy(), r.to_numpy()
    out = []
    i_trough = 0
    i = 1
    while i < len(vals):
        if vals[i] <= vals[i_trough]:  # latest year at the low: the year before the first rise
            i_trough = i
            i += 1
            continue
        if vals[i] - vals[i_trough] >= min_rise:
            # climb to the peak: highest value before a fall of min_fall from it
            i_peak = i
            j = i + 1
            while j < len(vals) and vals[i_peak] - vals[j] < min_fall:
                if vals[j] > vals[i_peak]:
                    i_peak = j
                j += 1
            completed = j < len(vals)
            out.append((int(years[i_trough]), int(years[i_peak]), completed))
            i_trough = j if completed else len(vals)
            i = i_trough + 1
            continue
        i += 1
    return out


def find_cycles(
    panel: pd.DataFrame,
    last_year: int,
    min_rise: float = 1.0,
    min_fall: float = 0.5,
    horizon: int = 2,
    ignore_years: tuple[int, ...] = (),
) -> pd.DataFrame:
    """One row per tightening cycle with its size, inflation context and outcomes. `ignore_years`
    are not counted as recession years (robustness: 2020, a pandemic rather than a policy recession)."""
    p = panel[panel["year"] <= last_year].copy()
    p["rate"] = policy_rate(p)
    rows = []
    for iso, g in p.groupby("ISO3"):
        g = g.set_index("year").sort_index()
        growth = 100 * np.log(g["rGDP"]).diff() if "rGDP" in g else pd.Series(dtype=float)
        for t, pk, done in _cycles_one(g["rate"], min_rise, min_fall):
            post = growth.loc[pk : pk + horizon].drop(list(ignore_years), errors="ignore")
            obs_complete = pk + horizon <= last_year
            rec = bool((post < 0).any()) if post.notna().any() else None
            if rec is False and not obs_complete:
                rec = None  # outcome window not over yet
            bc = g["BankingCrisis"] if "BankingCrisis" in g else pd.Series(dtype=float)
            win = bc.loc[t : pk + horizon]
            crisis = bool((win == 1).any()) if win.notna().any() else None
            rows.append(
                {
                    "ISO3": iso,
                    "country": g["countryname"].iloc[0],
                    "trough": t,
                    "peak": pk,
                    "years": pk - t,
                    "rise_pp": float(g.loc[pk, "rate"] - g.loc[t, "rate"]),
                    "peak_rate": float(g.loc[pk, "rate"]),
                    "infl_at_trough": float(g["infl"].get(t, np.nan)),
                    "infl_at_peak": float(g["infl"].get(pk, np.nan)),
                    "real_rate_at_peak": float(g.loc[pk, "rate"] - g["infl"].get(pk, np.nan)),
                    "min_growth_after": float(post.min()) if post.notna().any() else np.nan,
                    "recession_after": rec,
                    "crisis_after": crisis,
                    "completed": done,
                    "era": era(t),
                }
            )
    return pd.DataFrame(rows)


def _share(x: pd.Series) -> float:
    x = x.dropna().astype(bool)
    return float(x.mean()) if len(x) else np.nan


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a proportion (small-N friendly)."""
    if n == 0:
        return (np.nan, np.nan)
    p = k / n
    d = 1 + z**2 / n
    c = (p + z**2 / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / d
    return (c - h, c + h)


def summarise(cycles: pd.DataFrame, by: str) -> pd.DataFrame:
    """Share of cycles followed by recession (with Wilson 95% interval and N) by a grouping column."""
    rows = []
    for k, g in cycles.groupby(by, observed=True):
        r = g["recession_after"].dropna().astype(bool)
        lo, hi = wilson(int(r.sum()), len(r))
        rows.append(
            {
                by: k,
                "cycles (N)": len(r),
                "share ending in recession": _share(g["recession_after"]),
                "95% low": lo,
                "95% high": hi,
                "share with banking crisis": _share(g["crisis_after"]),
                "median rise (pp)": float(g["rise_pp"].median()),
            }
        )
    return pd.DataFrame(rows)


def add_buckets(cycles: pd.DataFrame) -> pd.DataFrame:
    c = cycles.copy()
    c["rise bucket"] = pd.cut(c["rise_pp"], [0, 2, 4, 100], labels=["1-2pp", "2-4pp", ">4pp"], right=False)
    c["inflation at peak"] = pd.cut(
        c["infl_at_peak"], [-100, 2, 5, 1e6], labels=["< 2%", "2-5%", "> 5%"], right=False
    )
    return c


def logit_recession(cycles: pd.DataFrame) -> dict | None:
    """Logit of 'recession after' on the rise, inflation at peak and the real rate at peak, with
    era fixed effects omitted (N is small within eras). Returns coefficients and N, or None."""
    import statsmodels.api as sm

    d = cycles.dropna(subset=["recession_after", "rise_pp", "infl_at_peak", "real_rate_at_peak"]).copy()
    d = d[d["infl_at_peak"].abs() < 100]  # drop hyperinflation episodes
    if len(d) < 30 or d["recession_after"].nunique() < 2:
        return None
    X = sm.add_constant(d[["rise_pp", "infl_at_peak", "real_rate_at_peak"]].astype(float))
    y = d["recession_after"].astype(float)
    try:
        res = sm.Logit(y, X).fit(
            disp=0, cov_type="cluster", cov_kwds={"groups": d["ISO3"].astype("category").cat.codes}
        )
    except Exception:  # separation or singular design: report nothing rather than garbage
        return None
    return {
        "params": res.params,
        "se": res.bse,
        "p": res.pvalues,
        "n": int(res.nobs),
        "countries": int(d["ISO3"].nunique()),
    }


def current_position(
    panel: pd.DataFrame, last_year: int, countries: tuple[str, ...] = ("USA", "DEU", "JPN"), lookback: int = 6
) -> pd.DataFrame:
    """Where each focus country stands now (cycles still under way are not in find_cycles until they
    pass min_rise). Trough = lowest rate in the last `lookback` realised years; peak = highest rate
    after it. 'rise (pp)' = peak - trough; 'past peak' when the rate is 0.5pp or more below the peak.
    Inflation is taken at the peak year, as in find_cycles, so past cycles are comparable."""
    p = panel[(panel["year"] <= last_year) & panel["ISO3"].isin(countries)].copy()
    p["rate"] = policy_rate(p)
    rows = []
    for iso, g in p.groupby("ISO3"):
        g = g.set_index("year").sort_index().dropna(subset=["rate"])
        if g.empty:
            continue
        w = g.loc[last_year - lookback : last_year]
        t = int(w["rate"][::-1].idxmin())  # latest year at the low, as in _cycles_one
        after = w.loc[t:]
        pk = int(after["rate"].idxmax())
        now = float(g["rate"].iloc[-1])
        past = float(after["rate"].max()) - now >= 0.5
        rows.append(
            {
                "ISO3": iso,
                "country": g["countryname"].iloc[0],
                "trough": t,
                "peak": pk,
                "latest year": int(g.index.max()),
                "rate now": now,
                "rise (pp)": float(after.loc[pk, "rate"] - after.loc[t, "rate"]),
                "stage": f"past peak (peak {pk})" if past else "rising or at peak",
                "inflation at peak": float(g["infl"].get(pk, np.nan)),
                "inflation latest": float(g["infl"].iloc[-1]),
            }
        )
    return pd.DataFrame(rows).set_index("ISO3")


def current_cycles(cycles: pd.DataFrame, countries: tuple[str, ...] = ("USA", "DEU", "JPN")) -> pd.DataFrame:
    """Latest cycle for each focus country (DEU stands in for the euro area: the GMD has no aggregate)."""
    c = cycles[cycles["ISO3"].isin(countries)].sort_values("trough")
    return c.groupby("ISO3").tail(1).set_index("ISO3")


def similar_share(
    cycles: pd.DataFrame,
    rise: float,
    infl: float,
    tol_rise: float = 1.0,
    tol_infl: float = 2.0,
    exclude: tuple[str, int] | None = None,
):
    """Recession share among past cycles of similar size and inflation (nearest-neighbour box).
    `exclude` = (ISO3, trough year) of the cycle being assessed, so it is not its own comparator."""
    if exclude is not None:
        cycles = cycles[~((cycles["ISO3"] == exclude[0]) & (cycles["trough"] == exclude[1]))]
    d = cycles[
        (cycles["rise_pp"].sub(rise).abs() <= tol_rise) & (cycles["infl_at_peak"].sub(infl).abs() <= tol_infl)
    ]
    r = d["recession_after"].dropna().astype(bool)
    lo, hi = wilson(int(r.sum()), len(r))
    return {"n": len(r), "share": float(r.mean()) if len(r) else np.nan, "lo": lo, "hi": hi}
