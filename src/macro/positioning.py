"""Positioning (BRIEF §5.7): CFTC Traders in Financial Futures, Tuesday reference dates.

Duration adjustment to 10-year-note equivalents uses approximate DV01 ratios per contract (the OFR
Hedge Fund Monitor publishes exact 10-year equivalents; prefer it when loaded). Equity and FX
positions are converted to USD notional with the latest price. Crowding = rolling percentile rank
above 90 or below 10 over 3 years.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from macro.utils import rolling_percentile

# Approximate DV01 of one contract relative to the 10Y T-note future (TY ~ $70/bp). Order of
# magnitude only: SOFR 3M futures $25/bp per contract.
DV01_RATIO = {"TFF_UST10_LEV": 1.0, "TFF_UST10_AM": 1.0, "TFF_SOFR3M_LEV": 25.0 / 70.0}
# Contract notional: E-mini S&P 500 = $50 x index; euro FX = EUR 125,000; yen = JPY 12.5m.
NOTIONAL = {
    "TFF_ES_LEV": ("SPX", 50.0, "mult"),
    "TFF_ES_AM": ("SPX", 50.0, "mult"),
    "TFF_EUR_LEV": ("EURUSD", 125_000.0, "mult"),
    "TFF_JPY_LEV": ("USDJPY", 12_500_000.0, "div"),
}
LABELS = {
    "TFF_UST10_LEV": "Leveraged funds, 10Y Treasury (10Y equiv., contracts)",
    "TFF_UST10_AM": "Asset managers, 10Y Treasury (10Y equiv., contracts)",
    "TFF_SOFR3M_LEV": "Leveraged funds, 3M SOFR (10Y equiv., contracts)",
    "TFF_ES_LEV": "Leveraged funds, E-mini S&P 500 (USD bn)",
    "TFF_ES_AM": "Asset managers, E-mini S&P 500 (USD bn)",
    "TFF_EUR_LEV": "Leveraged funds, euro FX (USD bn)",
    "TFF_JPY_LEV": "Leveraged funds, yen (USD bn)",
}


def adjust(net: pd.Series, sid: str, prices: dict[str, pd.Series]) -> pd.Series:
    """Rates -> 10Y-note equivalents (contracts); equity/FX -> USD bn notional at the same-date price."""
    if sid in DV01_RATIO:
        return net * DV01_RATIO[sid]
    if sid in NOTIONAL:
        pid, size, how = NOTIONAL[sid]
        px = prices[pid].reindex(net.index, method="ffill")
        usd = net * size * px if how == "mult" else net * size / px
        return usd / 1e9
    return net


def positioning_table(
    series: dict[str, pd.Series], window: int = 156, crowd: tuple[float, float] = (10, 90)
) -> tuple[pd.DataFrame, dict]:
    """Latest level, 4-week change, rolling percentile and crowding flag per series."""
    rows, pct = [], {}
    for sid, s in series.items():
        s = s.dropna()
        p = rolling_percentile(s, window)
        pct[sid] = p
        last_p = float(p.iloc[-1]) if p.notna().any() else np.nan
        flag = "crowded long" if last_p >= crowd[1] else "crowded short" if last_p <= crowd[0] else ""
        rows.append(
            {
                "series": LABELS.get(sid, sid),
                "id": sid,
                "reference date (Tue)": s.index[-1].date(),
                "net": float(s.iloc[-1]),
                "4w change": float(s.iloc[-1] - s.iloc[-5]) if len(s) > 5 else np.nan,
                "percentile (3y)": last_p,
                "flag": flag,
            }
        )
    return pd.DataFrame(rows).set_index("series"), pct
