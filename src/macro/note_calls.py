"""Post-mortem of the research notes' calls (config/note_calls.yaml).

Each call names a series, a transform, a statistic over the window from the call to its maturity,
and a condition. Before maturity the call is "open" and shows the latest value; after it, "right"
or "wrong". A withdrawn call is still scored: withdrawing a call does not erase it."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import yaml

from macro.config import ROOT
from macro.signposts import sahm

PATH = ROOT / "config" / "note_calls.yaml"


def load(path=PATH) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["calls"]


def _transform(s: pd.Series, how: str) -> pd.Series:
    s = s.dropna()
    if how == "yoy":
        m = s.resample("MS").last().dropna()
        return (100 * (m / m.shift(12) - 1)).dropna()
    if how == "sahm":
        return sahm(s)
    return s


def _holds(x: float, op: str, thr) -> bool:
    if op == "below":
        return x < thr
    if op == "above":
        return x > thr
    lo, hi = thr
    return lo <= x <= hi


def evaluate(get: Callable[[str], pd.Series | None], calls: list[dict], today=None) -> pd.DataFrame:
    today = pd.Timestamp(today or pd.Timestamp.today().normalize())
    rows = []
    for c in calls:
        made, mat = pd.Timestamp(c["made"]), pd.Timestamp(c["matures"])
        raw = get(c["series"])
        s = _transform(raw, c.get("transform", "level")) if raw is not None else pd.Series(dtype=float)
        win = s.loc[made : min(mat, today)]
        if c.get("stat", "at") == "at" or win.empty:
            val = float(s.loc[:mat].iloc[-1]) if not s.loc[:mat].empty else float("nan")
        else:
            val = float(win.max() if c["stat"] == "max" else win.min())
        # 'max below' fails as soon as it is breached; otherwise the verdict waits for maturity
        early_fail = (
            c.get("stat") == "max"
            and c["op"] == "below"
            and val == val
            and not _holds(val, "below", c["threshold"])
        )
        early_fail |= (
            c.get("stat") == "min"
            and c["op"] == "above"
            and val == val
            and not _holds(val, "above", c["threshold"])
        )
        if val != val:
            status = "no data"
        elif early_fail:
            status = "wrong"
        elif today <= mat or (
            c.get("stat", "at") == "at" and s.loc[:mat].index[-1] < mat - pd.DateOffset(months=1)
        ):
            status = "open"
        else:
            status = "right" if _holds(val, c["op"], c["threshold"]) else "wrong"
        rows.append(
            {
                "id": c["id"],
                "note": c["note"],
                "statement": c["statement"],
                "matures": mat.date(),
                "value": val,
                "status": status,
                "withdrawn": bool(c.get("withdrawn")),
            }
        )
    return pd.DataFrame(rows).set_index("id")
