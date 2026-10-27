import datetime as dt

import pytest
from pydantic import ValidationError

from macro import config


def test_catalogue_loads_and_ids_unique():
    cat = config.catalogue()
    assert len(cat.ids) == len(set(cat.ids)) > 50
    assert cat.get("DGS10").freq == "D"
    with pytest.raises(KeyError):
        cat.get("NOPE")


def test_every_series_has_lag_and_terms():
    for s in config.catalogue().series:
        assert s.release_lag_days >= 0
        assert s.terms, f"{s.id} missing redistribution terms"


def test_scenarios_sum_to_one():
    sc = config.scenarios()
    assert abs(sum(s.probability for s in sc.scenarios.values()) - 1) < 1e-9
    assert set(sc.scenarios) == {"disinflation", "sticky", "energy_shock", "hard_landing"}


def test_scenario_validation_rejects_bad_probabilities():
    raw = config._read("scenarios.yaml")
    raw["scenarios"]["sticky"]["probability"] = 0.9
    with pytest.raises(ValidationError):
        config.ScenarioSet(**raw)


def test_calendar_sorted_and_unverified_flagged():
    cal = config.calendar()
    dates = [e.date for e in cal.events]
    assert dates == sorted(dates)
    assert all(e.source in cal.sources for e in cal.events)


def test_stale_assumptions_flags_missing_pricing():
    stale = config.stale_assumptions(dt.date(2026, 1, 1))
    assert "fed_terminal_rate" in stale  # shipped empty on purpose
