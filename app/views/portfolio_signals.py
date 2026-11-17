import pandas as pd
import streamlit as st

from components import chart, footer, header, show_status, sidebar_controls, theme
from macro import plotting as pl
from portfolio_ui import DISCLAIMER, bundle, name, score_css

header(
    "Signals and tests",
    "Company-level scores for the semiconductor sleeve, and the pre-registered tests of each signal.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()

st.subheader("Semiconductor scorecard (−1 to +1)")
mt = b["micro_table"]
if not mt.empty:
    mt = mt.assign(**{"micro score": mt.mean(axis=1), "weight": b["target"].reindex(mt.index).fillna(0)})
    mt.index = [name(b, a) for a in mt.index]
    st.dataframe(
        mt.style.format(
            {c: "{:+.2f}" for c in mt.columns if c != "weight"} | {"weight": "{:.1%}"}, na_rep=""
        ).map(score_css, subset=[c for c in mt.columns if c != "weight"]),
        use_container_width=True,
    )
    st.caption(
        "Momentum and low volatility: ranks within the sleeve. Memory cycle (SK Hynix, Samsung, Micron): "
        "acceleration of Micron's trailing-12-month revenue growth, dated at the SEC filing; Micron reports a "
        "month before the Korean makers and is the cleanest free read of the memory cycle. Revenue growth: US filers "
        "only (SEC EDGAR). Korean fundamentals need a free OpenDART key (not yet wired). Sleeve 5-15%, 5% per name, "
        "SK Hynix and Samsung at least 1.5% each: the conviction is the owner's; the model sizes inside it."
    )

st.subheader("Pre-registered signal tests")
tests = b["tests"]
for k, t in tests.items():
    if t["n"] < 8:
        show_status("warning", f"{k}: not enough data yet ({t['n']} observations).")
        continue
    ok = t["t"] > 2
    show_status(
        "good" if ok else "warning",
        f"{k}: IC {t['IC']:+.2f}, t = {t['t']:+.1f}, {t['n']} non-overlapping observations — "
        + ("signal supported." if ok else "no reliable signal."),
    )
if not tests:
    show_status("warning", "Fundamentals or news tone not available yet (SEC_CONTACT secret, GDELT).")
st.caption(
    "H29: memory cycle against the memory basket's 13-week return relative to the semiconductor index. H30: weekly "
    "news tone against the next 4 weeks; the news family keeps a zero weight unless t > 2. Spearman rank "
    "correlation; samples spaced by the horizon so that observations do not overlap."
)

tone = {k.replace("NEWS_TONE_", "").title(): v.resample("W-FRI").mean() for k, v in b["tone"].items()}
if tone:
    df = pd.DataFrame(tone).dropna(how="all")
    fig = pl.line_chart(
        df,
        "News tone, weekly average (GDELT)",
        "GDELT Project",
        f"{df.index[-1]:%Y-%m-%d}",
        yaxis="tone",
        theme=th,
    )
    chart(fig, df, key="pf_tone")
mh = b["macro_history"]
if not mh.empty:
    fig = pl.line_chart(
        mh.dropna(how="all"),
        "Macro factors feeding the views",
        "Macro Tightening Monitor",
        f"{mh.index[-1]:%Y-%m-%d}",
        yaxis="scaled −1 to +1",
        theme=th,
        hline=0,
    )
    chart(fig, mh, key="pf_macro")
st.caption(DISCLAIMER)
footer()
