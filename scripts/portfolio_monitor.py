"""Hourly risk check of the paper portfolio (GitHub Actions, market hours, Seoul open to NY close).

MACRO_MODE=live python scripts/portfolio_monitor.py           # print the status
MACRO_MODE=live python scripts/portfolio_monitor.py --issue   # also open an issue on a new breach

Reads the paper book (archive/portfolio_book.csv) and the daily prices of the warm-start snapshot,
appends the latest Yahoo quotes as today's prices, and checks the paper drawdown and the day's loss
against config/portfolio.yaml. An alert fires once when a threshold is crossed (state kept in
archive/portfolio_alerts.json), not on every run while it stays crossed. It never trades: the
rebalance itself is done once a day by the refresh workflow, from closing prices.

It also checks the daily prices for anomalies: a jump that the sector proxy does not share, or a
Yahoo close that Stooq does not confirm. New ones go to archive/price_anomalies.csv and, with
--issue, into one GitHub issue (state in archive/price_anomaly_alerts.json).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time

import pandas as pd

import _bootstrap  # noqa: F401
from macro import fund_checks as fc
from macro import portfolio as pf
from macro import portfolio_live as pl
from macro.config import ROOT, catalogue
from macro.data import sources
from macro.data.http import SourceError

STATE = ROOT / "archive" / "portfolio_alerts.json"
SNAPSHOT = ROOT / "snapshot" / "live" / "data.parquet"
ANOMALIES = ROOT / "archive" / "price_anomalies.csv"
ANOMALY_STATE = ROOT / "archive" / "price_anomaly_alerts.json"


def local_prices() -> pd.DataFrame:
    """Daily closes of the snapshot in each series' own currency (catalogue ids as columns)."""
    d = pd.read_parquet(SNAPSHOT)
    wide = d.pivot_table(index="date", columns="series_id", values="value", aggfunc="last")
    wide.index = pd.to_datetime(wide.index)
    return wide


def daily_prices(cfg: dict) -> pd.DataFrame:
    wide = local_prices()
    return pf.usd_prices(lambda i: wide.get(i), cfg)


def second_source(wide: pd.DataFrame, assets) -> tuple[dict, dict]:
    """Same-day closes from the snapshot (Yahoo) and from Stooq, for the US listings."""
    cat = catalogue()
    prim: dict = {}
    sec: dict = {}
    for a in assets:
        if a not in wide:
            continue
        try:
            sym = sources.stooq_symbol(cat.get(a).source_id)
        except KeyError:
            continue
        last = wide[a].dropna()
        if sym is None or last.empty:
            continue
        prim[a] = (last.index[-1], float(last.iloc[-1]))
        try:
            st = sources.stooq_daily(sym)
        except SourceError as exc:
            print(f"Stooq unavailable for {a}: {exc}")
            if "network error" in str(exc) or "HTTP 4" in str(exc):
                break  # the source is down or refuses us: do not ask again for every line
            continue
        if prim[a][0] in st.index:
            sec[a] = (prim[a][0], float(st.loc[prim[a][0]]))
        time.sleep(0.5)
    return prim, sec


def check_prices(cfg: dict, issue: bool) -> pd.DataFrame:
    """Jumps without a matching sector move and Yahoo/Stooq disagreements. New ones are archived
    and, with --issue, reported once in a GitHub issue. Information only: nothing is traded."""
    an = cfg.get("anomalies", {})
    wide = local_prices()
    uni = [a for a in cfg["universe"] if a in wide]
    cols = sorted(set(uni) | {p for p in an.get("proxy", {}).values() if p in wide})
    jumps = fc.price_jumps(
        wide[cols].iloc[-400:], an.get("proxy", {}), an.get("jump_sd", 6.0), proxy_k=an.get("proxy_sd", 3.0)
    )
    jumps = jumps[jumps["asset"].isin(uni)]
    prim, sec = second_source(wide, uni)
    mism = fc.source_mismatches(prim, sec, an.get("source_tol", 0.02))
    print(
        f"price check: {len(jumps)} jumps, {len(mism)} source mismatches, {len(sec)} lines confirmed on Stooq"
    )
    new = fc.append_anomalies(pd.concat([jumps, mism], ignore_index=True), ANOMALIES)
    if new.empty:
        return new
    print(new[["date", "asset", "kind", "detail"]].to_string(index=False))
    prev = json.loads(ANOMALY_STATE.read_text()) if ANOMALY_STATE.exists() else {"seen": []}
    keys = [f"{d}|{a}|{k}" for d, a, k in zip(new["date"], new["asset"], new["kind"], strict=False)]
    fresh = [k for k in keys if k not in prev["seen"]]
    if fresh and issue:
        body = "\n".join(
            f"- **{a}** ({d}, {k}): {t}"
            for d, a, k, t in zip(new["date"], new["asset"], new["kind"], new["detail"], strict=False)
        )
        body += (
            "\n\nA jump is a daily move beyond the configured number of trailing standard deviations that its "
            "sector proxy did not share; a mismatch is a same-day close that differs between Yahoo and Stooq. "
            "Check the data before the next rebalance (archive/price_anomalies.csv). No position is changed."
        )
        title = f"Price anomaly: {', '.join(sorted(set(new['asset'])))}"
        subprocess.run(["gh", "issue", "create", "--title", title, "--body", body], check=False)
    if fresh:
        ANOMALY_STATE.parent.mkdir(exist_ok=True)
        ANOMALY_STATE.write_text(json.dumps({"seen": (prev["seen"] + fresh)[-500:]}))
    return new


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
    if SNAPSHOT.exists():
        check_prices(cfg, args.issue)
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
