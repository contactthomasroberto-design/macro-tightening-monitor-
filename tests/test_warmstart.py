"""Warm start: snapshot export/restore round trip and stale-while-revalidate result serving."""

import pickle

import pandas as pd
import pytest

from macro import warmstart
from macro.data.store import Store


@pytest.fixture
def live_env(tmp_path, monkeypatch):
    from macro import data as data_mod

    st = Store(tmp_path / "live.sqlite")
    res = tmp_path / "results"
    res.mkdir()
    gmd = tmp_path / "gmd"
    gmd.mkdir()
    monkeypatch.setattr(data_mod, "store", lambda: st)
    monkeypatch.setattr(warmstart, "_results_dir", lambda: res)
    monkeypatch.setattr(warmstart, "_gmd_dir", lambda: gmd)
    monkeypatch.setattr(warmstart, "mode", lambda: "live")
    return st, res, gmd


def test_snapshot_round_trip(tmp_path, live_env, monkeypatch):
    st, res, gmd = live_env
    df = pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-01", "2024-02-01"]), "value": [1.0, 2.0], "vintage_date": pd.NaT}
    )
    st.write("DGS10", df, source="fred", fetched_at="2026-10-28T05:20:00")
    st.write("UNRATE", df.assign(value=[4.0, 4.1]), source="fred", fetched_at="2026-10-28T05:21:00")
    (res / "policy__fed.pkl").write_bytes(pickle.dumps(("fp", {"x": 1}, {})))
    pd.DataFrame({"ISO3": ["USA"], "year": [2020]}).to_parquet(gmd / "GMD_2026_09.parquet")
    snap = tmp_path / "snap"
    man = warmstart.export(snap)
    assert man["series"] == 2 and man["results"] == 1 and man["gmd_version"] == "2026_09"

    # a fresh container: empty store, no results, no GMD cache
    st2 = Store(tmp_path / "fresh.sqlite")
    res2, gmd2 = tmp_path / "r2", tmp_path / "g2"
    from macro import data as data_mod

    monkeypatch.setattr(data_mod, "store", lambda: st2)
    monkeypatch.setattr(warmstart, "_results_dir", lambda: res2)
    monkeypatch.setattr(warmstart, "_gmd_dir", lambda: gmd2)
    out = warmstart.restore_if_empty(snap)
    assert out["restored"] and set(out["parts"]) == {"data", "results", "gmd"}
    assert st2.read("UNRATE").tolist() == [4.0, 4.1]
    assert st2.data_version() == man["data_version"]  # results fingerprints match the snapshot
    assert st2.last_fetched("DGS10").hour == 5  # TTLs count from the snapshot's fetch time
    assert (res2 / "policy__fed.pkl").exists() and (gmd2 / "GMD_2026_09.parquet").exists()
    assert warmstart.restore_if_empty(snap)["parts"] == []  # nothing missing the second time


def test_restore_never_raises_on_a_bad_snapshot(tmp_path, live_env):
    snap = tmp_path / "bad"
    snap.mkdir()
    (snap / "manifest.json").write_text("{not json")
    assert warmstart.restore_if_empty(snap)["restored"] is False
