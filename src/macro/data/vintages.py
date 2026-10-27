"""Publication lags and point-in-time views.

Two levels of real-time discipline (BRIEF §2.1-2.2):

1. **True vintages** (ALFRED, Philadelphia Fed RTDSM): values as they were published, revisions
   included. Read with `get_series(id, vintage=...)`.
2. **Release-lag truncation** (always applied in pseudo out-of-sample loops): an observation for
   reference period p is treated as available from `period_end(p) + release_lag_days`. This
   removes look-ahead from timing but NOT from revisions, so results built this way are labelled
   "latest-vintage, not point-in-time".
"""

from __future__ import annotations

import pandas as pd

from macro.config import catalogue

LATEST_VINTAGE_LABEL = "latest-vintage, not point-in-time"


def period_end(index: pd.DatetimeIndex, freq: str) -> pd.DatetimeIndex:
    """Last calendar day of each reference period. Observations are dated at period start for
    M and Q (FRED/ECB convention) and at the observation day for D and W (FRED weekly series are
    dated by week-ending day)."""
    if freq == "M":
        return index + pd.offsets.MonthEnd(0)
    if freq == "Q":
        return index + pd.offsets.QuarterEnd(0)
    return index


def available_at(s: pd.Series, freq: str, lag_days: int) -> pd.Series:
    """Date from which each observation is assumed public."""
    return pd.Series(period_end(pd.DatetimeIndex(s.index), freq) + pd.Timedelta(days=lag_days), index=s.index)


def truncate_as_of(s: pd.Series, as_of, series_id: str | None = None, freq: str | None = None,
                   lag_days: int | None = None) -> pd.Series:
    """Keep only observations published on or before `as_of`."""
    if series_id is not None:
        spec = catalogue().get(series_id)
        freq = freq or spec.freq
        lag_days = spec.release_lag_days if lag_days is None else lag_days
    if freq is None or lag_days is None:
        raise ValueError("need series_id or (freq, lag_days)")
    avail = available_at(s, freq, lag_days)
    return s[avail <= pd.Timestamp(as_of)]


def panel_as_of(panel: dict[str, pd.Series], as_of) -> dict[str, pd.Series]:
    return {k: truncate_as_of(v, as_of, series_id=k) for k, v in panel.items()}
