"""Hourly risk check of the paper portfolio (GitHub Actions, market hours, Seoul open to NY close).

MACRO_MODE=live python scripts/portfolio_monitor.py           # print the status
MACRO_MODE=live python scripts/portfolio_monitor.py --issue   # also open an issue on a new breach

Reads the paper book (archive/portfolio_book.csv) and the daily prices of the warm-start snapshot,
appends the latest Yahoo quotes as today's prices, and checks the paper drawdown and the day's loss
against config/portfolio.yaml. An alert fires once when a threshold is crossed (state kept in
archive/portfolio_alerts.json), not on every run while it stays crossed. It never trades: the
rebalance itself is done once a day by the refresh workflow, from closing prices.
"""

from __future__ import annotations

import argparse
import json
import subprocess

import pandas as pd

import _bootstrap  # noqa: F401
from macro import portfolio as pf
from macro import portfolio_live as pl
from macro.config import ROOT, catalogue
from macro.data import sources
from macro.data.http import SourceError

STATE = ROOT / "archive" / "portfolio_alerts.json"
SNAPSHOT = ROOT / "snapshot" / "live" / "data.parquet"


def daily_prices(cfg: dict) -> pd.DataFrame:
    d = pd.read_parquet(SNAPSHOT)
    wide = d.pivot_table(index="date", columns="series_id", values="value", aggfunc="last")
    wide.index = pd.to_datetime(wide.index)
    return pf.usd_prices(lambda i: wide.get(i), cfg)


def quotes(assets, cfg: dict) -> dict[str, float]:
    cat = catalogue()
    out: dict[str, float] = {}
    fx_cache: dict[str, float] = {}
    for a in assets:
        try:
            p, _ = sources.yahoo_quote(cat.get(a).source_id)
            fx_id = cfg.get("fx", {}).get(a)
            if fx_id:
                if fx_id not in fx_cache:
                    fx_cache[fx_id] = sources.yahoo_quote(cat.get(fx_id).source_id)[0]
                p /= fx_cache[fx_id]
            out[a] = p
        except (SourceError, KeyError) as exc:
            print(f"no quote for {a}: {exc}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", action="store_true")
    args = ap.parse_args()
    cfg = pf.load_config()
    book = pl.read_book()
    if book.empty:
        print("no paper book yet (first rebalance on", cfg["live"]["start"], ")")
        return 0
    px = daily_prices(cfg)
    held = book.loc[book["date"] == book["date"].max(), "asset"].tolist()
    st = pl.monitor(book, px, quotes(held, cfg), cfg)
    print(json.dumps(st, indent=2, default=str))
    prev = json.loads(STATE.read_text()) if STATE.exists() else {"breaches": []}
    new = [b.split(" ")[0] for b in st.get("breaches", [])]
    fresh = [b for b in st.get("breaches", []) if b.split(" ")[0] not in prev["breaches"]]
    if fresh and args.issue:
        title = "Portfolio alert: " + "; ".join(fresh)
        body = (
            f"Paper NAV {st['nav']:.4f}, drawdown {st['drawdown']:.1%}, today {st['day']:+.1%}.\n\n"
            f"Worst movers today: {', '.join(f'{k} {v:+.1%}' for k, v in st['worst movers'].items())}.\n\n"
            "The drawdown overlay acts at the next daily rebalance (config/portfolio.yaml). "
            "Model portfolio on paper: no order is placed."
        )
        subprocess.run(["gh", "issue", "create", "--title", title, "--body", body], check=False)
    if new != prev["breaches"]:
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps({"breaches": new, "checked": pd.Timestamp.now(tz="UTC").isoformat()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
