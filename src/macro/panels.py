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
