"""Warm start: snapshot export and application to an empty or an already populated cache."""

import pickle

import pandas as pd
import pytest

from macro import warmstart
from macro.data.store import Store
from macro.results import code_hash


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
    monkeypatch.setattr(warmstart, "_marker", lambda: tmp_path / "marker.json")
    monkeypatch.setattr(warmstart, "mode", lambda: "live")
    return st, res, gmd


def _frame(values):
    return pd.DataFrame(
        {"date": pd.to_datetime(["2024-01-01", "2024-02-01"]), "value": values, "vintage_date": pd.NaT}
    )


def _snapshot(tmp_path, st, res, gmd):
    st.write("DGS10", _frame([1.0, 2.0]), source="fred", fetched_at="2026-10-28T05:20:00")
    st.write("UNRATE", _frame([4.0, 4.1]), source="fred", fetched_at="2026-10-28T05:21:00")
    (res / "policy__fed.pkl").write_bytes(pickle.dumps(("fp-snap", {"x": "snapshot"}, {"code": code_hash()})))
    pd.DataFrame({"ISO3": ["USA"], "year": [2020]}).to_parquet(gmd / "GMD_2026_09.parquet")
    st.set_data_version(50)  # distinctive, so tests can tell whether it was adopted
    snap = tmp_path / "snap"
    return snap, warmstart.export(snap)


def _new_container(tmp_path, monkeypatch, name):
    from macro import data as data_mod

    st = Store(tmp_path / f"{name}.sqlite")
    res, gmd = tmp_path / f"{name}_r", tmp_path / f"{name}_g"
    res.mkdir()
    monkeypatch.setattr(data_mod, "store", lambda: st)
    monkeypatch.setattr(warmstart, "_results_dir", lambda: res)
    monkeypatch.setattr(warmstart, "_gmd_dir", lambda: gmd)
    monkeypatch.setattr(warmstart, "_marker", lambda: tmp_path / f"{name}_marker.json")
    return st, res, gmd


def test_snapshot_applied_to_an_empty_container(tmp_path, live_env, monkeypatch):
    snap, man = _snapshot(tmp_path, *live_env)
    assert man["series"] == 2 and man["results"] == 1 and man["gmd_version"] == "2026_09"
    st2, res2, gmd2 = _new_container(tmp_path, monkeypatch, "fresh")
    out = warmstart.apply_snapshot(snap)
    assert out["applied"] and len(out["parts"]) == 3
    assert st2.read("UNRATE").tolist() == [4.0, 4.1]
    assert st2.data_version() == man["data_version"]  # results fingerprints match the snapshot
    assert st2.last_fetched("DGS10").hour == 5  # TTLs count from the snapshot's fetch time
    assert (res2 / "policy__fed.pkl").exists() and (gmd2 / "GMD_2026_09.parquet").exists()
    assert warmstart.apply_snapshot(snap)["reason"] == "already applied"  # cheap on every app run


def test_snapshot_replaces_outdated_results_but_keeps_current_ones_and_newer_data(
    tmp_path, live_env, monkeypatch
):
    snap, man = _snapshot(tmp_path, *live_env)
    st2, res2, _ = _new_container(tmp_path, monkeypatch, "running")
    # a running process: older-code result, current-code result, and a series fetched after the snapshot
    (res2 / "policy__fed.pkl").write_bytes(pickle.dumps(("fp-old", {"x": "old code"}, {"code": "older"})))
    st2.write("UNRATE", _frame([9.0, 9.1]), source="fred", fetched_at="2026-10-28T09:00:00")
    out = warmstart.apply_snapshot(snap)
    assert out["applied"]
    assert pickle.loads((res2 / "policy__fed.pkl").read_bytes())[1] == {"x": "snapshot"}  # outdated replaced
    assert st2.read("UNRATE").tolist() == [9.0, 9.1]  # newer local data kept
    assert st2.read("DGS10").tolist() == [1.0, 2.0]  # missing series added
    assert st2.data_version() != man["data_version"]  # local data differs: results served stale, refreshed

    (res2 / "policy__fed.pkl").write_bytes(pickle.dumps(("fp-cur", {"x": "current"}, {"code": code_hash()})))
    (tmp_path / "running_marker.json").unlink()
    warmstart.apply_snapshot(snap)
    assert pickle.loads((res2 / "policy__fed.pkl").read_bytes())[1] == {"x": "current"}  # current kept


def test_apply_never_raises_on_a_bad_snapshot(tmp_path, live_env):
    snap = tmp_path / "bad"
    snap.mkdir()
    (snap / "manifest.json").write_text("{not json")
    assert warmstart.apply_snapshot(snap)["applied"] is False
