import json

import numpy as np
import pandas as pd

from macro import strategy as sg


def test_record_metrics_one_row_per_day(tmp_path):
    p = tmp_path / "m.csv"
    row = {c: np.nan for c in sg.METRIC_COLUMNS} | {"date": "2026-11-17", "version": "0.3.1", "Sharpe": 0.7}
    sg.record_metrics(row, p)
    sg.record_metrics(row | {"Sharpe": 0.8}, p)
    sg.record_metrics(row | {"date": "2026-11-18"}, p)
    df = sg.read_metrics(p)
    assert list(df["date"]) == ["2026-11-17", "2026-11-18"] and df["Sharpe"].iloc[0] == 0.8


def test_hypotheses_keep_history(tmp_path):
    for d, v in (("2026-11-17", {"H39": "True", "H41": False}), ("2026-11-21", {"H39": False, "H48": True})):
        (tmp_path / f"{d}.json").write_text(json.dumps({"date": d, "verdicts": v}))
    h = sg.hypotheses(tmp_path).set_index("hypothesis")
    assert h.loc["H39", "verdict"] == "rejetée" and h.loc["H39", "history"] == "validée → rejetée"
    assert list(h.index) == ["H39", "H41", "H48"]


def test_reviews_and_versions(tmp_path):
    (tmp_path / "2026-11-17.md").write_text(
        "# Revue\n\n**À surveiller** : protège le capital, alpha non prouvé.\n"
    )
    r = sg.reviews(tmp_path)
    assert r.iloc[0]["verdict"].startswith("À surveiller")
    v = sg.versions()
    assert {"portfolio", "backtest"} <= set(v["model"])


def test_factsheet_renders_on_demo_bundle():
    from macro.pipeline import portfolio_bundle

    text = sg.factsheet(portfolio_bundle(), "2026-11", "Revue : à surveiller.")
    assert "## Chiffres clés" in text and "Avis du comité" in text and "Sharpe" in text
    assert pd.notna(sg.metrics_row(portfolio_bundle(), "2026-11-17")["Sharpe"])
