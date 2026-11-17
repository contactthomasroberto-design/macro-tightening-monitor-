import pandas as pd
import streamlit as st

from components import footer, header, sidebar_controls
from macro import fund_process as fp
from macro import team

header(
    "Team",
    "The fund's research team: who covers what, what each member is working on, and their past work.",
)
ctl = sidebar_controls()


@st.cache_data(ttl=600, show_spinner=False)
def _load():
    return team.roster(), team.read_log(), fp.read_decisions()


roster, log, decisions = _load()
scores = fp.brier_table(decisions) if not decisions.empty else pd.DataFrame()
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

st.subheader("Forecast track record (decision registry)")
if decisions.empty:
    st.caption(
        "No forecast on record yet. From the committee of 18 Nov, every view is recorded with a threshold, a horizon "
        "and a probability (archive/decisions.csv) and scored automatically once its horizon passes."
    )
else:
    st.dataframe(
        scores.style.format(
            {"Brier": "{:.3f}", "skill": "{:+.2f}", "mean probability": "{:.0%}", "hit rate": "{:.0%}"},
            na_rep="—",
        ),
        use_container_width=True,
    )
    st.caption(
        "Brier score = mean of (probability − outcome)²: 0 is perfect, 0.25 is always saying 50%. Skill = 1 − Brier "
        "/ Brier of the base rate: above 0 the analyst beats a constant forecast. Outcomes come from the data, not "
        "from the committee. Few resolved forecasts mean the ranking is noise: read it after 20 or more per analyst."
    )
    with st.expander(f"All forecasts ({len(decisions)})"):
        st.dataframe(
            decisions.sort_values("date", ascending=False)[
                ["date", "agent", "claim", "probability", "horizon", "status", "outcome", "realised"]
            ],
            use_container_width=True,
            hide_index=True,
        )

for name, members in roster.groupby("team", sort=False):
    st.subheader(name)
    cols = st.columns(2)
    for i, (_, m) in enumerate(members.iterrows()):
        cur, past = team.current_and_past(log, m["agent"])
        with cols[i % 2].container(border=True):
            st.markdown(f"**{m['title']}**  \n<small>`{m['agent']}`</small>", unsafe_allow_html=True)
            st.markdown(m["mandate"])
            if m["agent"] in scores.index and scores.loc[m["agent"], "resolved"] > 0:
                sc = scores.loc[m["agent"]]
                st.markdown(
                    f"<small>Track record: Brier {sc['Brier']:.3f} on {int(sc['resolved'])} resolved forecasts, "
                    f"{int(sc['open'])} open</small>",
                    unsafe_allow_html=True,
                )
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
