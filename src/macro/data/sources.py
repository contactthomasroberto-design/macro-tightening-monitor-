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
        "kind": "hlw",
    },
    "LW": {
        "url": "https://www.newyorkfed.org/medialibrary/media/research/economists/williams/data/Laubach_Williams_current_estimates.xlsx",
        "kind": "lw",
    },
    "GSCPI": {
        "url": "https://www.newyorkfed.org/medialibrary/research/interactives/gscpi/downloads/gscpi_data.xlsx",
        "kind": "excel",
    },
    "ACMTermPremium.xls": {
        "url": "https://www.newyorkfed.org/medialibrary/media/research/data_indicators/ACMTermPremium.xls",
        "kind": "excel",
    },
    "CIE": {"url": None, "kind": "manual"},
    "MPT": {
        "url": "https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/research-and-data/data/market-probability-tracker/mpt_histdata.xlsx",
        "kind": "mpt",
    },  # Fed Board CIE: no stable file URL found (checked 2026-10-28)
    "FCIG_1Y": {
        "url": "https://www.federalreserve.gov/econres/notes/feds-notes/fci_g_public_monthly_1yr.csv",
        "kind": "csv",
    },
    "SPF_GROWTH": {
        "url": "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/historical-data/meangrowth.xlsx",
        "kind": "spf_growth",
    },
    "SPF_INFL": {
        "url": "https://www.philadelphiafed.org/-/media/frbp/assets/surveys-and-data/survey-of-professional-forecasters/historical-data/inflation.xlsx",
        "kind": "spf_infl",
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
YAHOO_PAUSE = pd.Timedelta(hours=1)
_yahoo_blocked_until: pd.Timestamp | None = None


def fetch_yahoo(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """Yahoo chart API, daily closes (adjusted if available). Personal-use terms.

    Explicit period1/period2: with range=max Yahoo silently downgrades the interval to 3 months.
    Circuit breaker: after a rate-limit answer (HTTP 429) Yahoo is not asked again for an hour, so
    the catalogue fallbacks answer at once (shared cloud IPs are often rate-limited)."""
    global _yahoo_blocked_until
    now = pd.Timestamp.now(tz="UTC")
    if _yahoo_blocked_until is not None and now < _yahoo_blocked_until:
        raise SourceError(f"Yahoo paused after a rate limit until {_yahoo_blocked_until:%H:%M} UTC")
    params = {"period1": 0, "period2": int(now.timestamp()), "interval": "1d"}
    try:
        js = get(f"{YAHOO_API}/{spec.source_id}", params).json()
    except SourceError as exc:
        if "HTTP 429" in str(exc):
            _yahoo_blocked_until = now + YAHOO_PAUSE
        raise
    try:
        res = js["chart"]["result"][0]
        ts = res["timestamp"]
        ind = res["indicators"]
        close = (ind.get("adjclose") or [{}])[0].get("adjclose") or ind["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SourceError(f"unexpected Yahoo payload for {spec.source_id}") from exc
    granularity = res.get("meta", {}).get("dataGranularity", "1d")
    if granularity != "1d":
        raise SourceError(f"Yahoo returned {granularity} data for {spec.source_id}, expected 1d")
    dates = pd.to_datetime(ts, unit="s").normalize()
    return _tidy(dates, np.array(close, dtype=float))


# ------------------------------------------------------------------------------------ CFTC TFF
def fetch_cftc(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """CFTC Traders in Financial Futures (futures only), net = long - short for a trader group.

    source_id = 'TFF:<cftc_contract_market_code>:<group>' with group in {lev_money, asset_mgr,
    dealer, other_rept}. The contract code is stable across contract renamings (e.g. the February
    2022 renames such as '10-YEAR U.S. TREASURY NOTES' -> 'UST 10Y NOTE'). Dates are Tuesdays.
    """
    _, code, group = spec.source_id.split(":")
    params = {
        "$where": f"cftc_contract_market_code='{code}'",
        "$select": f"report_date_as_yyyy_mm_dd,{group}_positions_long,{group}_positions_short",
        "$limit": 50000,
        "$order": "report_date_as_yyyy_mm_dd",
    }
    df = pd.DataFrame(get(CFTC_TFF, params).json())
    if df.empty:
        raise SourceError(f"no CFTC rows for contract {code}")
    net = pd.to_numeric(df[f"{group}_positions_long"]) - pd.to_numeric(df[f"{group}_positions_short"])
    return _tidy(df["report_date_as_yyyy_mm_dd"], net)


# ------------------------------------------------------------------------------------ Eurostat / BIS
EUROSTAT_API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
BIS_API = "https://stats.bis.org/api/v1/data"


def _jsonstat_series(js: dict) -> pd.Series:
    """One-dimensional JSON-stat answer (all other dimensions filtered to one value) -> Series by time."""
    if "error" in js:
        raise SourceError(f"Eurostat error: {js['error']}")
    times = js["dimension"]["time"]["category"]["index"]
    pos = {v: k for k, v in times.items()}
    vals = {pos[int(i)]: v for i, v in js.get("value", {}).items()}
    return pd.Series(vals).sort_index()


def _eurostat_period(labels: pd.Index) -> pd.DatetimeIndex:
    lab = labels.astype(str)
    if lab.str.contains("Q").any():
        return pd.PeriodIndex(lab.str.replace("-Q", "Q"), freq="Q").to_timestamp()
    return pd.to_datetime(lab)


def fetch_eurostat(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """Eurostat dissemination API (JSON-stat).

    'prc_hicp_minr:<geo>:<unit>:<coicop18>'  HICP (ECOICOP v2), monthly index.
    'techrec:namq_10_gdp:<geo>:<unit>:<s_adj>:<na_item>'  technical-recession indicator derived from
        quarterly real GDP: a quarter is in recession when it belongs to a run of two or more
        consecutive quarter-on-quarter declines; expanded to the three months of each quarter.
    """
    parts = spec.source_id.split(":")
    if parts[0] == "techrec":
        _, ds, geo, unit, sadj, item = parts
        js = get(f"{EUROSTAT_API}/{ds}", {"geo": geo, "unit": unit, "s_adj": sadj, "na_item": item}).json()
        gdp = _jsonstat_series(js)
        gdp.index = _eurostat_period(gdp.index)
        neg = (gdp.diff() < 0).astype(int)
        run = neg.groupby((neg != neg.shift()).cumsum()).transform("sum") * neg
        rec_q = (run >= 2).astype(float)
        months = pd.date_range(rec_q.index[0], rec_q.index[-1] + pd.offsets.QuarterEnd(0), freq="MS")
        rec_m = rec_q.reindex(months, method="ffill")
        return _tidy(rec_m.index, rec_m.to_numpy())
    ds, geo, unit, coicop = parts
    js = get(f"{EUROSTAT_API}/{ds}", {"geo": geo, "unit": unit, "coicop18": coicop}).json()
    sr = _jsonstat_series(js)
    return _tidy(_eurostat_period(sr.index), sr.to_numpy())


def fetch_bis(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """BIS statistics SDMX REST, csv. source_id = '<dataflow>:<key>'."""
    flow, key = spec.source_id.split(":", 1)
    text = get(f"{BIS_API}/{flow}/{key}/all", {"format": "csv"}).text
    df = pd.read_csv(io.StringIO(text))
    if "TIME_PERIOD" not in df or "OBS_VALUE" not in df:
        raise SourceError(f"unexpected BIS csv columns: {list(df.columns)[:8]}")
    return _tidy(pd.to_datetime(df["TIME_PERIOD"].astype(str)), df["OBS_VALUE"])


# ------------------------------------------------------------------------------------ Japan: BoJ, MOF
BOJ_API = "https://www.stat-search.boj.or.jp/api/v1/getDataCode"
MOF_JGB = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate"


def fetch_boj(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """Bank of Japan Time-Series Data Search API. source_id = '<DB>:<SERIES_CODE>' (e.g. FM02:STRACLUCON).
    Dates come as YYYYMMDD (daily) or YYYYMM (monthly); the API pages long series via NEXTPOSITION."""
    db, code = spec.source_id.split(":")
    dates: list = []
    values: list = []
    pos = None
    for _ in range(50):
        params = {"format": "json", "lang": "en", "db": db, "code": code}
        if pos:
            params["startPosition"] = pos
        js = get(BOJ_API, params).json()
        if js.get("STATUS") != 200 or not js.get("RESULTSET"):
            raise SourceError(f"BoJ API: {js.get('MESSAGE', 'no result')}")
        v = js["RESULTSET"][0]["VALUES"]
        dates += v["SURVEY_DATES"]
        values += v["VALUES"]
        pos = js.get("NEXTPOSITION")
        if not pos:
            break
    d = pd.Series(dates).astype(str)
    fmt = "%Y%m%d" if d.str.len().max() == 8 else "%Y%m"
    return _tidy(pd.to_datetime(d, format=fmt), pd.to_numeric(pd.Series(values), errors="coerce"))


def _jgb_csv(text: str) -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(text), skiprows=1, na_values=["-"])
    raw["Date"] = pd.to_datetime(raw["Date"], format="%Y/%m/%d", errors="coerce")
    return raw.dropna(subset=["Date"])


def fetch_mof_jgb(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """Japan Ministry of Finance JGB benchmark yields (daily). source_id = 'JGB:<tenor>' e.g. JGB:10Y.
    History file (to the previous month) + current-month file."""
    tenor = spec.source_id.split(":")[1]
    hist = _jgb_csv(get(f"{MOF_JGB}/historical/jgbcme_all.csv").text)
    cur = _jgb_csv(get(f"{MOF_JGB}/jgbcme.csv").text)
    df = pd.concat([hist, cur]).drop_duplicates("Date", keep="last").sort_values("Date")
    if tenor not in df:
        raise SourceError(f"tenor {tenor} not in MOF JGB file: {list(df.columns)}")
    return _tidy(df["Date"], pd.to_numeric(df[tenor], errors="coerce"))


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
    resp = get(meta["url"])
    kind = meta["kind"]
    if kind == "csv":
        df = pd.read_csv(io.StringIO(resp.text))
        return _tidy(df[df.columns[0]], df[column])
    if kind == "hlw":
        return _parse_rstar(resp.content, "HLW Estimates", "Natural Rate (r*)", column)
    if kind == "lw":
        return _parse_rstar(resp.content, "data", "One-Sided Estimates", "rstar")
    if kind == "spf_growth":
        return _parse_spf_growth(resp.content, column)
    if kind == "spf_infl":
        return _parse_spf_infl(resp.content, column)
    if kind == "mpt":
        return _parse_mpt(resp.content, column)
    return _excel_column(resp.content, column)


def _parse_rstar(content: bytes, sheet: str, block: str, column: str) -> pd.DataFrame:
    """NY Fed r* workbooks: a header row names column blocks (e.g. 'Natural Rate (r*)'), the next row
    names the columns inside each block (US / Canada / Euro Area, or rstar / g / z). Dates in column 0."""
    raw = pd.read_excel(io.BytesIO(content), sheet_name=sheet, header=None)
    for r in range(min(15, len(raw))):
        row = raw.iloc[r].astype(str).str.strip()
        hits = [j for j, v in enumerate(row) if v == block]
        if not hits:
            continue
        sub = raw.iloc[r + 1].astype(str).str.strip()
        j = next((k for k in range(hits[0], raw.shape[1]) if sub.iloc[k] == column), None)
        if j is None:
            break
        body = raw.iloc[r + 2 :]
        dates = pd.to_datetime(body.iloc[:, 0], errors="coerce")
        return _tidy(dates, body.iloc[:, j])
    raise SourceError(f"block {block!r} / column {column!r} not found in sheet {sheet!r}")


def _parse_mpt(content: bytes, column: str) -> pd.DataFrame:
    """Atlanta Fed Market Probability Tracker (options on 3-month compounded SOFR): for each trade date,
    the mean of the risk-neutral distribution of the 3-month average fed funds rate for each quarterly
    reference period. '<N>m' -> linear interpolation of that mean at trade date + N months (percent).
    Risk-neutral: includes term/risk premia, so it is 'priced', not an expectation."""
    months = int(column.rstrip("m"))
    df = pd.read_excel(io.BytesIO(content), sheet_name="DATA")
    df = df[df["field"] == "Rate: mean"].copy()
    df["date"] = pd.to_datetime(df["date"])
    df["ref"] = pd.to_datetime(df["reference_start"])
    df["days"] = (df["ref"] - df["date"]).dt.days
    target = months * 30.4375
    out = {}
    for d, g in df.groupby("date"):
        g = g.sort_values("days")
        if g["days"].min() <= target <= g["days"].max():
            out[d] = float(np.interp(target, g["days"], g["value"])) / 100
    if not out:
        raise SourceError("MPT file: no trade date spans the requested horizon")
    sr = pd.Series(out).sort_index()
    return _tidy(sr.index, sr.to_numpy())


def _spf_dates(df: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.PeriodIndex.from_fields(
        year=df["YEAR"].astype(int), quarter=df["QUARTER"].astype(int), freq="Q"
    ).to_timestamp()


def _parse_spf_growth(content: bytes, column: str) -> pd.DataFrame:
    """SPF meanGrowth.xlsx: one sheet per variable, columns d<var>2..d<var>6 = annualised q/q growth
    forecasts for the current quarter (2) and the next four (3..6).
    '<VAR>:cq' -> current quarter; '<VAR>:4q' -> geometric mean of quarters 3..6."""
    var, what = column.split(":")
    xl = pd.read_excel(io.BytesIO(content), sheet_name=var)
    d = f"d{var.lower()}"
    dates = _spf_dates(xl)
    if what == "cq":
        return _tidy(dates, xl[f"{d}2"])
    g = xl[[f"{d}{k}" for k in range(3, 7)]].apply(pd.to_numeric, errors="coerce")
    return _tidy(dates, 100 * (np.prod(1 + g / 100, axis=1) ** (1 / 4) - 1))


def _parse_spf_infl(content: bytes, column: str) -> pd.DataFrame:
    """SPF Inflation.xlsx (sheet INFLATION): INFCPI1YR, INFCPI10YR, INFPGDP1YR (median forecasts)."""
    xl = pd.read_excel(io.BytesIO(content), sheet_name="INFLATION")
    return _tidy(_spf_dates(xl), xl[column])


FETCHERS: dict[str, Callable[[SeriesSpec, str | None], pd.DataFrame]] = {
    "fred": fetch_fred,
    "ecb": fetch_ecb,
    "eurostat": fetch_eurostat,
    "bis": fetch_bis,
    "boj": fetch_boj,
    "mof": fetch_mof_jgb,
    "atlanta_fed": fetch_research_file,
    "yahoo": fetch_yahoo,
    "cftc": fetch_cftc,
    "nyfed_files": fetch_research_file,
    "fed_board_files": fetch_research_file,
    "philly": fetch_research_file,
}


def _normalise_dates(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Monthly and quarterly observations are dated at period start throughout the project
    (some sources date them at period end, e.g. the FCI-G csv)."""
    if freq in ("M", "Q"):
        df = df.copy()
        df["date"] = df["date"].dt.to_period(freq).dt.to_timestamp()
        df = df.drop_duplicates("date", keep="last")
    return df


def fetch(spec: SeriesSpec, vintage: str | None = None) -> pd.DataFrame:
    """Primary source; on failure, the catalogue fallback (if any). The returned frame records which
    source answered in df.attrs['source']."""
    try:
        df = FETCHERS[spec.source](spec, vintage)
        df.attrs["source"] = spec.source
    except (SourceError, ValueError, KeyError) as exc:
        if not spec.fallback:
            raise
        log.warning("%s: primary source failed (%s); using fallback %s", spec.id, exc, spec.fallback)
        fb = spec.model_copy(
            update={
                "source": spec.fallback["source"],
                "source_id": spec.fallback["source_id"],
                "fallback": None,
            }
        )
        df = FETCHERS[fb.source](fb, vintage)
        df.attrs["source"] = f"{fb.source} (fallback for {spec.source})"
    out = _normalise_dates(df, spec.freq)
    out.attrs = df.attrs
    return out


__all__ = ["fetch", "fetch_alfred_all_vintages", "SourceError", "MANUAL_DIR", "Path"]
