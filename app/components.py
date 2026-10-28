"""Reusable Streamlit pieces: header (LIVE/DEMO badge, run metadata), footer disclaimer,
chart wrapper (plotly + table view + CSV download), status chips."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from macro.plotting import STATUS, fit_time_axis
from macro.utils import DISCLAIMER, RESEARCH_SERIES_NOTE, SYNTHETIC_BANNER, is_demo, run_metadata

# Pages re-read their (disk-cached) model results at most this often, so numbers recomputed by the
# background refresh (macro.autorefresh) appear without restarting the app.
CACHE_TTL = 3600


def theme() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # older Streamlit or no browser context (AppTest)
        return "light"


_CSS = """
<style>
  html, body, [class*="css"] { font-feature-settings: "tnum" 1; }
  h1 { font-size: 1.65rem !important; font-weight: 600 !important; letter-spacing: -0.01em; margin-bottom: 0.1rem; }
  h2, h3 { font-weight: 600 !important; letter-spacing: -0.005em; }
  h3 { font-size: 1.08rem !important; border-bottom: 1px solid rgba(128,128,128,0.25); padding-bottom: 0.25rem;
       margin-top: 1.4rem !important; }
  [data-testid="stMetricValue"] { font-size: 1.45rem; font-weight: 600; }
  [data-testid="stMetricLabel"] p { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
  [data-testid="stSidebarNav"] a span { font-size: 0.9rem; }
  .mtm-badge { display: inline-block; padding: 1px 7px; border-radius: 3px; font-size: 0.72rem; font-weight: 600;
               letter-spacing: 0.06em; color: #fff; margin-right: 8px; vertical-align: 1px; }
  .mtm-meta { color: #6a737d; font-size: 0.8rem; }
  .mtm-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: 1px; }
  #MainMenu, footer { visibility: hidden; }
</style>
"""


def header(title: str, subtitle: str | None = None) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    if is_demo():
        st.error(f"**{SYNTHETIC_BANNER}**")
    meta = run_metadata()
    badge = (
        "<span class='mtm-badge' style='background:#b7791f'>DEMO · SYNTHETIC DATA</span>"
        if is_demo()
        else "<span class='mtm-badge' style='background:#1f3a5f'>LIVE DATA</span>"
    )
    st.title(title)
    st.markdown(
        f"{badge}<span class='mtm-meta'>Run {meta['run_timestamp']} · build {meta['git_hash']} · "
        "Research product, not investment advice</span>",
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(subtitle)


def footer(research_series: bool = False) -> None:
    st.divider()
    if research_series:
        st.caption(RESEARCH_SERIES_NOTE)
    st.caption(DISCLAIMER)


def chart_start() -> str | None:
    """Start of the chart window chosen in the sidebar (shared by every page)."""
    ctl = st.session_state.get("_mtm_ctl")
    if ctl:
        return ctl["start"]
    y = st.session_state.get("start_year")
    return f"{int(y)}-01-01" if y else None


def chart(
    fig: go.Figure,
    data: pd.DataFrame | pd.Series | None = None,
    key: str | None = None,
    full_history: bool = False,
) -> None:
    """Plotly chart fitted to the sidebar window (time axes start at 'Charts start in' and end at the
    last observation; dense series thinned), with an on-demand table and CSV of the same window.
    `full_history=True` keeps the whole sample (still clipped to the data range)."""
    start = None if full_history else chart_start()
    fit_time_axis(fig, start)
    st.plotly_chart(
        fig, use_container_width=True, key=f"fig_{key}" if key else None, config={"displaylogo": False}
    )
    if data is not None:
        df = data.to_frame() if isinstance(data, pd.Series) else data
        if start is not None and isinstance(df.index, pd.DatetimeIndex):
            df = df.loc[start:]
        if st.toggle("Data", key=f"tbl_{key}" if key else None, help="Show the data behind this chart"):
            st.dataframe(df.tail(500), use_container_width=True)
            st.download_button(
                "Download CSV",
                df.to_csv().encode(),
                file_name=f"{key or 'data'}.csv",
                mime="text/csv",
                key=f"dl_{key}" if key else None,
            )


def status_chip(level: str, text: str) -> str:
    c, _, label = STATUS[level]
    return f"<span class='mtm-dot' style='background:{c}'></span><span style='color:{c};font-weight:600'>{label}</span> — {text}"


def show_status(level: str, text: str) -> None:
    st.markdown(status_chip(level, text), unsafe_allow_html=True)


def result_meta(res) -> None:
    """Caption with provenance of a `Result`: sources, as-of, N, specifications tried."""
    bits = [f"Sources: {', '.join(res.sources) or 'n/a'}", f"as of {res.as_of or 'n/a'}"]
    if res.n_obs is not None:
        bits.append(f"N = {res.n_obs}")
    if res.n_specs_tried is not None:
        bits.append(f"specifications tried: {res.n_specs_tried}")
    st.caption(" · ".join(bits))
    for n in res.notes:
        st.caption(f"Note: {n}")


_building_global = False


def global_controls() -> dict:
    """Called by app/streamlit_app.py on every run, before the page: the sidebar controls exist once
    for the whole app, so the chosen window and parameters survive page changes."""
    global _building_global
    _building_global = True
    try:
        ctl = sidebar_controls()
    finally:
        _building_global = False
    st.session_state["_mtm_ctl"] = ctl
    return ctl


def sidebar_controls() -> dict:
    """Global controls (BRIEF §7): date range, r* range, rule parameters. Values persist across pages
    through session_state keys."""
    import copy

    from macro.config import assumptions

    if not _building_global and "_mtm_ctl" in st.session_state:
        # rendered once by the app entry point for every page (values persist across pages)
        return st.session_state["_mtm_ctl"]
    a = assumptions()
    sb = st.sidebar
    sb.header("Controls")
    start_year = sb.slider(
        "Charts start in",
        1960,
        pd.Timestamp.today().year - 1,
        st.session_state.get("start_year", 2000),
        key="start_year",
        help="Every time-series chart starts here and ends at the latest observation.",
    )
    lo, hi = a["rstar"]["user_range"]
    rstar = sb.slider(
        "r* range (real, %)",
        -1.0,
        3.0,
        st.session_state.get("rstar_range", (float(lo), float(hi))),
        step=0.25,
        key="rstar_range",
    )
    rules = copy.deepcopy(a["rules"])
    with sb.expander("Rule parameters"):
        rules["taylor1993"]["a_pi"] = st.number_input(
            "Taylor: inflation coefficient", 1.0, 3.0, float(rules["taylor1993"]["a_pi"]), 0.1, key="t93_api"
        )
        rules["taylor1993"]["a_gap"] = st.number_input(
            "Taylor: output-gap coefficient",
            0.0,
            2.0,
            float(rules["taylor1993"]["a_gap"]),
            0.1,
            key="t93_agap",
        )
        rules["inertial"]["rho"] = st.number_input(
            "Inertial rule: smoothing ρ", 0.0, 0.99, float(rules["inertial"]["rho"]), 0.05, key="inr_rho"
        )
        rules["inertial"]["a_pi"] = rules["taylor1993"]["a_pi"]
        rules["inertial"]["a_gap"] = rules["taylor1993"]["a_gap"]
        rules["unemployment_gap"]["okun"] = st.number_input(
            "Okun coefficient", 1.0, 3.0, float(rules["unemployment_gap"]["okun"]), 0.1, key="okun"
        )
    sb.caption("Defaults from config/assumptions.yaml.")
    return {
        "start": f"{start_year}-01-01",
        "rstar_range": tuple(rstar),
        "rules": rules,
        "rstar_step": float(a["rstar"]["grid_step"]),
    }


def scenario_controls() -> dict[str, float]:
    """Sidebar sliders for scenario probabilities (defaults from config/scenarios.yaml),
    re-normalised to sum to 1."""
    from macro.config import scenarios

    sc = scenarios().scenarios
    with st.sidebar.expander("Scenario probabilities", expanded=False):
        raw = {
            k: st.slider(
                v.label, 0.0, 1.0, float(st.session_state.get(f"p_{k}", v.probability)), 0.05, key=f"p_{k}"
            )
            for k, v in sc.items()
        }
        tot = sum(raw.values())
        if tot <= 0:
            st.warning("All probabilities are zero: defaults used.")
            return {k: v.probability for k, v in sc.items()}
        w = {k: v / tot for k, v in raw.items()}
        if abs(tot - 1) > 1e-9:
            st.caption(f"Re-normalised (inputs summed to {tot:.2f}).")
    return w
