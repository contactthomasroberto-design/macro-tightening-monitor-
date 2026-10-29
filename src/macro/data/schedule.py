"""When to re-ask a source: poll around expected releases instead of on a fixed timer.

Each catalogue series has a frequency and a release lag (days between the end of the reference
period and first publication, `config/series.yaml`). From the last observation in the cache this
gives the expected date of the next one:

    next period end + release lag      (monthly: end of the month after the last observation, ...)

- before that date (minus an early margin, because the lags are conservative) the series is checked
  at the slow frequency TTL (`store.TTL`), as before;
- inside the release window it is checked every few minutes until the new observation appears, so
  a CPI print reaches the dashboard within the polling interval of its publication at the source;
- if nothing has appeared long after the expected date (a lag set too short, a discontinued series),
  it falls back to the slow TTL instead of polling forever.

Daily market series are checked hourly once a new business day's value is due (FRED publishes most
of them once a day). Yahoo series are checked every two hours at most (rate limits).
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from macro.data.store import TTL

# (early margin, late cutoff, polling interval near the expected date, interval elsewhere in the window)
_WINDOWS = {
    "D": (dt.timedelta(0), dt.timedelta(days=7), dt.timedelta(hours=1), dt.timedelta(hours=1)),
    "W": (dt.timedelta(days=1), dt.timedelta(days=14), dt.timedelta(minutes=30), dt.timedelta(hours=1)),
    "M": (dt.timedelta(days=2), dt.timedelta(days=25), dt.timedelta(minutes=10), dt.timedelta(minutes=30)),
    "Q": (dt.timedelta(days=5), dt.timedelta(days=45), dt.timedelta(minutes=15), dt.timedelta(hours=1)),
}
NEAR = dt.timedelta(days=2)  # "near the expected date": the fast interval applies within this distance
SLOW_SOURCES = {"yahoo": dt.timedelta(hours=2)}  # minimum interval for rate-limited sources


def expected_next(freq: str, last_obs: pd.Timestamp, lag_days: int) -> pd.Timestamp:
    """Expected publication date of the observation after `last_obs`."""
    last_obs = pd.Timestamp(last_obs).normalize()
    if freq == "D":
        nxt = last_obs + pd.offsets.BDay(1)
    elif freq == "W":
        nxt = last_obs + pd.Timedelta(days=7)
    elif freq == "M":
        nxt = last_obs + pd.offsets.MonthEnd(0) + pd.offsets.MonthEnd(1)
    else:
        nxt = last_obs + pd.offsets.QuarterEnd(0) + pd.offsets.QuarterEnd(1)
    return nxt + pd.Timedelta(days=lag_days)


def poll_interval(spec, last_obs, now: dt.datetime) -> dt.timedelta:
    """How long a successful fetch of `spec` stays valid, given its last observation."""
    if last_obs is None:
        return dt.timedelta(0)
    early, late, fast, slow = _WINDOWS[spec.freq]
    lag = spec.release_lag_days
    if spec.freq == "M":
        early = max(early, dt.timedelta(days=lag // 2))
    elif spec.freq == "Q":
        early = max(early, dt.timedelta(days=lag // 3))
    exp = expected_next(spec.freq, last_obs, lag).to_pydatetime().replace(tzinfo=dt.UTC)
    if now < exp - early or now > exp + late:
        every = TTL[spec.freq]
    else:
        every = fast if abs(now - exp) <= NEAR else slow
    return max(every, SLOW_SOURCES.get(spec.source, dt.timedelta(0)))


def due(spec, last_obs, last_fetched: dt.datetime | None, now: dt.datetime | None = None) -> bool:
    """True when the series should be fetched now."""
    if last_fetched is None:
        return True
    now = now or dt.datetime.now(dt.UTC)
    return now - last_fetched >= poll_interval(spec, last_obs, now)
