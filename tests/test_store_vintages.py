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
