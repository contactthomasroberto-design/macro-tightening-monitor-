"""Record the strategy's figures and write the monthly factsheet (src/macro/strategy.py).

MACRO_MODE=live python scripts/strategy_record.py

Run by the refresh workflow: one row per day in archive/strategy_metrics.csv, and the current month's factsheet
in docs/factsheets/<YYYY-MM>.md (rewritten until the month ends, then frozen)."""

from __future__ import annotations

import pandas as pd

import _bootstrap  # noqa: F401
from macro import strategy as sg
from macro.config import ROOT
from macro.pipeline import portfolio_bundle
from macro.utils import is_demo


def main() -> int:
    b = portfolio_bundle()
    now = pd.Timestamp.now(tz="UTC")
    row = sg.metrics_row(b, now.date().isoformat())
    rv = sg.reviews()
    verdict = None
    if not rv.empty:
        last = rv.iloc[-1]
        verdict = f"Revue de stratégie du {last['date']} : {last['verdict']}"
    text = sg.factsheet(b, f"{now:%Y-%m}", verdict)
    if is_demo():
        print(row)
        print(text[:1500])
        return 0
    df = sg.record_metrics(row)
    sg.FACTSHEETS.mkdir(parents=True, exist_ok=True)
    out = sg.FACTSHEETS / f"{now:%Y-%m}.md"
    out.write_text(text, encoding="utf-8")
    print(f"{len(df)} days on record -> {sg.METRICS.relative_to(ROOT)}; factsheet -> {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
