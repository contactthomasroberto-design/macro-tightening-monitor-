import datetime as dt

import pandas as pd
import streamlit as st

from components import footer, header
from macro.config import calendar

header("Calendar and news", "Upcoming central-bank decisions and major data releases.")

cal = calendar()
today = dt.date.today()
rows = [
    {
        "date": e.date,
        "in_days": (e.date - today).days,
        "event": e.label,
        "bank/region": e.bank or e.region,
        "category": e.category,
        "source": cal.sources.get(e.source, e.source),
        "verified": "verified" if e.verified else "unverified",
        "retrieved": e.retrieved,
    }
    for e in cal.events
]
df = pd.DataFrame(rows)
upcoming = df[df["in_days"] >= 0]
n_unver = int((~pd.Series([e.verified for e in cal.events])).sum())
if n_unver:
    st.warning(
        f"{n_unver} events are marked **unverified**: entered without retrieving the official calendar. Check the source "
        "link and set `verified: true` and `retrieved:` in config/calendar.yaml.",
    )
st.subheader("Upcoming")
st.dataframe(upcoming, use_container_width=True, hide_index=True)
with st.expander("Past events in calendar file"):
    st.dataframe(df[df["in_days"] < 0], use_container_width=True, hide_index=True)
st.caption(
    "What moved the nowcasts this week appears on the Growth and Inflation pages (news decomposition)."
)
footer()
