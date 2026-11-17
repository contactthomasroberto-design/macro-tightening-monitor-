import pandas as pd
import streamlit as st

from components import footer, header, sidebar_controls
from macro import news

header(
    "News",
    "Latest headlines from BBC, MarketWatch, CNBC, the Fed, the ECB, and Reuters and Bloomberg via Google News, "
    "tagged by holding and theme.",
)
ctl = sidebar_controls()


@st.cache_data(ttl=900, show_spinner="Reading the feeds…")
def _news():
    return news.headlines()


df, failed = _news()
tags = sorted({t for ts in df["tags"] for t in ts})
c1, c2 = st.columns([3, 1])
pick = c1.multiselect(
    "Filter by tag", tags, default=[t for t in ("SK Hynix", "Samsung", "Memory chips", "Fed") if t in tags]
)
only = c2.toggle("Tagged only", value=True)
show = df
if pick:
    show = show[show["tags"].map(lambda ts: bool(set(ts) & set(pick)))]
elif only:
    show = show[show["tags"].map(bool)]
for _, r in show.head(80).iterrows():
    when = f"{r['published']:%d %b %H:%M} UTC" if pd.notna(r["published"]) else ""
    tg = " · ".join(r["tags"])
    st.markdown(
        f"**[{r['title']}]({r['link']})**  \n<small>{r['source']} · {when}{' · ' + tg if tg else ''}</small>",
        unsafe_allow_html=True,
    )
if show.empty:
    st.info("No headline matches the filter.")
st.caption(
    f"{len(df)} headlines from the last 72 hours, refreshed every 15 minutes. Headlines are shown, not scored: "
    "the quantitative news input is the GDELT tone (Signals), which keeps a zero weight until it passes its test."
    + (f" Feeds unavailable now: {', '.join(failed)}." if failed else "")
)
footer()
