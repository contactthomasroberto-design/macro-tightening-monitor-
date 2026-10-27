"""Macro Tightening Monitor — Streamlit entry point (multi-page via st.navigation)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT / "app"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

st.set_page_config(page_title="Macro Tightening Monitor", page_icon="📉", layout="wide")

PAGES_DIR = Path(__file__).parent / "pages"

# (file, title, icon) — order is the navigation order. Pages are added milestone by milestone.
PAGES = [
    ("overview.py", "Overview", "🧭"),
    ("calendar.py", "Calendar and news", "🗓️"),
    ("inflation.py", "Inflation", "🔥"),
    ("policy.py", "Policy", "🏛️"),
    ("fincond.py", "Financial conditions", "🌡️"),
    ("curves.py", "Curves and term premium", "📈"),
    ("growth.py", "Growth and recession risk", "🏭"),
    ("transmission.py", "Transmission", "🔗"),
    ("positioning.py", "Positioning", "🧲"),
    ("scenarios.py", "Scenarios and fans", "🌪️"),
    ("regimes.py", "Regime and views", "🧭"),
    ("track_record.py", "Track record", "🎯"),
    ("data_health.py", "Data health", "🩺"),
    ("model_cards.py", "Model cards", "📇"),
]


def build_navigation():
    pages = [
        st.Page(str(PAGES_DIR / f), title=t, icon=i, default=(k == 0))
        for k, (f, t, i) in enumerate(PAGES)
        if (PAGES_DIR / f).exists()
    ]
    return st.navigation(pages)


build_navigation().run()
