"""View layer (BRIEF §5.9): scorecard, priced-vs-model, market-confirmation check, view template.

Language rule: implications and sensitivities, never recommendations ("implies", "is consistent
with", "sensitivity"; no "buy", "sell", "overweight").
"""

from __future__ import annotations

import numpy as np
import pandas as pd

BANNED_WORDS = ("buy", "sell", "overweight", "underweight", "go long", "go short", "price target")


def status_from(value: float, thresholds: tuple[float, float, float], higher_is_worse: bool = True) -> str:
    """Map a value to good/warning/serious/critical with three increasing thresholds."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "warning"
    v = value if higher_is_worse else -value
    t1, t2, t3 = thresholds if higher_is_worse else tuple(-t for t in thresholds)
    if v < t1:
        return "good"
    if v < t2:
        return "warning"
    if v < t3:
        return "serious"
    return "critical"


def scorecard_row(metric: str, value, unit: str, status: str, note: str = "") -> dict:
    return {"metric": metric, "value": value, "unit": unit, "status": status, "note": note}


def market_confirmation(moves: dict[str, float], view: str) -> pd.DataFrame:
    """Do recent market moves agree with the stated view?

    moves: 4-week changes — '2Y yield' (bp), '10Y breakeven' (bp), 'Broad dollar' (%), 'Credit spread' (bp),
    'S&P 500' (%). For a 'tightening' view consistent signs are: 2Y up, breakeven down or flat,
    dollar up, credit spread up, equities down. 'easing' is the mirror image."""
    expected = {"2Y yield": 1, "10Y breakeven": -1, "Broad dollar": 1, "Credit spread": 1, "S&P 500": -1}
    sign = 1 if view == "tightening" else -1
    rows = []
    for k, e in expected.items():
        if k not in moves or moves[k] is None or np.isnan(moves[k]):
            continue
        m = moves[k]
        consistent = np.sign(m) == sign * e or abs(m) < 1e-9
        rows.append(
            {
                "indicator": k,
                "4-week move": m,
                "expected sign": "+" if sign * e > 0 else "−",
                "consistent": bool(consistent),
            }
        )
    return pd.DataFrame(rows).set_index("indicator") if rows else pd.DataFrame()


def view_template(
    view: str,
    evidence: list[str],
    priced: str,
    change_view: list[str],
    risks: list[str],
    catalysts: list[str],
    implications: list[str],
) -> dict:
    """Structured view for the written notes. Validates the language rule."""
    v = {
        "View": view,
        "Evidence": evidence,
        "What is priced": priced,
        "What would change the view": change_view,
        "Risks": risks,
        "Catalysts (calendar)": catalysts,
        "Implications and sensitivities (not recommendations)": implications,
    }
    text = " ".join([view, priced, *evidence, *change_view, *risks, *catalysts, *implications]).lower()
    bad = [w for w in BANNED_WORDS if w in text]
    if bad:
        raise ValueError(f"recommendation language not allowed in views: {bad}")
    return v
