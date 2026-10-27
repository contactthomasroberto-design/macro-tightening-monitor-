import datetime as dt

import pandas as pd
import pytest

from macro import archive


def _fc(point=2.0):
    return pd.DataFrame(
        {
            "model": ["COMB", "RW"],
            "target_date": ["2027-01-01", "2027-01-01"],
            "h": [3, 3],
            "point": [point, 2.5],
            "sigma": [0.5, 0.7],
        }
    )


def test_record_dedupes_and_quantiles(tmp_path):
    p = tmp_path / "a.csv"
    n = archive.record(
        _fc(), "inflation", "US headline", "US", "2026-10-01", "latest", dt.date(2026, 10, 27), p
    )
    assert n == 2
    assert (
        archive.record(
            _fc(9.9), "inflation", "US headline", "US", "2026-10-01", "latest", dt.date(2026, 10, 28), p
        )
        == 0
    )
    a = archive.read(p)
    assert a["point"].tolist() == [2.0, 2.5]  # never overwritten
    r = a.iloc[0]
    assert r["q05"] < r["q16"] < r["q50"] < r["q84"] < r["q95"]


def test_code_freeze_within_window(tmp_path, monkeypatch):
    p = tmp_path / "a.csv"
    archive.record(_fc(), "inflation", "US headline", "US", "2026-10-01", "latest", dt.date(2026, 10, 2), p)
    monkeypatch.setitem(archive.MODEL_VERSIONS, "inflation", "0.2.0")
    with pytest.raises(archive.FrozenModelError):
        archive.record(
            _fc(), "inflation", "US headline", "US", "2026-10-08", "latest", dt.date(2026, 10, 9), p
        )
    # next window is fine
    assert (
        archive.record(
            _fc(), "inflation", "US headline", "US", "2026-11-01", "latest", dt.date(2026, 11, 2), p
        )
        == 2
    )


def test_track_record(tmp_path):
    p = tmp_path / "a.csv"
    archive.record(_fc(), "inflation", "US headline", "US", "2026-10-01", "latest", dt.date(2026, 10, 2), p)
    rows, summ = archive.track_record(
        archive.read(p), {"US headline": pd.Series({pd.Timestamp("2027-01-01"): 2.2})}
    )
    comb = summ[summ["model"] == "COMB"].iloc[0]
    assert comb["n"] == 1 and comb["mae"] == pytest.approx(0.2) and comb["coverage_68"] == 1.0
