import numpy as np
import pandas as pd
import pytest

import macro.data as data
from macro.config import catalogue
from macro.data import demo
from macro.data.http import SourceError


@pytest.fixture
def live_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MACRO_MODE", "live")
    monkeypatch.setenv("MACRO_DB", str(tmp_path / "live.sqlite"))
    data._stores.clear()
    yield
    data._stores.clear()


def _ok_frame():
    return pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-02", "2024-01-03"]), "value": [4.0, 4.1], "vintage_date": pd.NaT}
    )


def test_live_fetch_then_cache(live_db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        data.sources, "fetch", lambda spec, vintage=None: calls.append(spec.id) or _ok_frame()
    )
    s = data.get_series("DGS10")
    assert s.attrs["stale"] is False and s.attrs["source"] == "fred"
    data.get_series("DGS10")  # fresh: no second call
    assert calls == ["DGS10"]


def test_live_degrades_to_cache_on_failure(live_db, monkeypatch):
    monkeypatch.setattr(data.sources, "fetch", lambda spec, vintage=None: _ok_frame())
    data.get_series("DGS10")

    def boom(spec, vintage=None):
        raise SourceError("HTTP 503")

    monkeypatch.setattr(data.sources, "fetch", boom)
    s = data.get_series("DGS10", refresh=True)
    assert s.attrs["stale"] is True
    assert s.tolist() == [4.0, 4.1]
    assert data.store().last_failure("DGS10")[1].endswith("HTTP 503")


def test_live_no_cache_raises(live_db, monkeypatch):
    def boom(spec, vintage=None):
        raise SourceError("down")

    monkeypatch.setattr(data.sources, "fetch", boom)
    with pytest.raises(data.DataUnavailable):
        data.get_series("DGS2")
    assert data.try_series("DGS2") is None


def test_demo_covers_catalogue_and_is_deterministic():
    a = demo.generate()
    assert set(a) == set(catalogue().ids)
    demo.generate.cache_clear()
    b = demo.generate()
    for k in ("DGS10", "CPIAUCSL", "TFF_ES_LEV"):
        pd.testing.assert_series_equal(a[k], b[k])


def test_demo_identities_and_coherence():
    d = demo.generate()
    pd.testing.assert_series_equal(d["T10Y2Y"], d["DGS10"] - d["DGS2"], check_names=False)
    pd.testing.assert_series_equal(d["DFII10"], d["DGS10"] - d["T10YIE"], check_names=False)
    steps = d["DFEDTARU"].diff().dropna()
    steps = steps[steps != 0]
    assert np.allclose((steps * 4).round(), steps * 4)  # 25bp steps
    core = 100 * (d["CPILFESL"] / d["CPILFESL"].shift(12) - 1)
    pol = d["DFEDTARU"].resample("MS").last()
    assert core.corr(pol) > 0.3  # rule-based policy responds to inflation
    assert 0.03 < d["USREC"].mean() < 0.3
    assert (
        d["T10Y3M"].resample("MS").mean().shift(12).corr(d["USREC"]) < 0
    )  # inverted curve precedes recessions


def test_demo_get_series_has_provenance():
    s = data.get_series("DGS10")
    assert s.attrs["mode"] == "demo" and "synthetic" in s.attrs["source"]
    t = data.get_series("CPIAUCSL", as_of="2020-03-14")
    assert t.index.max() == pd.Timestamp("2020-01-01")
