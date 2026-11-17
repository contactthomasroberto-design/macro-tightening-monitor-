"""Strategy: is it relevant, and is it improving? The committee's verdicts, the evidence, its evolution over
time, the tested hypotheses, the model versions and the monthly factsheet."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import footer, header, sidebar_controls, theme
from macro import strategy as sg
from markets_ui import NAVY
from portfolio_ui import DISCLAIMER, bundle

header(
    "Strategy",
    "Is the strategy relevant in today's market, and is it improving? Verdicts, evidence and evolution.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()


@st.cache_data(ttl=600, show_spinner=False)
def _load():
    return sg.reviews(), sg.read_metrics(), sg.hypotheses(), sg.versions()


rv, mt, hy, vs = _load()

# ------------------------------------------------------------------ 1. verdict
st.subheader("Investment committee verdict")
if rv.empty:
    st.info("The first strategy review is written by tonight's committee (docs/research/strategy/).")
else:
    last = rv.iloc[-1]
    v = str(last["verdict"]).lower()
    box = st.success if "pertinente" in v and "revoir" not in v else st.error if "revoir" in v else st.warning
    box(f"**{pd.Timestamp(last['date']):%d %b %Y}** — {last['verdict']}")
    with st.expander("Full review"):
        st.markdown((sg.ROOT / last["file"]).read_text(encoding="utf-8"))
    if len(rv) > 1:
        with st.expander(f"Previous verdicts ({len(rv) - 1})"):
            st.dataframe(rv.iloc[:-1][::-1][["date", "verdict"]], hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ 2. evidence
st.subheader("The evidence")
m = b["metrics"]
full, bench = m["full model"], m["benchmark 60/40"]
row = sg.metrics_row(b, "")
c = st.columns(5)
c[0].metric("Sharpe", f"{full['Sharpe']:.2f}", f"60/40 {bench['Sharpe']:.2f}", delta_color="off")
c[1].metric(
    "Max drawdown", f"{full['max drawdown']:.1%}", f"60/40 {bench['max drawdown']:.1%}", delta_color="off"
)
c[2].metric(
    "Sharpe without 2026 picks",
    "—" if pd.isna(row["survivorship-free Sharpe"]) else f"{row['survivorship-free Sharpe']:.2f}",
    help="Quant lab H39: semiconductors through SOXX only, no names chosen in 2026.",
)
c[3].metric(
    "Deflated Sharpe",
    "—" if pd.isna(row["DSR model variants"]) else f"{row['DSR model variants']:.2f}",
    "proof of skill above 0.95",
    delta_color="off",
    help="Probability that the Sharpe ratio is not luck, given the number of variants tried.",
)
c[4].metric(
    "Overfitting probability",
    "—" if pd.isna(row["PBO"]) else f"{row['PBO']:.0%}",
    "acceptable below 50%",
    delta_color="off",
)
nav = b.get("paper_nav", pd.Series(dtype=float))
st.caption(
    "Backtest walk-forward since 2005, weekly, net of costs: hypothetical. "
    + (
        f"Paper book since {nav.index[0]:%d %b %Y}: {nav.iloc[-1] - 1:+.2%}."
        if len(nav)
        else f"The paper book starts on {b['config']['live']['start']}: from then on, it is the only real evidence."
    )
)
fb = b.get("fund_benchmarks")
if isinstance(fb, pd.DataFrame) and not fb.empty:
    with st.expander("Against funds one can buy (DBMF, RPAR, QAI, HDG)"):
        st.dataframe(
            fb.drop(index=["first week", "weeks"], errors="ignore")
            .astype(float)
            .T.style.format("{:.2f}", na_rep="—"),
            use_container_width=True,
        )

# ------------------------------------------------------------------ 3. evolution
st.subheader("Evolution")
if len(mt) < 2:
    st.caption(
        "The evolution is recorded once a day from now on (archive/strategy_metrics.csv); the chart appears after two days."
    )
else:
    mt = mt.assign(date=pd.to_datetime(mt["date"]))
    fig = go.Figure()
    fig.add_scatter(
        x=mt["date"], y=mt["Sharpe"], name="Sharpe (fund)", line=dict(color=f"rgb{NAVY}", width=2)
    )
    fig.add_scatter(
        x=mt["date"], y=mt["benchmark Sharpe"], name="Sharpe (60/40)", line=dict(color="#9aa5b1", dash="dot")
    )
    if mt["survivorship-free Sharpe"].notna().any():
        fig.add_scatter(
            x=mt["date"],
            y=mt["survivorship-free Sharpe"],
            name="Sharpe without 2026 picks",
            line=dict(color="#c97b2a"),
        )
    if mt["DSR model variants"].notna().any():
        fig.add_scatter(
            x=mt["date"], y=mt["DSR model variants"], name="Deflated Sharpe", line=dict(color="#2a9d8f")
        )
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    first, now = mt.iloc[0], mt.iloc[-1]
    comp = pd.DataFrame(
        {
            f"{first['date']:%d %b %Y} (v{first['version']})": first,
            f"{now['date']:%d %b %Y} (v{now['version']})": now,
        }
    ).loc[
        ["annual return", "Sharpe", "max drawdown", "survivorship-free Sharpe", "DSR model variants", "PBO"]
    ]
    st.dataframe(comp.astype(float).style.format("{:.3f}", na_rep="—"), use_container_width=True)

# ------------------------------------------------------------------ 4. hypotheses
st.subheader("What we tested")
if hy.empty:
    st.caption("No quant-lab verdict yet.")
else:
    ok, ko = hy[hy["verdict"] == "validée"], hy[hy["verdict"] == "rejetée"]
    c = st.columns(2)
    c[0].markdown(
        f"**Validated ({len(ok)})**\n\n" + ("\n".join(f"- {h}" for h in ok["hypothesis"]) or "- none")
    )
    c[1].markdown(
        f"**Rejected ({len(ko)})**\n\n" + ("\n".join(f"- {h}" for h in ko["hypothesis"]) or "- none")
    )
    st.caption(
        "Pre-registered before any test (docs/research_log.md). A rejected idea stays out of the model; a validated "
        "one becomes a dated version proposal, decided by the owner."
    )
    with st.expander("Verdict history by hypothesis"):
        st.dataframe(hy, hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ 5. versions and factsheet
if not vs.empty:
    with st.expander(f"Model versions ({len(vs)})"):
        st.dataframe(vs[::-1], hide_index=True, use_container_width=True)
sheets = sorted(sg.FACTSHEETS.glob("*.md"))
st.subheader("Monthly factsheet")
if not sheets:
    st.caption("Written by GitHub at every refresh from now on (docs/factsheets/).")
else:
    pick = st.selectbox("Month", [p.stem for p in sheets][::-1])
    text = (sg.FACTSHEETS / f"{pick}.md").read_text(encoding="utf-8")
    st.download_button("Download (Markdown)", text, file_name=f"factsheet-{pick}.md")
    with st.expander("Read", expanded=True):
        st.markdown(text)
st.caption(DISCLAIMER)
footer()
