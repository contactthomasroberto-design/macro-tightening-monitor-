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
st.set_page_config(page_title="Macro Tightening Monitor", layout="wide")


def _clear_page_caches() -> None:
    st.cache_data.clear()
    st.cache_resource.clear()


@st.cache_resource
def _autorefresh():
    """Live mode: poll the sources for new releases and recompute the light models whose inputs
    changed, in a background thread every MACRO_REFRESH_MINUTES (default 10). Started once per server
    process. After new data, the page caches are cleared so the next page view shows it."""
    import os

    from macro import autorefresh

    if not any(getattr(cb, "__name__", "") == "_clear_page_caches" for cb in autorefresh.ON_CHANGE):
        autorefresh.ON_CHANGE.append(_clear_page_caches)
    return autorefresh.start_background(float(os.environ.get("MACRO_REFRESH_MINUTES", "10")))


def _serve_stale_results() -> None:
    """Pages show the last computed results at once; the background refresh replaces them. A new
    daily snapshot in the repository (computed results) is adopted on the next run, restart or not."""
    from macro import results, warmstart

    results.SERVE_STALE = True
    if warmstart.apply_snapshot().get("applied"):
        _clear_page_caches()  # new results from the snapshot: page caches must not hide them


_serve_stale_results()
_autorefresh()

PAGES_DIR = Path(__file__).parent / "views"

# Navigation sections: (section, [(file, title), ...]) — order is the navigation order.
SECTIONS = [
    ("Monitor", [("overview.py", "Overview"), ("calendar.py", "Calendar and releases")]),
    (
        "Models",
        [
            ("inflation.py", "Inflation"),
            ("policy.py", "Monetary policy"),
            ("fincond.py", "Financial conditions"),
            ("curves.py", "Yield curves and term premium"),
            ("growth.py", "Growth and recession risk"),
            ("transmission.py", "Transmission"),
            ("positioning.py", "Positioning"),
        ],
    ),
    (
        "Outlook",
        [
            ("scenarios.py", "Scenarios and fan charts"),
            ("regimes.py", "Regime and views"),
            ("history.py", "Historical cycles"),
        ],
    ),
    (
        "Governance",
        [
            ("track_record.py", "Track record"),
            ("data_health.py", "Data health"),
            ("model_cards.py", "Model cards"),
        ],
    ),
]
PAGES = [p for _, ps in SECTIONS for p in ps]


def build_navigation():
    nav = {
        section: [
            st.Page(str(PAGES_DIR / f), title=t, default=(f == PAGES[0][0]))
            for f, t in ps
            if (PAGES_DIR / f).exists()
        ]
        for section, ps in SECTIONS
    }
    return st.navigation(nav, expanded=True)


page = build_navigation()
from components import global_controls  # noqa: E402  (after sys.path setup and the stale-module purge)

global_controls()
page.run()
