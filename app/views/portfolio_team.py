import pandas as pd
import streamlit as st

from components import footer, header, sidebar_controls
from macro import team

header(
    "Team",
    "The fund's research team: who covers what, what each member is working on, and their past work.",
)
ctl = sidebar_controls()


@st.cache_data(ttl=600, show_spinner=False)
def _load():
    return team.roster(), team.read_log()


roster, log = _load()
c = st.columns(4)
c[0].metric("Members", len(roster))
c[1].metric("Teams", roster["team"].nunique())
c[2].metric("Assignments on record", len(log))
last = log["date"].max() if not log.empty else None
c[3].metric("Last research run", f"{last:%d %b %Y}" if last is not None and pd.notna(last) else "none yet")
st.caption(
    "Each member is an AI research agent with a written mandate (.claude/agents/). They research; they do not set the "
    "portfolio's weights, which come from the rules. Every night at 23:41 (Zurich) the CIO briefs the team, the "
    "analysts research their area across the whole market, and the work is recorded here and in docs/research/."
)

for name, members in roster.groupby("team", sort=False):
    st.subheader(name)
    cols = st.columns(2)
    for i, (_, m) in enumerate(members.iterrows()):
        cur, past = team.current_and_past(log, m["agent"])
        with cols[i % 2].container(border=True):
            st.markdown(f"**{m['title']}**  \n<small>`{m['agent']}`</small>", unsafe_allow_html=True)
            st.markdown(m["mandate"])
            if cur is None:
                st.markdown("<small>No assignment yet.</small>", unsafe_allow_html=True)
                continue
            status = "🟦 working on" if cur["status"] == "en cours" else "✓ last work"
            link = f" — [note]({cur['link']})" if isinstance(cur["link"], str) and cur["link"] else ""
            st.markdown(
                f"<small>{status} ({cur['date']:%d %b})</small>  \n**{cur['task']}**{link}",
                unsafe_allow_html=True,
            )
            if isinstance(cur["summary"], str) and cur["summary"]:
                st.markdown(f"<small>{cur['summary']}</small>", unsafe_allow_html=True)
            if not past.empty:
                with st.expander(f"Previous work ({len(past)})"):
                    for _, p in past.iterrows():
                        st.markdown(f"- {p['date']:%d %b %Y} — {p['task']}: {p['summary']}")
footer()
