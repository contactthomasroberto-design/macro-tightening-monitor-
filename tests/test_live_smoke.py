"""Live smoke test (BRIEF §4): every catalogue id exists at its source, parses to numbers, and is
fresh. Skipped by default; run with `make test-live` (needs network; FRED_API_KEY optional).
Writes data/live_smoke.csv so stale or broken series can be documented and replaced."""

import datetime as dt

import pandas as pd
import pytest

from macro.config import ROOT, catalogue
from macro.data import sources
from macro.data.health import max_age_days

pytestmark = pytest.mark.live
RESULTS: list[dict] = []


@pytest.mark.parametrize("spec", catalogue().series, ids=lambda s: s.id)
def test_series_live(spec):
    row = {"id": spec.id, "source": spec.source, "source_id": spec.source_id, "ok": False}
    try:
        df = sources.fetch(spec)
        last = df["date"].max()
        if spec.freq in ("M", "Q"):
            last = last + (pd.offsets.MonthEnd(0) if spec.freq == "M" else pd.offsets.QuarterEnd(0))
        age = (pd.Timestamp(dt.date.today()) - last).days
        row |= {
            "answered_by": df.attrs.get("source", spec.source),
            "n": len(df),
            "last_obs": df["date"].max().date(),
            "age_days": age,
            "max_age_days": max_age_days(spec.freq, spec.release_lag_days),
        }
        assert len(df) > 10, "too few observations"
        assert df["value"].notna().all()
        assert age <= row["max_age_days"], f"stale: last obs {row['last_obs']} ({age} days)"
        row["ok"] = True
    except Exception as exc:  # recorded for the report, then re-raised
        row["error"] = f"{type(exc).__name__}: {exc}"
        if spec.optional:
            row["skipped"] = "optional series: models degrade gracefully without it"
            pytest.skip(f"optional series unavailable: {row['error']}")
        raise
    finally:
        RESULTS.append(row)
        out = ROOT / "data" / "live_smoke.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(RESULTS).to_csv(out, index=False)
