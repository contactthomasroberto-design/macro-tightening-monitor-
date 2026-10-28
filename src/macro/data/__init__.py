"""Data layer: one interface over pluggable sources.

    get_series(id, vintage=None, as_of=None, refresh=False) -> pd.Series

- demo mode: synthetic generator, written once to the demo SQLite cache.
- live mode: SQLite cache with TTL by frequency; on expiry the source is called (with retries);
  if the source fails, the last cached copy is returned with `attrs["stale"] = True` and the
  failure is logged in `fetch_log` (the dashboard shows a banner). No silent failure: if there is
  neither data nor cache, `DataUnavailable` is raised.

Every returned Series carries provenance in `.attrs`: source, fetched_at, stale, vintage, mode.
"""

from __future__ import annotations

import logging

import pandas as pd

from macro.config import catalogue
from macro.data import demo, sources
from macro.data.http import SourceError
from macro.data.store import Store
from macro.data.vintages import LATEST_VINTAGE_LABEL, truncate_as_of
from macro.utils import is_demo

log = logging.getLogger("macro.data")


class DataUnavailable(RuntimeError):
    pass


_stores: dict[str, Store] = {}


def store() -> Store:
    from macro.data.store import default_path

    key = str(default_path())
    if key not in _stores:
        _stores[key] = Store(key)
    return _stores[key]


def _attach(s: pd.Series, source: str, fetched_at, stale: bool, vintage: str | None) -> pd.Series:
    s.attrs.update(
        {
            "source": source,
            "fetched_at": str(fetched_at) if fetched_at else None,
            "stale": stale,
            "vintage": vintage or LATEST_VINTAGE_LABEL,
            "mode": "demo" if is_demo() else "live",
        }
    )
    return s


def load_demo_into_store(st: Store | None = None) -> int:
    st = st or store()
    n = 0
    for sid, s in demo.generate().items():
        df = pd.DataFrame({"date": s.index, "value": s.to_numpy(), "vintage_date": pd.NaT})
        n += st.write(sid, df, source="demo")
    return n


def refresh_series(series_id: str, st: Store | None = None) -> tuple[bool, str]:
    """Fetch one series from its live source into the cache. Returns (ok, message)."""
    st = st or store()
    spec = catalogue().get(series_id)
    try:
        df = sources.fetch(spec)
    except (SourceError, ValueError, KeyError) as exc:
        msg = f"{type(exc).__name__}: {exc}"
        log.warning("fetch failed for %s: %s", series_id, msg)
        st.log_fetch(series_id, False, msg)
        return False, msg
    st.write(series_id, df, source=spec.source)
    st.log_fetch(series_id, True, f"{len(df)} rows, last {df['date'].iloc[-1].date()}")
    return True, "ok"


def get_series(series_id: str, vintage: str | None = None, as_of=None, refresh: bool = False) -> pd.Series:
    """Return a series by catalogue id.

    vintage: ALFRED real-time vintage (YYYY-MM-DD), read from the cache (populate with
             scripts/update_data.py --vintages). Latest vintage when None.
    as_of:   apply publication-lag truncation (pseudo real time, BRIEF §2.2).
    """
    spec = catalogue().get(series_id)
    st = store()
    if is_demo():
        if st.last_fetched(series_id) is None:
            load_demo_into_store(st)
        s = st.read(series_id)
        s = _attach(s, "demo (synthetic)", st.last_fetched(series_id), False, None)
    elif vintage is not None:
        s = st.read(series_id, vintage=vintage)
        if s.empty:
            raise DataUnavailable(
                f"no cached ALFRED vintage {vintage} for {series_id}; run update_data.py --vintages"
            )
        s = _attach(s, f"{spec.source} (ALFRED)", st.last_fetched(series_id), False, vintage)
    else:
        stale = False
        if refresh or not st.is_fresh(series_id, spec.freq):
            ok, _ = refresh_series(series_id, st)
            stale = not ok
        s = st.read(series_id)
        if s.empty:
            raise DataUnavailable(f"{series_id}: source failed and no cached copy")
        s = _attach(s, spec.source, st.last_fetched(series_id), stale, None)
    if as_of is not None:
        attrs = dict(s.attrs)
        s = truncate_as_of(s, as_of, series_id=series_id)
        s.attrs.update(attrs | {"as_of": str(pd.Timestamp(as_of).date())})
    return s


def get_frame(ids: list[str], **kw) -> pd.DataFrame:
    """Several series side by side (outer join on dates, native frequencies preserved)."""
    return pd.concat({i: get_series(i, **kw) for i in ids}, axis=1)


def try_series(series_id: str, **kw) -> pd.Series | None:
    """Like get_series but returns None (and logs) when unavailable — for optional inputs."""
    try:
        return get_series(series_id, **kw)
    except DataUnavailable as exc:
        log.warning("%s", exc)
        return None


def as_of_label(*series: pd.Series | None) -> str:
    """Latest common observation date across inputs, for chart footers."""
    dates = [s.dropna().index.max() for s in series if s is not None and not s.dropna().empty]
    return min(dates).strftime("%Y-%m-%d") if dates else "n/a"


def source_label(*ids: str) -> str:
    """Provider-grouped source line, e.g. 'FRED (DGS2, DGS10); ECB Data Portal (EA_DFR)'."""
    names = {
        "fred": "FRED",
        "ecb": "ECB Data Portal",
        "eurostat": "Eurostat",
        "bis": "BIS",
        "boj": "Bank of Japan",
        "mof": "Japan MOF",
        "atlanta_fed": "Atlanta Fed",
        "yahoo": "Yahoo Finance",
        "cftc": "CFTC TFF",
        "nyfed_files": "NY Fed",
        "fed_board_files": "Federal Reserve Board",
        "philly": "Philadelphia Fed",
    }
    groups: dict[str, list[str]] = {}
    for i in dict.fromkeys(ids):
        groups.setdefault(names[catalogue().get(i).source], []).append(i)
    lab = "; ".join(f"{k} ({', '.join(v)})" for k, v in groups.items())
    return ("SYNTHETIC — " + lab) if is_demo() else lab
