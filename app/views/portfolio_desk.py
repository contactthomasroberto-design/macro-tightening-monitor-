"""Research notes: every piece of work of the team, in one place.

Three sources, newest first:
- the analysts' deep-dive research of the day (docs/research/notes/<date>/), written by the midday session;
- the committee's notes and debates (docs/research/committee/<date>/), written by the nightly session;
- the GitHub desk's computed notes (docs/research/desk/), rewritten at every refresh."""

import re

import pandas as pd
import streamlit as st

from components import footer, header, sidebar_controls
from macro.config import ROOT

header(
    "Research notes",
    "All the team's work: deep-dive research of the day, committee notes and debates, and the computed desk notes.",
)
ctl = sidebar_controls()
RESEARCH = ROOT / "docs" / "research"


def dated_dirs(folder: str) -> list:
    base = RESEARCH / folder
    return sorted((p for p in base.glob("20*") if p.is_dir()), reverse=True) if base.exists() else []


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def browse(folder: str, empty: str, key: str) -> None:
    days = dated_dirs(folder)
    if not days:
        st.info(empty)
        return
    day = st.selectbox("Day", [d.name for d in days], key=f"{key}-day")
    files = sorted((RESEARCH / folder / day).glob("*.md"))
    if not files:
        st.caption("No note that day.")
        return
    texts = {f.stem: f.read_text(encoding="utf-8") for f in files}
    total = sum(word_count(t) for t in texts.values())
    st.caption(f"{len(files)} documents, {total:,} words.".replace(",", " "))
    for name, text in texts.items():
        first = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.strip()), name)
        with st.expander(f"{first}  ·  {word_count(text):,} words".replace(",", " ")):
            st.markdown(text)


from macro import fund_process as fp  # noqa: E402
from macro import research_notes as rn  # noqa: E402

props = rn.follow_up(rn.proposals(), fp.read_decisions())
vol = rn.word_counts()
c = st.columns(3)
c[0].metric(
    "Words written (last 7 days)",
    f"{int(vol[pd.to_datetime(vol['date']) >= pd.Timestamp.today() - pd.Timedelta(days=7)]['words'].sum()):,}".replace(
        ",", " "
    )
    if not vol.empty
    else "0",
)
c[1].metric("Analysts' proposals", len(props))
c[2].metric("Adopted by the committee", int(props["adopted"].sum()) if not props.empty else 0)
if not props.empty:
    with st.expander("Analysts' proposals and what the committee did with them"):
        view = props.sort_values("date", ascending=False).assign(date=lambda d: d["date"].dt.date)
        st.dataframe(
            view[
                [
                    "date",
                    "agent",
                    "ticker",
                    "direction",
                    "threshold",
                    "horizon",
                    "probability",
                    "adopted",
                    "rationale",
                ]
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.caption(
            "Adopted = a committee decision on the same instrument and direction within two days: it is in the "
            "book's views. Each rejection is explained in the daily note."
        )

tabs = st.tabs(["Deep-dive research", "Committee notes and debates", "GitHub desk (computed)"])
with tabs[0]:
    browse(
        "notes",
        "The analysts' research of the day is written by the midday research session (docs/research/notes/).",
        "notes",
    )
with tabs[1]:
    browse("committee", "The committee's notes and debates are written by the nightly session.", "committee")
with tabs[2]:
    DESK = RESEARCH / "desk"
    if not (DESK / "README.md").exists():
        st.info(
            "No desk run yet: notes are written by GitHub Actions at every refresh (scripts/desk_run.py)."
        )
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
            "Computed by code from the data store and the portfolio's models (src/macro/desk.py): no AI opinion; the "
            "analysts read, challenge and complete these notes."
        )
footer()
