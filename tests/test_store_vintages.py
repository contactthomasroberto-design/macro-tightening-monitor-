import datetime as dt

import pandas as pd

from macro.data.store import Store
from macro.data.vintages import truncate_as_of


def _df(dates, values, vintage=None):
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates),
            "value": values,
            "vintage_date": pd.Timestamp(vintage) if vintage else pd.NaT,
        }
    )


def test_latest_snapshot_replaced(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    st.write("X", _df(["2020-01-01", "2020-02-01"], [1.0, 2.0]), "fred")
    st.write("X", _df(["2020-01-01"], [5.0]), "fred")
    s = st.read("X")
    assert s.tolist() == [5.0]


def test_vintage_read_takes_latest_vintage_before_date(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    st.write("GDP", _df(["2020-01-01"], [100.0], "2020-04-30"), "alfred")
    st.write("GDP", _df(["2020-01-01", "2020-04-01"], [101.0, 102.0], "2020-07-30"), "alfred")
    assert st.read("GDP", vintage="2020-05-15").tolist() == [100.0]
    assert st.read("GDP", vintage="2020-08-01").tolist() == [101.0, 102.0]
    assert st.vintages("GDP") == ["2020-04-30", "2020-07-30"]
    assert st.read("GDP").empty  # no latest-vintage snapshot written


def test_ttl_and_fetch_log(tmp_path):
    st = Store(tmp_path / "t.sqlite")
    assert not st.is_fresh("X", "D")
    st.write("X", _df(["2020-01-01"], [1.0]), "fred")
    assert st.is_fresh("X", "D")
    later = dt.datetime.now(dt.UTC) + dt.timedelta(days=1)
    assert not st.is_fresh("X", "D", now=later)
    assert st.is_fresh("X", "Q", now=later)
    st.log_fetch("X", False, "HTTP 503")
    assert st.last_failure("X")[1] == "HTTP 503"
    st.log_fetch("X", True, "ok")
    assert st.last_failure("X") is None


def test_truncate_as_of_respects_release_lag():
    s = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]))
    # monthly, 15-day lag: Feb data (period end Feb 29) public from Mar 15
    out = truncate_as_of(s, "2024-03-14", freq="M", lag_days=15)
    assert out.index.max() == pd.Timestamp("2024-01-01")
    out = truncate_as_of(s, "2024-03-15", freq="M", lag_days=15)
    assert out.index.max() == pd.Timestamp("2024-02-01")


def test_truncate_uses_catalogue_lag():
    s = pd.Series([1.0, 2.0], index=pd.to_datetime(["2024-01-01", "2024-02-01"]))
    lag = 15  # CPIAUCSL in series.yaml
    out = truncate_as_of(s, pd.Timestamp("2024-02-29") + pd.Timedelta(days=lag - 1), series_id="CPIAUCSL")
    assert len(out) == 1


def test_data_version_moves_only_when_content_changes(tmp_path):
    st = Store(tmp_path / "v.sqlite")
    assert st.data_version() == 0
    df = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-01", "2024-02-01"]), "value": [1.0, 2.0], "vintage_date": pd.NaT}
    )
    st.write("X", df, source="fred")
    v1 = st.data_version()
    assert v1 == 1
    st.write("X", df, source="fred", fetched_at="2030-01-01T00:00:00")  # re-check, same numbers
    assert st.data_version() == v1
    assert st.last_fetched("X").year == 2030  # the re-check is still recorded
    df2 = pd.concat(
        [df, pd.DataFrame({"date": [pd.Timestamp("2024-03-01")], "value": [3.0], "vintage_date": pd.NaT})]
    )
    st.write("X", df2, source="fred")
    assert st.data_version() == v1 + 1
    st.write("X", df2.assign(value=[1.0, 2.5, 3.0]), source="fred")  # revision
    assert st.data_version() == v1 + 2
    assert st.read("X").tolist() == [1.0, 2.5, 3.0]


def test_autorefresh_skips_fresh_series_and_reports(tmp_path, monkeypatch):
    from macro import autorefresh
    from macro import data as data_mod

    st = Store(tmp_path / "a.sqlite")
    monkeypatch.setattr(data_mod, "store", lambda: st)
    monkeypatch.setattr(autorefresh, "STATUS_PATH", tmp_path / "status.json")
    monkeypatch.setattr(autorefresh, "is_demo", lambda: False)
    calls = []

    def fake_refresh(sid, st_=None):
        calls.append(sid)
        df = pd.DataFrame({"date": pd.to_datetime(["2024-01-01"]), "value": [1.0], "vintage_date": pd.NaT})
        st.write(sid, df, source="test")
        return (sid != "DGS10", "ok" if sid != "DGS10" else "HTTP 500")

    monkeypatch.setattr(data_mod, "refresh_series", fake_refresh)
    out = autorefresh.refresh_and_warm(warm=False, light=False)
    assert out["checked"] == len(calls) > 50
    assert out["failed"] == {"DGS10": "HTTP 500"} and out["data_changed"]
    calls.clear()
    out2 = autorefresh.refresh_and_warm(warm=False, light=False)  # everything fresh now: nothing fetched
    assert calls == [] and out2["checked"] == 0 and not out2["data_changed"]
    assert autorefresh.read_status()["finished"]


def test_autorefresh_is_off_in_demo(monkeypatch):
    from macro import autorefresh

    monkeypatch.setattr(autorefresh, "is_demo", lambda: True)
    assert autorefresh.refresh_and_warm() == {"skipped": "demo mode"}
    assert autorefresh.start_background() is None


def test_failed_fetch_is_not_retried_for_an_hour(tmp_path, monkeypatch):
    from macro import data as data_mod

    st = Store(tmp_path / "n.sqlite")
    df = pd.DataFrame({"date": pd.to_datetime(["2024-01-01"]), "value": [1.0], "vintage_date": pd.NaT})
    st.write("SX5E", df, source="yahoo", fetched_at="2000-01-01T00:00:00")  # expired copy
    st.log_fetch("SX5E", False, "HTTP 429")
    assert st.failed_recently("SX5E", dt.timedelta(hours=1))
    assert not st.failed_recently(
        "SX5E", dt.timedelta(hours=1), now=dt.datetime.now(dt.UTC) + dt.timedelta(hours=2)
    )
    calls = []
    monkeypatch.setattr(data_mod, "store", lambda: st)
    monkeypatch.setattr(data_mod, "is_demo", lambda: False)
    monkeypatch.setattr(data_mod, "refresh_series", lambda sid, s=None: calls.append(sid) or (False, "429"))
    s = data_mod.get_series("SX5E")
    assert calls == [] and s.tolist() == [1.0] and s.attrs["stale"]
    data_mod.get_series("SX5E", refresh=True)  # an explicit refresh still asks the source
    assert calls == ["SX5E"]


def test_load_or_compute_runs_once_under_concurrency(tmp_path, monkeypatch):
    import threading
    import time

    from macro import results

    monkeypatch.setattr(results, "_dir", lambda: tmp_path)
    monkeypatch.setattr(results, "_fingerprint", lambda name: "fp")
    n = []

    def slow():
        n.append(1)
        time.sleep(0.3)
        return 42

    ts = [threading.Thread(target=lambda: results.load_or_compute("x:y", slow)) for _ in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(n) == 1 and results.load_or_compute("x:y", slow) == 42
