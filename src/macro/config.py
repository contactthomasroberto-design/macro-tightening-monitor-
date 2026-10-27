"""Typed loaders for the YAML files in `config/`.

Validation happens at load time so a malformed catalogue or scenario file fails loudly
instead of silently feeding a model.
"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"

Freq = Literal["D", "W", "M", "Q"]
Source = Literal["fred", "ecb", "yahoo", "nyfed_files", "fed_board_files", "philly", "cftc"]


class SeriesSpec(BaseModel):
    id: str
    source: Source
    source_id: str
    freq: Freq
    units: str
    release_lag_days: int = Field(ge=0)
    region: Literal["US", "EA", "JP", "GLOBAL"]
    category: str
    description: str
    verify: bool = False
    terms: str = ""


class Catalogue(BaseModel):
    series: list[SeriesSpec]

    @model_validator(mode="after")
    def _unique_ids(self) -> Catalogue:
        ids = [s.id for s in self.series]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate series ids in series.yaml: {sorted(dupes)}")
        return self

    def get(self, series_id: str) -> SeriesSpec:
        for s in self.series:
            if s.id == series_id:
                return s
        raise KeyError(f"unknown series id {series_id!r}; add it to config/series.yaml")

    @property
    def ids(self) -> list[str]:
        return [s.id for s in self.series]


class Scenario(BaseModel):
    label: str
    probability: float = Field(ge=0, le=1)
    narrative: str
    oil_shock_pct: list[float]
    unemp_change_pp: list[float]
    infl_shock_pp: list[float]
    tp_change_bp: list[float]


class ScenarioSet(BaseModel):
    horizon_quarters: int
    scenarios: dict[str, Scenario]

    @model_validator(mode="after")
    def _check(self) -> ScenarioSet:
        total = sum(s.probability for s in self.scenarios.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"scenario probabilities must sum to 1, got {total:.4f}")
        for name, s in self.scenarios.items():
            for field in ("oil_shock_pct", "unemp_change_pp", "infl_shock_pp", "tp_change_bp"):
                if len(getattr(s, field)) != self.horizon_quarters:
                    raise ValueError(f"scenario {name}.{field} must have {self.horizon_quarters} values")
        return self


class CalendarEvent(BaseModel):
    date: dt.date
    kind: str
    label: str
    category: str
    source: str
    bank: str | None = None
    region: str | None = None
    retrieved: dt.date | None = None
    verified: bool = False


class Calendar(BaseModel):
    sources: dict[str, str]
    events: list[CalendarEvent]

    @field_validator("events")
    @classmethod
    def _sorted(cls, v: list[CalendarEvent]) -> list[CalendarEvent]:
        return sorted(v, key=lambda e: e.date)


def _read(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


@lru_cache(maxsize=1)
def catalogue() -> Catalogue:
    raw = _read("series.yaml")
    return Catalogue(series=raw["series"])


@lru_cache(maxsize=1)
def assumptions() -> dict:
    """Assumptions are kept as a plain dict: the dashboard edits them in place (copy first)."""
    return _read("assumptions.yaml")


def scenarios() -> ScenarioSet:
    return ScenarioSet(**_read("scenarios.yaml"))


def calendar() -> Calendar:
    return Calendar(**_read("calendar.yaml"))


def stale_assumptions(today: dt.date | None = None) -> list[str]:
    """Return keys of market-pricing assumptions that are missing or older than staleness_days."""
    today = today or dt.date.today()
    a = assumptions()
    limit = a.get("staleness_days", 30)
    out = []
    for key, entry in a.get("market_pricing", {}).items():
        as_of = entry.get("as_of")
        if entry.get("value") is None or as_of is None:
            out.append(key)
            continue
        as_of = as_of if isinstance(as_of, dt.date) else dt.date.fromisoformat(str(as_of))
        if (today - as_of).days > limit:
            out.append(key)
    return out
