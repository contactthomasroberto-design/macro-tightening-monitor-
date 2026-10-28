"""Macro Tightening Monitor — Streamlit entry point (multi-page via st.navigation)."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
for p in (ROOT / "src", ROOT / "app"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _purge_stale_modules() -> None:
    """After a redeploy, Streamlit Community Cloud can pull the new files without restarting the
    server process, which keeps project modules imported from the previous code (an ImportError on a
    name added since). Drop them, and the cached results, whenever the project files changed since
    they were loaded, so the next imports read the new code."""
    files = [f for d in (ROOT / "src" / "macro", ROOT / "app") for f in d.rglob("*.py")]
    sig = hash(tuple(sorted((str(f), f.stat().st_mtime_ns) for f in files)))
    prev = getattr(sys, "_mtm_code_signature", None)
    loaded = "components" in sys.modules or "macro" in sys.modules
    if (prev is None and loaded) or (prev is not None and prev != sig):
        for name in list(sys.modules):
            if name in ("components", "macro") or name.startswith("macro."):
                del sys.modules[name]
        st.cache_data.clear()
        st.cache_resource.clear()
    sys._mtm_code_signature = sig  # type: ignore[attr-defined]


_purge_stale_modules()
st.set_page_config(page_title="Macro Tightening Monitor", page_icon="📉", layout="wide")


@st.cache_resource
def _autorefresh():
    """Live mode: refresh expired data and recompute models in a background thread, every few hours
    (MACRO_REFRESH_HOURS, default 3). Started once per server process."""
    import os

    from macro import autorefresh

    return autorefresh.start_background(float(os.environ.get("MACRO_REFRESH_HOURS", "3")))


_autorefresh()

PAGES_DIR = Path(__file__).parent / "views"

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
    ("history.py", "Historical cycles", "📜"),
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
