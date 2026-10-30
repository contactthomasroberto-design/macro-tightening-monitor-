"""Signposts: thresholds that would change the view, evaluated on the latest data.

Configured in `config/signposts.yaml`. Two computed series: SAHM (3-month average unemployment
minus its minimum over the previous 12 months, the real-time Sahm rule) and OAT_BUND (France minus
Germany 10-year yields, ECB long-term interest rates).
"""

from __future__ import annotations

import pandas as pd
import yaml

from macro.config import CONFIG_DIR


def load() -> list[dict]:
    with open(CONFIG_DIR / "signposts.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["signposts"]


def sahm(unrate: pd.Series) -> pd.Series:
    """The project's Sahm rule (macro.recession.sahm), on the observations as published: a month the
    BLS did not publish (October 2025, government shutdown) is skipped, not turned into a gap that
    would blank the rule for a year."""
    from macro.recession import sahm as sahm_rule

    return sahm_rule(unrate.dropna())["sahm"].dropna()


def transform(s: pd.Series, how: str) -> pd.Series:
    s = s.dropna()
    if how == "yoy":
        s = s.resample("MS").last()
        return 100 * (s / s.shift(12) - 1)
    if how == "ann3m":
        s = s.resample("MS").last()
        return 100 * ((s / s.shift(3)) ** 4 - 1)
    if how == "bp":
        return 100 * s
    return s


def series_for(sid: str, get) -> pd.Series | None:
    """Catalogue series or a computed one; `get` is try_series (returns None when unavailable)."""
    if sid == "SAHM":
        u = get("UNRATE")
        return None if u is None else sahm(u)
    if sid == "OAT_BUND":
        fr, de = get("FR_10Y"), get("DE_10Y")
        if fr is None or de is None:
            return None
        return (fr.resample("MS").last() - de.resample("MS").last()).dropna()
    return get(sid)


def evaluate(get, items: list[dict] | None = None) -> pd.DataFrame:
    """One row per signpost: latest value, threshold, crossed or not, distance to the threshold."""
    rows = []
    for it in items or load():
        s = series_for(it["series"], get)
        if s is None or s.dropna().empty:
            rows.append({**it, "latest": None, "date": None, "crossed": None, "distance": None})
            continue
        x = transform(s, it["transform"]).dropna()
        v = float(x.iloc[-1])
        crossed = v > it["threshold"] if it["op"] == "above" else v < it["threshold"]
        dist = (it["threshold"] - v) if it["op"] == "above" else (v - it["threshold"])
        rows.append(
            {**it, "latest": v, "date": x.index[-1].date(), "crossed": bool(crossed), "distance": dist}
        )
    return pd.DataFrame(rows).set_index("id")


def newly_crossed(now: pd.DataFrame, previous: dict[str, bool]) -> list[str]:
    """Signposts crossed now and not crossed at the previous check."""
    return [i for i, r in now.iterrows() if r["crossed"] is True and not previous.get(i, False)]
