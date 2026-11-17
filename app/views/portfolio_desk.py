import streamlit as st

from components import footer, header, sidebar_controls
from macro.config import ROOT

header(
    "Desk",
    "The GitHub desk: every analyst's computed note, refreshed with the data, across all the markets the monitor follows.",
)
ctl = sidebar_controls()
DESK = ROOT / "docs" / "research" / "desk"

if not (DESK / "README.md").exists():
    st.info("No desk run yet: notes are written by GitHub Actions at every refresh (scripts/desk_run.py).")
else:
    index = (DESK / "README.md").read_text(encoding="utf-8")
    head, _, debate = index.partition("## Points à débattre")
    st.markdown(head.split("\n", 1)[1] if head.startswith("# ") else head)
    with st.expander("Points to debate at tonight's committee", expanded=True):
        st.markdown("## Points à débattre" + debate)
    notes = sorted(p for p in DESK.glob("*.md") if p.name != "README.md")
    pick = st.selectbox("Read a note", [p.stem for p in notes])
    if pick:
        st.markdown((DESK / f"{pick}.md").read_text(encoding="utf-8"))
st.caption(
    "Computed by code from the data store and the portfolio's models (src/macro/desk.py): figures, z-scores, "
    "percentiles, signal-family scores and their agreement, published house views, positioning. No AI opinion; the "
    "nightly committee of Claude agents reads, challenges and completes these notes."
)
footer()
