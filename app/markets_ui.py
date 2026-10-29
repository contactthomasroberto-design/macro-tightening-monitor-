"""Formatting and the cached bundle shared by the Markets pages."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from components import CACHE_TTL
from macro.pipeline import markets_bundle

NAVY = (31, 58, 95)
RED = (165, 42, 42)


@st.cache_resource(ttl=CACHE_TTL, show_spinner="Computing cross-asset analytics…")
def bundle() -> dict:
    return markets_bundle()


def ordinal(x: float) -> str:
    """1st, 2nd, 3rd, 4th, 11th, 22nd ... for a percentile."""
    n = int(round(x))
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def fmt_level(v: float, kind: str) -> str:
    if v != v:
        return "n/a"
    if kind == "yield":
        return f"{v:.2f}%"
    if kind == "spread":
        return f"{v:,.0f} bp"
    if kind == "vol":
        return f"{v:.1f}"
    return f"{v:,.4f}" if abs(v) < 10 else f"{v:,.2f}" if abs(v) < 1000 else f"{v:,.0f}"


def fmt_move(v: float, unit: str) -> str:
    if v != v:
        return ""
    if unit == "bp":
        return f"{v:+.0f} bp"
    if unit == "%":
        return f"{v:+.2f}%"
    return f"{v:+.1f}"


def adds_to_stress(z: float, risk: int) -> bool:
    """True when the move adds to risk aversion: spreads, volatility or the dollar up, equities down."""
    return risk != 0 and z == z and np.sign(z) == np.sign(risk)


def z_color(z: float, risk: int = 0) -> str:
    """Background for a move in standard deviations: intensity from |z|; red when the move adds to
    risk aversion, navy otherwise (assets with no clear risk sign are always navy)."""
    if z != z:
        return ""
    alpha = min(abs(z) / 3.0, 1.0) * 0.45
    r, g, b = RED if adds_to_stress(z, risk) else NAVY
    return f"background-color: rgba({r},{g},{b},{alpha:.2f})"


def dashboard_table(d: pd.DataFrame) -> pd.io.formats.style.Styler:
    """The cross-asset monitor as a styled table (moves in quoting units, z-score shaded)."""
    out = pd.DataFrame(index=d.index)
    out["Class"] = d["class"]
    out["Last"] = [fmt_level(v, k) for v, k in zip(d["last"], d["kind"], strict=True)]
    for h in ("1D", "1W", "1M", "3M", "YTD"):
        out[h] = [fmt_move(v, u) for v, u in zip(d[h], d["unit"], strict=True)]
    out["1M move (σ)"] = d["z 1M"]
    out["Level pctile"] = d["level pct 10y"]
    out["Realised vol pctile (3y)"] = d["rvol pct 3y"]
    out["As of"] = [
        f"{t:%d %b}" + (" (stale)" if s >= 3 else "")
        for t, s in zip(d["as_of"], d["stale_bdays"], strict=True)
    ]
    risk = d["risk"]

    def shade(col: pd.Series) -> list[str]:
        return [z_color(z, int(risk.loc[i])) for i, z in col.items()]

    return out.style.apply(shade, subset=["1M move (σ)"]).format(
        {"1M move (σ)": "{:+.1f}", "Level pctile": "{:.0f}", "Realised vol pctile (3y)": "{:.0f}"}, na_rep=""
    )
