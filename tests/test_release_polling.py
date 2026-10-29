"""Release-aware polling, content hashes, release log and input-based result validation."""

import datetime as dt
import types

import pandas as pd

from macro.data import schedule
from macro.data.store import Store


def _spec(freq, lag, source="fred"):
    return types.SimpleNamespace(freq=freq, release_lag_days=lag, source=source)


def _utc(*a):
    return dt.datetime(*a, tzinfo=dt.UTC)


def test_monthly_series_is_polled_fast_only_around_its_expected_release():
    cpi = _spec("M", 15)
    last = pd.Timestamp("2026-09-01")  # September CPI in hand
    assert schedule.expected_next("M", last, 15) == pd.Timestamp("2026-11-15")  # end Oct + 15 days
    assert schedule.poll_interval(cpi, last, _utc(2026, 10, 20)) == dt.timedelta(days=3)  # too early
    assert schedule.poll_interval(cpi, last, _utc(2026, 11, 13)) == dt.timedelta(minutes=10)  # near
    assert schedule.poll_interval(cpi, last, _utc(2026, 11, 9)) == dt.timedelta(minutes=30)  # early window
    assert schedule.poll_interval(cpi, last, _utc(2027, 1, 5)) == dt.timedelta(days=3)  # long overdue
    fetched = _utc(2026, 11, 13, 12, 0)
    assert not schedule.due(cpi, last, fetched, _utc(2026, 11, 13, 12, 5))
    assert schedule.due(cpi, last, fetched, _utc(2026, 11, 13, 12, 11))


def test_daily_and_rate_limited_sources():
    last = pd.Timestamp("2026-10-23")  # a Friday
    assert schedule.expected_next("D", last, 1) == pd.Timestamp("2026-10-27")  # Monday + 1 day
    now = _utc(2026, 10, 27, 15)
    assert schedule.poll_interval(_spec("D", 1), last, now) == dt.timedelta(hours=1)
    assert schedule.poll_interval(_spec("D", 1, "yahoo"), last, now) == dt.timedelta(hours=2)
    assert schedule.due(_spec("D", 1), last, None)  # never fetched


def _frame(dates, values):
    return pd.DataFrame({"date": pd.to_datetime(dates), "value": values, "vintage_date": pd.NaT})


def test_content_hash_and_release_log(tmp_path):
    a, b = Store(tmp_path / "a.sqlite"), Store(tmp_path / "b.sqlite")
    a.write("CPI", _frame(["2026-08-01", "2026-09-01"], [1.0, float("nan")]), source="fred")
    b.write("CPI", _frame(["2026-08-01", "2026-09-01"], [1.0, float("nan")]), source="fred", fetched_at="x")
    assert a.content_hashes(["CPI"]) == b.content_hashes(["CPI"])  # same content, same hash anywhere
    h0 = a.content_hashes(["CPI"])["CPI"]
    a.write("CPI", _frame(["2026-08-01", "2026-09-01"], [1.1, float("nan")]), source="fred")  # revision
    assert a.content_hashes(["CPI"])["CPI"] != h0
    assert a.recent_releases(dt.datetime(2000, 1, 1, tzinfo=dt.UTC)).empty  # a revision is not a release
    a.write("CPI", _frame(["2026-08-01", "2026-09-01", "2026-10-01"], [1.1, 2.0, 3.0]), source="fred")
    rel = a.recent_releases(dt.datetime(2000, 1, 1, tzinfo=dt.UTC))
    assert rel["series_id"].tolist() == ["CPI"] and rel["obs_date"].tolist() == ["2026-10-01"]
    assert a.content_hashes(["NOPE"]) == {"NOPE": "missing"}
    assert a.latest_state()["CPI"][0] == "2026-10-01"


def test_results_are_invalidated_only_by_their_own_inputs(tmp_path, monkeypatch):
    from macro import data as data_mod
    from macro import results

    st = Store(tmp_path / "live.sqlite")
    st.write("CPIAUCSL", _frame(["2026-08-01"], [1.0]), source="fred")
    st.write("DGS10", _frame(["2026-08-01"], [4.0]), source="fred")
    monkeypatch.setattr(data_mod, "store", lambda: st)
    monkeypatch.setattr(data_mod, "is_demo", lambda: False)
    monkeypatch.setattr(data_mod, "refresh_series", lambda sid, s=None: (True, "ok"))
    monkeypatch.setattr(data_mod.Store, "is_fresh", lambda self, sid, freq, now=None: True)
    monkeypatch.setattr(results, "_dir", lambda: tmp_path)
    monkeypatch.setattr(results, "default_path", lambda: tmp_path / "live.sqlite")
    calls = {"infl": 0, "curve": 0}

    def infl():
        calls["infl"] += 1
        return float(data_mod.get_series("CPIAUCSL").iloc[-1])

    def curve():
        calls["curve"] += 1
        return float(data_mod.get_series("DGS10").iloc[-1])

    def outer():  # a bundle built on another bundle inherits its inputs
        return results.load_or_compute("inflation:US", infl) * 2

    assert results.load_or_compute("inflation:US", infl) == 1.0
    assert results.load_or_compute("curves:all", curve) == 4.0
    assert results.load_or_compute("views", outer) == 2.0
    st.write("CPIAUCSL", _frame(["2026-08-01", "2026-09-01"], [1.0, 2.0]), source="fred")  # CPI release
    assert results.load_or_compute("curves:all", curve) == 4.0 and calls["curve"] == 1  # untouched
    assert results.load_or_compute("inflation:US", infl) == 2.0 and calls["infl"] == 2  # recomputed
    assert results.load_or_compute("views", outer) == 4.0  # its CPI input changed too
    assert results.is_valid("views", tmp_path / "views.pkl")
