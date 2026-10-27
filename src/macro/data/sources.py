"""Source adapters. Each `fetch_*` returns a tidy DataFrame with columns
`date` (Timestamp), `value` (float), `vintage_date` (Timestamp or NaT for latest-vintage).

Sources are deliberately thin and documented: the parsing rules below are the contract that
the live smoke test (`tests/test_live_smoke.py`) verifies against the real endpoints.
"""

from __future__ import annotations

import io
import logging
import os
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from macro.config import ROOT, SeriesSpec
from macro.data.http import SourceError, get

log = logging.getLogger("macro.data")

MANUAL_DIR = ROOT / "data" / "manual"

FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
ECB_API = "https://data-api.ecb.europa.eu/service/data"
YAHOO_API = "https://query1.finance.yahoo.com/v8/finance/chart"
CFTC_TFF = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"  # TFF futures only (verify)

# Published research files. URLs must be checked by the live smoke test; when a URL moves,
# drop the file in data/manual/<id>.csv (columns: date,value) and record the release date.
RESEARCH_FILES: dict[str, dict] = {
    "HLW": {
        "url": "https://www.newyorkfed.org/medialibrary/media/research/economists/williams/data/Holston_Laubach_Williams_current_estimates.xlsx",
        "kind": "excel",
    },
    "LW": {
        "url": "https://www.newyorkfed.org/medialibrary/media/research/economists/williams/data/Laubach_Williams_current_estimates.xlsx",
        "kind": "excel",
    },
    "GSCPI": {
        "url": "https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx",
        "kind": "excel",
    },
    "ACMTermPremium.xls": {
        "url": "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls",
        "kind": "excel",
    },
    "CIE": {"url": None, "kind": "manual"},  # Fed Board CIE: download page, no stable file URL known
    "FCIG": {"url": None, "kind": "manual"},  # Fed Board FCI-G: download page, no stable file URL known
    "SPF": {
        "url": "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/historical-data/meangrowth.xlsx",
        "kind": "excel",
    },
}


def _tidy(dates, values, vintage=None) -> pd.DataFrame:
    df = pd.DataFrame({"date": pd.to_datetime(dates), "value": pd.to_numeric(values, errors="coerce")})
    df["vintage_date"] = pd.Timestamp(vintage) if vintage is not None else pd.NaT
    df = df.dropna(subset=["date", "value"]).drop_duplicates("date", keep="last").sort_values("date")
    if df.empty:
        raise SourceError("parsed series is empty")
    return df.reset_index(drop=True)


# ------------------------------------------------------------------------------------ FRED / ALFRED
def fetch_fred(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """FRED latest vintage, or a single ALFRED vintage when `vintage` is given (needs FRED_API_KEY).

    Without an API key the public csv endpoint is used: latest vintage only.
    """
    key = os.environ.get("FRED_API_KEY")
    if key:
        params = {"series_id": spec.source_id, "api_key": key, "file_type": "json"}
        if vintage:
            params |= {"realtime_start": vintage, "realtime_end": vintage}
        obs = get(FRED_API, params).json().get("observations", [])
        return _tidy([o["date"] for o in obs], [o["value"] for o in obs], vintage)
    if vintage:
        raise SourceError("ALFRED vintages need FRED_API_KEY; results are latest-vintage, not point-in-time")
    text = get(FRED_CSV, {"id": spec.source_id}).text
    df = pd.read_csv(io.StringIO(text), na_values=["."])
    date_col = df.columns[0]  # 'observation_date' (current) or 'DATE' (older format)
    return _tidy(df[date_col], df[df.columns[1]])


def fetch_alfred_all_vintages(spec: SeriesSpec) -> pd.DataFrame:
    """Every vintage of a FRED series (ALFRED). Each row's vintage_date = its realtime_start."""
    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise SourceError("ALFRED needs FRED_API_KEY")
    params = {
        "series_id": spec.source_id,
        "api_key": key,
        "file_type": "json",
        "realtime_start": "1776-07-04",
        "realtime_end": "9999-12-31",
    }
    obs = get(FRED_API, params).json().get("observations", [])
    df = pd.DataFrame(obs)
    if df.empty:
        raise SourceError("no ALFRED vintages")
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(df["date"]),
            "value": pd.to_numeric(df["value"], errors="coerce"),
            "vintage_date": pd.to_datetime(df["realtime_start"]),
        }
    )
    return out.dropna(subset=["value"]).sort_values(["vintage_date", "date"]).reset_index(drop=True)


# ------------------------------------------------------------------------------------ ECB
def fetch_ecb(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """ECB Data Portal SDMX REST, csv format. source_id = '<FLOW>.<KEY>'."""
    flow, key = spec.source_id.split(".", 1)
    text = get(f"{ECB_API}/{flow}/{key}", {"format": "csvdata"}).text
    df = pd.read_csv(io.StringIO(text))
    if "TIME_PERIOD" not in df or "OBS_VALUE" not in df:
        raise SourceError(f"unexpected ECB csv columns: {list(df.columns)[:8]}")
    periods = df["TIME_PERIOD"].astype(str)
    if spec.freq == "Q":
        dates = pd.PeriodIndex(periods.str.replace("-Q", "Q"), freq="Q").to_timestamp()
    else:
        dates = pd.to_datetime(periods)
    return _tidy(dates, df["OBS_VALUE"])


# ------------------------------------------------------------------------------------ Yahoo
def fetch_yahoo(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """Yahoo chart API, daily closes (adjusted if available). Personal-use terms."""
    js = get(f"{YAHOO_API}/{spec.source_id}", {"range": "max", "interval": "1d"}).json()
    try:
        res = js["chart"]["result"][0]
        ts = res["timestamp"]
        ind = res["indicators"]
        close = (ind.get("adjclose") or [{}])[0].get("adjclose") or ind["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SourceError(f"unexpected Yahoo payload for {spec.source_id}") from exc
    dates = pd.to_datetime(ts, unit="s").normalize()
    return _tidy(dates, np.array(close, dtype=float))


# ------------------------------------------------------------------------------------ CFTC TFF
def fetch_cftc(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """CFTC Traders in Financial Futures (futures only), net = long - short for a trader group.

    source_id = 'TFF:<market name substring>:<group>' with group in
    {lev_money, asset_mgr, dealer, other_rept}. Dates are the Tuesday reference dates.
    """
    _, market, group = spec.source_id.split(":")
    params = {
        "$where": f"upper(market_and_exchange_names) like '%{market.upper()}%'",
        "$select": f"report_date_as_yyyy_mm_dd,market_and_exchange_names,{group}_positions_long_all,{group}_positions_short_all",
        "$limit": 50000,
        "$order": "report_date_as_yyyy_mm_dd",
    }
    rows = get(CFTC_TFF, params).json()
    df = pd.DataFrame(rows)
    if df.empty:
        raise SourceError(f"no CFTC rows for {market}")
    # A substring can match several contracts (e.g. 'ULTRA'); keep the most frequent exact name.
    name = df["market_and_exchange_names"].value_counts().index[0]
    df = df[df["market_and_exchange_names"] == name]
    net = pd.to_numeric(df[f"{group}_positions_long_all"]) - pd.to_numeric(df[f"{group}_positions_short_all"])
    return _tidy(df["report_date_as_yyyy_mm_dd"], net)


# ------------------------------------------------------------------------------------ research files
def _manual(spec: SeriesSpec) -> pd.DataFrame | None:
    p = MANUAL_DIR / f"{spec.id}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    return _tidy(df["date"], df["value"])


def _excel_column(content: bytes, column: str) -> pd.DataFrame:
    """Find `column` in any sheet of a workbook; the first datetime-like column is the date."""
    sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None)
    for _, raw in sheets.items():
        for hdr in range(min(10, len(raw))):
            row = raw.iloc[hdr].astype(str).str.strip()
            if column in set(row):
                df = raw.iloc[hdr + 1 :].copy()
                df.columns = row
                date_col = df.columns[0]
                return _tidy(df[date_col], df[column])
    raise SourceError(f"column {column!r} not found in workbook")


def fetch_research_file(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """Published research series (NY Fed, Fed Board, Philadelphia Fed).

    Order: manual drop in data/manual/<id>.csv, then the scripted download in RESEARCH_FILES.
    """
    manual = _manual(spec)
    if manual is not None:
        return manual
    file_key, column = spec.source_id.split(":", 1)
    meta = RESEARCH_FILES.get(file_key)
    if not meta or not meta["url"]:
        raise SourceError(f"{spec.id}: no scripted download; place data/manual/{spec.id}.csv (date,value)")
    content = get(meta["url"]).content
    if file_key == "SPF":
        return _parse_spf(content, column)
    return _excel_column(content, column)


def _parse_spf(content: bytes, column: str) -> pd.DataFrame:
    """SPF mean growth file: one sheet per variable, columns YEAR, QUARTER, <VAR>1..<VAR>6.

    <VAR>2 is the current-quarter forecast; the 4-quarter-ahead average annualised growth is the
    geometric mean of <VAR>3..<VAR>6 (quarter-on-quarter annualised rates).
    'SPF:CPI10' reads the 10-year expectation sheet when present.
    """
    parts = column.split(":")
    var = parts[0]
    xl = pd.read_excel(io.BytesIO(content), sheet_name=None)
    if var not in xl:
        raise SourceError(f"SPF sheet {var} not found (sheets: {list(xl)[:10]})")
    df = xl[var]
    dates = pd.PeriodIndex.from_fields(
        year=df["YEAR"].astype(int), quarter=df["QUARTER"].astype(int), freq="Q"
    ).to_timestamp()
    if var == "CPI10":
        return _tidy(dates, df["CPI10"])
    if len(parts) > 1 and parts[1] == "cq":  # current-quarter forecast, e.g. RGDP2
        return _tidy(dates, df[f"{var}2"])
    cols = [f"{var}{k}" for k in range(3, 7)]
    g = df[cols].apply(pd.to_numeric, errors="coerce")
    four_q = 100 * (np.prod(1 + g / 100, axis=1) ** (1 / 4) - 1)
    return _tidy(dates, four_q)


FETCHERS: dict[str, Callable[[SeriesSpec, str | None], pd.DataFrame]] = {
    "fred": fetch_fred,
    "ecb": fetch_ecb,
    "yahoo": fetch_yahoo,
    "cftc": fetch_cftc,
    "nyfed_files": fetch_research_file,
    "fed_board_files": fetch_research_file,
    "philly": fetch_research_file,
}


def fetch(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    return FETCHERS[spec.source](spec, vintage)


__all__ = ["fetch", "fetch_alfred_all_vintages", "SourceError", "MANUAL_DIR", "Path"]
