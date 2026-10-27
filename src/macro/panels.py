"""Input panels for each model module, assembled from the data layer.

This is the only place where model inputs are read; model modules receive DataFrames and do no
I/O, which keeps them testable on simulated data with planted parameters.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from macro.config import catalogue
from macro.data import get_series, try_series
from macro.utils import to_monthly

INFLATION_IDS = {
    "US": {
        "headline": "CPIAUCSL",
        "core": "CPILFESL",
        "energy": "CPIENGSL",
        "food": "CPIUFDSL",
        "services": "CUSR0000SAS",
        "goods": "CUSR0000SACL1E",
        "ppi": "PPIFIS",
        "pce": "PCEPI",
        "core_pce": "PCEPILFE",
        "median": "MEDCPIM158SFRBCLE",
        "trimmed": "TRMMEANCPIM158SFRBCLE",
        "sticky": "CORESTICKM159SFRBATL",
        "unemp": "UNRATE",
        "nrou": "NROU",
    },
    "EA": {
        "headline": "EA_HICP",
        "core": "EA_HICP_CORE",
        "energy": "EA_HICP_ENERGY",
        "food": "EA_HICP_FOOD",
        "services": "EA_HICP_SERV",
        "goods": "EA_HICP_NEIG",
        "unemp": "EA_UNRATE",
    },
    "JP": {"headline": "JP_CPI"},
}

EXPECTATION_IDS = ["MICH", "SPF_CPI_1Y", "SPF_CPI10", "T10YIE", "T5YIFR", "EXPINF10YR"]


def monthly(series_id: str, how: str = "mean", optional: bool = False) -> pd.Series | None:
    """Series at month-start frequency: monthly as is, quarterly forward-filled within the quarter,
    daily/weekly averaged (or last value with how='last')."""
    s = try_series(series_id) if optional else get_series(series_id)
    if s is None:
        return None
    freq = catalogue().get(series_id).freq
    if freq == "M":
        return s
    if freq == "Q":
        return s.resample("MS").ffill()
    return to_monthly(s, how)


def oil_local(region: str) -> pd.Series:
    """Monthly average Brent in local currency (USD for US, EUR for EA, JPY for JP)."""
    brent = monthly("DCOILBRENTEU")
    if region == "EA":
        return (brent / monthly("EURUSD")).dropna()
    if region == "JP":
        return (brent * monthly("USDJPY")).dropna()
    return brent


def inflation_panel(region: str) -> pd.DataFrame:
    """Monthly price indexes (levels) and real-side inputs for the inflation module."""
    ids = INFLATION_IDS[region]
    cols = {}
    for k, sid in ids.items():
        s = monthly(sid, optional=k not in ("headline",))
        if s is not None:
            cols[k] = s
    df = pd.DataFrame(cols)
    df["oil"] = oil_local(region)
    g = monthly("GSCPI", optional=True)
    if g is not None and region in ("US", "EA"):
        df["gscpi"] = g
    return df.sort_index()


def expectations_panel() -> pd.DataFrame:
    """US inflation-expectation measures at monthly frequency (quarterly surveys forward-filled
    within the quarter they were published in)."""
    cols = {}
    for sid in EXPECTATION_IDS:
        s = monthly(sid, optional=True)
        if s is not None:
            cols[sid] = s
    return pd.DataFrame(cols).sort_index()


def unemployment_gap(region: str, panel: pd.DataFrame) -> pd.Series:
    """US: UNRATE - CBO NROU. EA/JP: deviation from a backward-looking 10-year mean
    (no official natural-rate series in the catalogue; stated on the page)."""
    if "unemp" not in panel:
        return pd.Series(np.nan, index=panel.index)
    if region == "US" and "nrou" in panel:
        return panel["unemp"] - panel["nrou"].ffill()
    return panel["unemp"] - panel["unemp"].rolling(120, min_periods=36).mean()


POLICY_IDS = {
    "fed": {
        "rate": "DFF",
        "infl": "PCEPILFE",
        "infl_label": "core PCE",
        "unemp": "UNRATE",
        "ustar": "NROU",
        "gdp": "GDPC1",
        "pot": "GDPPOT",
        "y2": "DGS2",
        "rstar": ["HLW_RSTAR_US", "LW_RSTAR_US"],
    },
    "ecb": {
        "rate": "EA_DFR",
        "infl": "EA_HICP_CORE",
        "infl_label": "HICP excl. energy and food",
        "unemp": "EA_UNRATE",
        "y2": "EA_YC_2Y",
        "rstar": ["HLW_RSTAR_EA"],
    },
    "boj": {"rate": "JP_POLICY", "infl": "JP_CPI", "infl_label": "CPI all items", "rstar": []},
}


def policy_panel(bank: str) -> dict:
    """Quarterly and monthly inputs for the policy module.

    Output gap: US = 100 log(GDPC1/GDPPOT) (CBO potential); EA = Okun proxy -2 (u - u_trend) with a
    backward-looking 10-year mean as u_trend; JP = 0 (no gap series in the free catalogue; stated).
    """
    ids = POLICY_IDS[bank]
    rate_m = monthly(ids["rate"])
    pi_m = 100 * (monthly(ids["infl"]) / monthly(ids["infl"]).shift(12) - 1)
    m = pd.DataFrame({"i": rate_m, "pi": pi_m})
    if "unemp" in ids:
        m["u"] = monthly(ids["unemp"])
    if bank == "fed":
        m["ustar"] = monthly(ids["ustar"])
        gdp, pot = get_series(ids["gdp"]), get_series(ids["pot"])
        yq = 100 * np.log(gdp / pot.reindex(gdp.index))
        m["y"] = yq.resample("MS").ffill().reindex(m.index).ffill(limit=2)
        gap_note = "output gap = 100 log(real GDP / CBO potential GDP)"
    elif "u" in m:
        m["ustar"] = m["u"].rolling(120, min_periods=36).mean()
        m["y"] = -2.0 * (m["u"] - m["ustar"])
        gap_note = "output gap proxied by Okun's law, -2 x (u - backward 10-year mean of u)"
    else:
        m["y"] = 0.0
        gap_note = "no output-gap series available: gap set to 0 (inflation-only rule)"
    q = m.resample("QS").mean()
    y2 = monthly(ids["y2"]) if "y2" in ids else None
    return {"monthly": m, "quarterly": q, "y2": y2, "gap_note": gap_note, "ids": ids}


FCI_IDS = {
    "policy_rate": "DFF",
    "y10": "DGS10",
    "mortgage": "MORTGAGE30US",
    "baa": "DBAA",
    "equity": "SPX",
    "house": "CSUSHPISA",
    "dollar": "DTWEXBGS",
}


def fincond_panel() -> dict:
    """Quarterly-average levels of the seven FCI variables, GDP, and comparison indices."""
    levels_q = pd.DataFrame({k: monthly(sid).resample("QS").mean() for k, sid in FCI_IDS.items()})
    gdp = get_series("GDPC1")
    pot = get_series("GDPPOT")
    gap = 100 * np.log(gdp / pot.reindex(gdp.index))
    stat = pd.DataFrame(
        {
            "credit_spread": monthly("BAA10Y"),
            "vix": monthly("VIXCLS"),
            "curve_inversion": -monthly("T10Y3M"),
            "dollar_12m": 100 * np.log(monthly("DTWEXBGS")).diff(12),
            "equity_drawdown": -100
            * (monthly("SPX", how="last") / monthly("SPX", how="last").rolling(12).max() - 1),
        }
    )
    nfci = monthly("NFCI")
    fcig = monthly("FCIG_1Y", optional=True)
    return {
        "levels_q": levels_q,
        "gdp_q": gdp,
        "output_gap_q": gap,
        "stat_panel": stat,
        "nfci": nfci,
        "fcig": fcig,
    }
