import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import chart, footer, header, sidebar_controls, theme
from macro import plotting as pl
from macro.data import source_label
from macro.markets import CORR_PAIRS, REGIMES
from markets_ui import bundle

header(
    "Cross-asset regimes",
    "Growth and rates quadrants, and how the main cross-asset correlations behave now.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()
reg = b["regime"]
sp = b["regime_spells"]
as_of = pd.Timestamp(b["as_of"]).strftime("%Y-%m-%d")
COLORS = {"Goldilocks": "#5b8db8", "Reflation": "#1f3a5f", "Rates shock": "#a52a2a", "Risk-off": "#8c8c8c"}

# ------------------------------------------------------------------ quadrant
st.subheader("Regime: equities and yields over the last 3 months")
if sp is not None:
    st.markdown(
        f"Current regime: **{sp['current']}** since {sp['since']:%d %B %Y} ({sp['days']} business days): "
        f"{REGIMES[sp['current']]}."
    )
    st.caption(
        "Each day is classified by the sign of the S&P 500's 63-day log return and of the 63-day change in the "
        "10-year Treasury yield. Rule fixed in advance, no estimation. " + source_label("SPX", "DGS10")
    )
    r = reg.loc[ctl["start"] :]
    fig = go.Figure()
    for name, col in COLORS.items():
        m = (r == name).astype(float).where(r == name)
        fig.add_trace(go.Bar(x=m.index, y=m.values, name=name, marker_color=col, marker_line_width=0))
    fig.update_layout(barmode="stack", bargap=0)
    fig.update_yaxes(visible=False)
    pl.base_layout(
        fig,
        f"Cross-asset regime by day: now {sp['current']}",
        source_label("SPX", "DGS10"),
        as_of,
        th,
        height=260,
    )
    chart(fig, reg.rename("regime").to_frame(), key="regime_hist")

    share = (sp["share"] * 100).round(0).astype(int)
    st.caption(
        "Share of days since the start of the sample: " + ", ".join(f"{k} {v}%" for k, v in share.items())
    )


# ------------------------------------------------------------------ correlations
st.subheader("Rolling correlations (3 months, daily changes)")
ct = b["correlation_table"]
if not ct.empty:
    st.dataframe(
        ct.style.format("{:+.2f}", subset=["current (3M)", "1y low", "1y high", "10y average"]).format(
            "{:.0f}", subset=["percentile 10y"]
        ),
        use_container_width=True,
    )
    readings = {p.name: p.reading for p in CORR_PAIRS}
    st.caption(" · ".join(f"**{k}**: {v}" for k, v in readings.items() if k in ct.index))
    corrs = pd.concat(b["correlations"], axis=1)
    sb = corrs[["Stock-bond"]] if "Stock-bond" in corrs else corrs.iloc[:, :1]
    sb = sb.dropna()
    v = float(sb.iloc[-1, 0])
    fig = pl.line_chart(
        sb.resample("W-FRI").last(),
        f"Stock-bond correlation {v:+.2f}: bonds {'do not hedge' if v > 0 else 'hedge'} equities at the moment",
        source_label("SPX", "DGS10")
        + "; 63-day correlation of daily returns, bond return = minus the yield change",
        as_of,
        yaxis="correlation",
        theme=th,
        hline=0,
    )
    chart(fig, sb, key="stockbond")
    others = corrs.drop(columns=sb.columns)
    fig = pl.small_multiples(
        others.resample("W-FRI").last(),
        "Other cross-asset correlations",
        "Macro Tightening Monitor calculations; 63-day correlation of daily changes",
        as_of,
        ncols=3,
        hline=0,
        theme=th,
    )
    chart(fig, others, key="corrs")
footer()
