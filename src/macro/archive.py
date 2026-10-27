"""Forecast archive and track record (BRIEF §2.5, GDPNow-style).

Every scheduled run appends its forecasts with the data vintage to `archive/forecasts.csv`
(live mode; committed, small). Demo runs go to the ignored demo cache so synthetic numbers never
enter the public archive. Rows are never overwritten: a (data_as_of, model, variable,
target_date) key already present is skipped.

Code freeze: a model's version cannot change inside a calendar-month window that already holds
archived rows from another version of that model (raise `FrozenModelError`).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from macro.config import ROOT
from macro.utils import git_hash, is_demo, mode
from macro.versions import MODEL_VERSIONS

COLUMNS = [
    "run_date",
    "mode",
    "git_hash",
    "data_as_of",
    "module",
    "model",
    "model_version",
    "region",
    "variable",
    "target_date",
    "horizon",
    "point",
    "sigma",
    "q05",
    "q16",
    "q50",
    "q84",
    "q95",
    "vintage_label",
]
KEY = ["data_as_of", "model", "variable", "target_date"]
QUANTS = {"q05": 0.05, "q16": 0.16, "q50": 0.50, "q84": 0.84, "q95": 0.95}


class FrozenModelError(RuntimeError):
    pass


def archive_path() -> Path:
    if is_demo():
        return ROOT / "data" / "cache" / "forecasts_demo.csv"
    return ROOT / "archive" / "forecasts.csv"


def read(path: Path | None = None) -> pd.DataFrame:
    path = path or archive_path()
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, parse_dates=["run_date", "data_as_of", "target_date"])
    return df


def _window(d) -> str:
    return pd.Timestamp(d).strftime("%Y-%m")


def check_freeze(existing: pd.DataFrame, module: str, version: str, run_date: dt.date) -> None:
    if existing.empty:
        return
    w = _window(run_date)
    same = existing[(existing["module"] == module) & (existing["run_date"].dt.strftime("%Y-%m") == w)]
    other = set(same["model_version"].astype(str)) - {version}
    if other:
        raise FrozenModelError(
            f"{module} v{version} cannot archive in window {w}: rows from v{sorted(other)} already exist. "
            "Model changes take effect in the next window (see docs/MODEL_CHANGELOG.md)."
        )


def record(
    forecasts: pd.DataFrame,
    module: str,
    variable: str,
    region: str,
    data_as_of,
    vintage_label: str,
    run_date: dt.date | None = None,
    path: Path | None = None,
) -> int:
    """Append forecasts (columns: model, target_date, h, point, sigma). Returns rows written."""
    path = path or archive_path()
    run_date = run_date or dt.date.today()
    version = MODEL_VERSIONS[module]
    existing = read(path)
    check_freeze(existing, module, version, run_date)
    f = forecasts.copy()
    out = pd.DataFrame(
        {
            "run_date": pd.Timestamp(run_date),
            "mode": mode(),
            "git_hash": git_hash(),
            "data_as_of": pd.Timestamp(data_as_of),
            "module": module,
            "model": f["model"].to_numpy(),
            "model_version": version,
            "region": region,
            "variable": variable,
            "target_date": pd.to_datetime(f["target_date"]).to_numpy(),
            "horizon": f["h"].to_numpy(),
            "point": f["point"].to_numpy(),
            "sigma": f["sigma"].to_numpy(),
            "vintage_label": vintage_label,
        }
    )
    for k, q in QUANTS.items():
        out[k] = out["point"] + stats.norm.ppf(q) * out["sigma"]
    out = out[COLUMNS]
    if not existing.empty:
        keys = set(map(tuple, existing[KEY].astype(str).to_numpy()))
        mask = [tuple(r) not in keys for r in out[KEY].astype(str).to_numpy()]
        out = out[mask]
    if out.empty:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    header = not path.exists() or path.stat().st_size == 0
    out.to_csv(path, mode="a", header=header, index=False, float_format="%.4f", date_format="%Y-%m-%d")
    return len(out)


def track_record(archive: pd.DataFrame, outcomes: dict[str, pd.Series]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Join archived forecasts with later outcomes.

    outcomes: {variable: realised series (latest vintage) indexed by target date}.
    Returns (rows with error and band coverage, summary by variable/model/horizon).
    """
    if archive.empty:
        return archive.assign(actual=np.nan, error=np.nan), pd.DataFrame()
    a = archive.copy()
    a["actual"] = [
        outcomes.get(v, pd.Series(dtype=float)).get(pd.Timestamp(d), np.nan)
        for v, d in zip(a["variable"], a["target_date"], strict=True)
    ]
    a["error"] = a["actual"] - a["point"]
    a["in_68"] = (a["actual"] >= a["q16"]) & (a["actual"] <= a["q84"])
    a["in_90"] = (a["actual"] >= a["q05"]) & (a["actual"] <= a["q95"])
    done = a.dropna(subset=["actual"])
    if done.empty:
        return a, pd.DataFrame()
    summ = (
        done.groupby(["variable", "model", "horizon"])
        .agg(
            n=("error", "size"),
            mae=("error", lambda e: float(np.mean(np.abs(e)))),
            rmse=("error", lambda e: float(np.sqrt(np.mean(e**2)))),
            bias=("error", "mean"),
            coverage_68=("in_68", "mean"),
            coverage_90=("in_90", "mean"),
        )
        .reset_index()
    )
    return a, summ
