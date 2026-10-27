"""Data health: freshness, coverage and fetch status per series (dashboard 'Data health' page)."""

from __future__ import annotations

import datetime as dt

import pandas as pd

from macro.config import catalogue
from macro.data import demo
from macro.data.store import Store

# A series is 'stale' when its last observation is older than one period + release lag + slack.
PERIOD_DAYS = {"D": 1, "W": 7, "M": 31, "Q": 92}
SLACK_DAYS = {"D": 6, "W": 10, "M": 20, "Q": 45}


def max_age_days(freq: str, lag: int) -> int:
    return PERIOD_DAYS[freq] + lag + SLACK_DAYS[freq]


def reference_today() -> dt.date:
    """Today, or the fixed end of the synthetic sample in demo mode."""
    from macro.utils import is_demo

    return pd.Timestamp(demo.DEMO_END).date() if is_demo() else dt.date.today()


def health_table(st: Store, today: dt.date | None = None) -> pd.DataFrame:
    today = today or reference_today()
    rows = []
    for spec in catalogue().series:
        s = st.read(spec.id)
        fail = st.last_failure(spec.id)
        last_obs = s.index.max().date() if not s.empty else None
        # monthly/quarterly observations are dated at period start: age is measured from period end
        if last_obs is not None and spec.freq in ("M", "Q"):
            off = pd.offsets.MonthEnd(0) if spec.freq == "M" else pd.offsets.QuarterEnd(0)
            last_end = (pd.Timestamp(last_obs) + off).date()
        else:
            last_end = last_obs
        age = (today - last_end).days if last_end else None
        limit = max_age_days(spec.freq, spec.release_lag_days)
        if s.empty:
            status = "critical"
        elif fail is not None:
            status = "serious"
        elif age is not None and age > limit:
            status = "warning"
        else:
            status = "good"
        rows.append({
            "id": spec.id, "status": status, "region": spec.region, "category": spec.category, "freq": spec.freq,
            "source": spec.source, "first_obs": s.index.min().date() if not s.empty else None, "last_obs": last_obs,
            "age_days": age, "max_age_days": limit, "n_obs": len(s), "verify_flag": spec.verify,
            "last_fetch": st.last_fetched(spec.id), "last_error": fail[1] if fail else "", "terms": spec.terms,
        })
    return pd.DataFrame(rows)


def catalogue_markdown() -> str:
    """docs/data_catalogue.md, generated from config/series.yaml (single source of truth)."""
    lines = [
        "# Data catalogue",
        "",
        "Generated from `config/series.yaml` by `scripts/update_data.py --catalogue`. Do not edit by hand.",
        "",
        "Release lag = days between the end of the reference period and first publication (approximate).",
        "`verify` = ID, units or freshness to be confirmed by the live smoke test (`make test-live`).",
        "",
        "| id | region | freq | source | source id | units | lag (d) | verify | description | terms |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in catalogue().series:
        lines.append(
            f"| `{s.id}` | {s.region} | {s.freq} | {s.source} | `{s.source_id}` | {s.units} | {s.release_lag_days} | "
            f"{'yes' if s.verify else ''} | {s.description} | {s.terms} |"
        )
    return "\n".join(lines) + "\n"
