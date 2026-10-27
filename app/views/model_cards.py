import streamlit as st

from components import footer, header
from macro.config import ROOT
from macro.versions import MODEL_VERSIONS

header(
    "Model cards",
    "Purpose, inputs, equations, sample, assumptions, validation and failure modes of every model; changelog and research log.",
)
docs = ROOT / "docs"
cards = sorted(p for p in (docs / "model_cards").glob("*.md") if p.stem != "TEMPLATE")
tab_cards, tab_notes, tab_log, tab_research = st.tabs(
    ["Model cards", "Source notes", "Model changelog", "Research log"]
)
with tab_cards:
    name = st.selectbox("Model", [p.stem for p in cards], key="card_sel")
    st.caption(f"Current version: {MODEL_VERSIONS.get(name, 'n/a')}")
    st.markdown((docs / "model_cards" / f"{name}.md").read_text())
with tab_notes:
    notes = sorted(p for p in (docs / "notes").glob("*.md") if p.stem != "TEMPLATE")
    n = st.selectbox("Module", [p.stem for p in notes], key="note_sel")
    st.markdown((docs / "notes" / f"{n}.md").read_text())
with tab_log:
    st.markdown((docs / "MODEL_CHANGELOG.md").read_text())
with tab_research:
    st.markdown((docs / "research_log.md").read_text())
footer()
