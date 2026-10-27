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
