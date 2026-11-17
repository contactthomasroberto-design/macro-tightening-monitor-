"""Cached bundle and labels shared by the Portfolio pages."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components import CACHE_TTL
from macro.pipeline import portfolio_bundle

SLEEVE_ORDER = ["equity", "semis", "bond", "real", "cash"]
SLEEVE_LABEL = {
    "equity": "Equities",
    "semis": "Semiconductors (conviction)",
    "bond": "Bonds",
    "real": "Gold and commodities",
    "cash": "Cash",
}
SLEEVE_COLOR = {  # sober palette: no alarm colours for ordinary holdings
    "equity": "#002855",
    "semis": "#7391b5",
    "bond": "#8c8c8c",
    "real": "#b08d3c",
    "cash": "#d0d0d0",
}
DISCLAIMER = (
    "Model portfolio tracked on paper by fixed rules (config/portfolio.yaml). It places no orders and is "
    "not investment advice: past and simulated results do not predict future returns."
)


@st.cache_resource(
    ttl=CACHE_TTL, show_spinner="Loading the portfolio (first run simulates 20 years, a few minutes)…"
)
def _bundle() -> dict:
    return portfolio_bundle()


def bundle() -> dict:
    """The portfolio bundle, or a clear message (and stop) while its data are not loaded yet."""
    try:
        return _bundle()
    except (KeyError, ValueError) as exc:
        st.info(
            "The portfolio's price data are not in the dashboard yet: they arrive with the next GitHub refresh "
            f"(a few times a day). Detail: {type(exc).__name__}: {exc}"
        )
        st.stop()
        raise  # unreachable: st.stop() ends the script


def name(b: dict, a: str) -> str:
    return b["config"]["universe"].get(a, {}).get("name", a)


def sleeve(b: dict, a: str) -> str:
    return b["config"]["universe"].get(a, {}).get("sleeve", "")


def by_sleeve(b: dict, w: pd.Series) -> pd.Series:
    s = w.groupby([sleeve(b, a) for a in w.index]).sum()
    return s.reindex([x for x in SLEEVE_ORDER if x in s.index])


def score_css(v) -> str:
    """Cell shading for a score in [-1, 1]: blue positive, red negative (no matplotlib needed)."""
    if not isinstance(v, int | float) or v != v:
        return ""
    a = min(abs(float(v)), 1.0) * 0.45
    rgb = "31,58,95" if v > 0 else "165,42,42"
    return f"background-color: rgba({rgb},{a:.2f})"
