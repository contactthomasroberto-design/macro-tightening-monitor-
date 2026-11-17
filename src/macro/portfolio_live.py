"""Paper book of the systematic portfolio: archived targets, paper NAV, trades, data gate.

The book (archive/portfolio_book.csv) is append-only: one row per asset at each paper rebalance,
written by the refresh workflow, never edited. The paper NAV is recomputed from the book and
prices, so it cannot be flattered after the fact."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from macro.config import ROOT

BOOK = ROOT / "archive" / "portfolio_book.csv"
COLUMNS = ["date", "asset", "weight", "status", "overlay", "reason", "version"]


def read_book(path: Path = BOOK) -> pd.DataFrame:
    if not Path(path).exists():
        return pd.DataFrame(columns=COLUMNS)
    df = pd.read_csv(path, parse_dates=["date"])
    return df[COLUMNS]


def holdings_at(book: pd.DataFrame) -> pd.DataFrame:
    """Weights by rebalance date (rows) and asset (columns)."""
    if book.empty:
        return pd.DataFrame()
    return book.pivot_table(index="date", columns="asset", values="weight", aggfunc="last").fillna(0.0)


def paper_nav(book: pd.DataFrame, px: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Daily paper NAV (start = 1) and the drifted weights at the last date. Prices are carried
    forward over holidays of one market (Seoul and New York do not close on the same days)."""
    h = holdings_at(book)
    if h.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    p = px.reindex(columns=h.columns).ffill()
    p = p.loc[h.index[0] :]
    rets = p.pct_change(fill_method=None).fillna(0.0)
    nav, out = 1.0, {}
    w = h.iloc[0][h.iloc[0] != 0]  # p starts at the first rebalance date
    for d in p.index:
        if d in h.index:
            w = h.loc[d]
            w = w[w != 0]
            out[d] = nav
            continue
        rn = rets.loc[d, w.index]
        g = float((w * rn).sum())
        w = w * (1 + rn) / (1 + g)
        nav *= 1 + g
        out[d] = nav
    return pd.Series(out), w


def stale_assets(px: pd.DataFrame, assets, today: pd.Timestamp, max_days: int) -> list[str]:
    """Assets whose last price is more than `max_days` business days old."""
    out = []
    for a in assets:
        s = px[a].dropna() if a in px else pd.Series(dtype=float)
        if s.empty or np.busday_count(s.index[-1].date(), today.date()) > max_days:
            out.append(a)
    return out


def rebalance_due(book: pd.DataFrame, today: pd.Timestamp, overlay: int, cfg: dict) -> str | None:
    """Why the paper book should rebalance today, or None."""
    live = cfg["live"]
    if not live.get("trading_enabled", True) or today < pd.Timestamp(live["start"]):
        return None
    if book.empty:
        return "first paper rebalance"
    last = book["date"].max()
    if cfg["model"].get("rebalance") == "weekly" and today.isocalendar()[:2] != last.isocalendar()[:2]:
        return "weekly rebalance"
    if (today.year, today.month) != (last.year, last.month):
        return "monthly rebalance"
    if int(book.loc[book["date"] == last, "overlay"].iloc[0]) != overlay:
        return "drawdown overlay changed"
    return None


def trades(target: pd.Series, current: pd.Series, band: float) -> pd.DataFrame:
    """Paper trades in percent of NAV, skipping those below the no-trade band."""
    idx = target.index.union(current.index)
    t, c = target.reindex(idx).fillna(0.0), current.reindex(idx).fillna(0.0)
    d = pd.DataFrame({"current": c, "target": t, "trade": t - c})
    d["action"] = np.where(d["trade"].abs() < band, "hold", np.where(d["trade"] > 0, "buy", "sell"))
    return d.sort_values("trade", key=np.abs, ascending=False)


def append_book(
    path: Path, date: pd.Timestamp, w: pd.Series, status: str, overlay: int, reason: str, version: str
) -> int:
    """Append one rebalance (once per date). Returns the number of rows written."""
    book = read_book(path)
    if not book.empty and (book["date"] == pd.Timestamp(date)).any():
        return 0
    rows = pd.DataFrame(
        {
            "date": pd.Timestamp(date).normalize(),
            "asset": w.index,
            "weight": w.round(6).to_numpy(),
            "status": status,
            "overlay": overlay,
            "reason": reason,
            "version": version,
        }
    )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows.to_csv(path, mode="a", header=not Path(path).exists(), index=False)
    return len(rows)


def monitor(book: pd.DataFrame, px: pd.DataFrame, quotes: dict[str, float], cfg: dict) -> dict:
    """Intraday check: the paper NAV with the latest quotes appended as today's prices, its
    drawdown from the peak and today's change, against the alert thresholds."""
    nav, w = paper_nav(book, px)
    if nav.empty:
        return {"status": "no paper book yet"}
    last = px.reindex(columns=w.index).ffill().iloc[-1]
    q = pd.Series(quotes).reindex(w.index)
    move = (q / last - 1).fillna(0.0)
    day = float((w * move).sum())
    now = float(nav.iloc[-1] * (1 + day))
    peak = max(float(nav.max()), now)
    dd = 1 - now / peak
    al = cfg["live"]["alerts"]
    breaches = []
    if dd >= al["drawdown"]:
        breaches.append(f"drawdown {dd:.1%} ≥ {al['drawdown']:.0%}")
    if -day >= al["daily_loss"]:
        breaches.append(f"daily loss {-day:.1%} ≥ {al['daily_loss']:.0%}")
    worst = move.sort_values().head(3)
    return {
        "status": "breach" if breaches else "ok",
        "nav": now,
        "drawdown": dd,
        "day": day,
        "breaches": breaches,
        "worst movers": {k: float(v) for k, v in worst.items()},
        "quoted": int(q.notna().sum()),
        "held": len(w),
    }
