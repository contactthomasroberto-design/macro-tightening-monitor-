import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import footer, header, show_status, sidebar_controls, theme
from macro import news
from macro import news_scoring as ns
from macro import plotting as pl
from markets_ui import NAVY, RED

header(
    "News",
    "Headlines from Reuters and Bloomberg (via Google News), BBC, MarketWatch, CNBC, the Fed and the ECB, scored "
    "for sentiment, relevance, novelty and freshness, and what they weigh on each holding.",
)
ctl = sidebar_controls()
th = theme()
cfg = news.load()
NAMES = {
    "HYNIX": "SK Hynix",
    "SAMSUNG": "Samsung Electronics",
    "MU": "Micron",
    "TSM": "TSMC",
    "NVDA": "NVIDIA",
    "ASML": "ASML",
    "MARKET": "Market-wide (Fed, ECB, BoJ, jobs, trade)",
}


@st.cache_data(ttl=600, show_spinner=False)
def _archive() -> pd.DataFrame:
    return ns.read_archive()


@st.cache_data(ttl=900, show_spinner="Reading the feeds…")
def _live():
    return news.headlines(cfg)


arch = _archive()
now = pd.Timestamp.now(tz="UTC")
recent = arch[arch["first_seen"] >= now - pd.Timedelta(days=3)] if not arch.empty else arch

# ------------------------------------------------------------------ pressure by holding
st.subheader("News pressure by holding (last 3 days)")
if recent.empty:
    show_status(
        "warning",
        "No scored headline yet: FinBERT scores the feeds every two hours in GitHub Actions "
        "(portfolio-monitor workflow); the first batch appears after its next run. Unscored headlines below.",
    )
else:
    a = ns.asset_scores(recent, cfg, now=now)
    a.index = [NAMES.get(i, i) for i in a.index]
    fig = go.Figure(
        go.Bar(
            y=a.index[::-1],
            x=a["news score"][::-1],
            orientation="h",
            marker_color=[f"rgb{NAVY}" if v >= 0 else f"rgb{RED}" for v in a["news score"][::-1]],
            text=[f"{h} headlines" for h in a["headlines"][::-1]],
            textposition="outside",
        )
    )
    fig.add_vline(x=0, line_width=1)
    pl.base_layout(
        fig,
        "Weighted news sentiment by holding (−1 to +1)",
        "FinBERT on public RSS headlines; Macro Tightening Monitor",
        f"{now:%Y-%m-%d %H:%M} UTC",
        th,
        height=120 + 34 * len(a),
    )
    fig.update_xaxes(range=[-1, 1])
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
    st.dataframe(
        a.style.format({"news score": "{:+.2f}", "attention": "{:.2f}"}),
        use_container_width=True,
    )
    st.caption(
        "Score: weighted mean of headline sentiment (FinBERT, P(positive) − P(negative)), weights = relevance² × "
        "novelty² × source credibility × freshness (half-life 24 hours). Relevance: 1 for the company itself, 0.6 "
        "for its sector, 0.3 for market-wide news. Novelty: a near-duplicate of an earlier headline counts for "
        "less. Attention: sum of the weights (how much fresh, relevant news there is)."
    )

# ------------------------------------------------------------------ does it move the portfolio?
st.subheader("Does news move the portfolio?")
try:
    from portfolio_ui import _bundle

    b = _bundle()
    t32 = b["tests"].get("H32 company news tone (gate)", {})
    conf = b.get("news_confidence", 0.0)
    if t32.get("n", 0) >= 8:
        show_status(
            "good" if conf > 0 else "warning",
            f"Pre-registered test H32 (company news tone, 2017 onward): IC {t32['IC']:+.2f}, t = {t32['t']:+.1f}, "
            f"{t32['n']} observations. News weight in the allocation: **{conf:.0%}**"
            + (" (signal supported)." if conf > 0 else " (no reliable signal: news is shown, not used)."),
        )
    else:
        show_status("warning", "News tone history not available yet: the news weight stays at 0.")
except Exception:  # noqa: BLE001 - the news page must work even when the portfolio is not computed yet
    show_status("warning", "Portfolio not computed yet: the news weight stays at 0 until its test runs.")
st.caption(
    "The allocation uses news only if it has predicted returns out of sample: company news tone from GDELT "
    "(which indexes Reuters, Bloomberg and thousands of outlets since 2017), 4-week average against its past "
    "year, for the next 4 weeks' return relative to the semiconductor index. The FinBERT archive built here "
    "replaces GDELT as the test sample once it holds a year. Research shows news is priced within days "
    "(Ke, Kelly and Xiu, 2019): a monthly rebalance captures only its slow part."
)

# ------------------------------------------------------------------ headlines by impact
st.subheader("Headlines by impact")
if not recent.empty:
    h = recent.assign(impact=ns.impact(recent, cfg, now=now)).sort_values("impact", ascending=False)
    tags = sorted({t for ts in h["tags"] for t in ts})
    pick = st.multiselect("Filter by tag", tags, key="news_tags")
    if pick:
        h = h[h["tags"].map(lambda ts: bool(set(ts) & set(pick)))]
    for _, r in h.head(40).iterrows():
        s = r["sentiment"]
        mark = "🟦" if s > 0.3 else ("🟥" if s < -0.3 else "⬜")
        when = f"{r['published']:%d %b %H:%M} UTC" if pd.notna(r["published"]) else ""
        st.markdown(
            f"{mark} **[{r['title']}]({r['link']})**  \n<small>{r['source']} · {when} · sentiment {s:+.2f} · "
            f"novelty {r['novelty']:.2f} · impact {r['impact']:.2f} · {' · '.join(r['tags'])}</small>",
            unsafe_allow_html=True,
        )

with st.expander("Latest headlines, live, not yet scored"):
    df, failed = _live()
    tagged = df[df["tags"].map(bool)]
    for _, r in tagged.head(60).iterrows():
        when = f"{r['published']:%d %b %H:%M} UTC" if pd.notna(r["published"]) else ""
        st.markdown(
            f"**[{r['title']}]({r['link']})**  \n<small>{r['source']} · {when} · {' · '.join(r['tags'])}</small>",
            unsafe_allow_html=True,
        )
    st.caption(
        f"{len(df)} headlines in the last 72 hours, {len(tagged)} about the holdings or the macro themes."
        + (f" Feeds unavailable now: {', '.join(failed)}." if failed else "")
    )
st.caption(
    "Headlines link to their publishers; only the title, time and link are kept. Reuters and Bloomberg publish no "
    "public feed: their headlines come through Google News."
)
footer()
