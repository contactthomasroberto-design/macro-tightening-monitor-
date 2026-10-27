"""Reusable Streamlit pieces: header (LIVE/DEMO badge, run metadata), footer disclaimer,
chart wrapper (plotly + table view + CSV download), status chips."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from macro.plotting import STATUS
from macro.utils import DISCLAIMER, RESEARCH_SERIES_NOTE, SYNTHETIC_BANNER, is_demo, run_metadata


def theme() -> str:
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:  # older Streamlit or no browser context (AppTest)
        return "light"


def header(title: str, subtitle: str | None = None) -> None:
    if is_demo():
        st.error(f"**{SYNTHETIC_BANNER}**", icon="⚠️")
    meta = run_metadata()
    badge = "🟠 DEMO" if is_demo() else "🟢 LIVE"
    st.title(title)
    st.caption(f"{badge} · git `{meta['git_hash']}` · run {meta['run_timestamp']} · not investment advice")
    if subtitle:
        st.markdown(subtitle)


def footer(research_series: bool = False) -> None:
    st.divider()
    if research_series:
        st.caption(RESEARCH_SERIES_NOTE)
    st.caption(DISCLAIMER)


def chart(fig: go.Figure, data: pd.DataFrame | pd.Series | None = None, key: str | None = None) -> None:
    """Plotly chart with a table view and CSV download of the underlying data."""
    st.plotly_chart(fig, use_container_width=True, key=f"fig_{key}" if key else None)
    if data is not None:
        df = data.to_frame() if isinstance(data, pd.Series) else data
        with st.expander("Table view and CSV"):
            st.dataframe(df.tail(500), use_container_width=True)
            st.download_button(
                "Download CSV",
                df.to_csv().encode(),
                file_name=f"{key or 'data'}.csv",
                mime="text/csv",
                key=f"dl_{key}" if key else None,
            )


def status_chip(level: str, text: str) -> str:
    c, icon, label = STATUS[level]
    return f"<span style='color:{c};font-weight:600'>{icon} {label}</span> — {text}"


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
        st.caption(f"ℹ️ {n}")


def sidebar_controls() -> dict:
    """Global controls (BRIEF §7): date range, r* range, rule parameters. Values persist across pages
    through session_state keys."""
    import copy

    from macro.config import assumptions

    a = assumptions()
    sb = st.sidebar
    sb.header("Controls")
    start_year = sb.slider(
        "Charts start in", 1990, 2025, st.session_state.get("start_year", 2000), key="start_year"
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
