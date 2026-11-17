import plotly.graph_objects as go
import streamlit as st

from components import footer, header, sidebar_controls, theme
from macro import plotting as pl
from markets_ui import NAVY
from portfolio_ui import DISCLAIMER, bundle, name

header(
    "Portfolio risk",
    "Where the risk sits, what a bad week costs, and how the current weights fare in shocks.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()
r = b["risk"]

c = st.columns(4)
c[0].metric(
    "Ex-ante volatility",
    f"{r['volatility']:.1%}",
    f"benchmark {r['benchmark volatility']:.1%}",
    delta_color="off",
)
c[1].metric(
    "Tracking error",
    f"{r['tracking error']:.1%}",
    f"cap {b['config']['model']['tracking_error_max']:.0%}",
    delta_color="off",
)
c[2].metric("VaR 95%, 1 week", f"{r['VaR 95% (1 week)']:.1%}")
c[3].metric("Expected shortfall 95%", f"{r['expected shortfall 95% (1 week)']:.1%}")
st.caption(
    "Covariance: Ledoit-Wolf shrinkage on 3 years of weekly USD returns. VaR and expected shortfall: historical "
    "simulation of today's weights over the last 3 years (the 5% worst weeks)."
)

rc = r["risk contribution"].sort_values()
rc = rc[rc.abs() > 0.001]
fig = go.Figure(
    go.Bar(y=[name(b, a) for a in rc.index], x=rc.to_numpy(), orientation="h", marker_color=f"rgb{NAVY}")
)
pl.base_layout(
    fig,
    "Share of portfolio variance by holding",
    "Macro Tightening Monitor",
    f"{b['as_of']:%Y-%m-%d}",
    th,
    height=80 + 24 * len(rc),
)
fig.update_xaxes(tickformat=".0%")
st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

st.subheader("Shocks: one-week moves, current weights")
sc = b["scenarios"]
if not sc.empty:
    st.dataframe(sc.rename("portfolio move (%)").to_frame().style.format("{:+.2f}"), use_container_width=True)
    st.caption(
        "The shocked asset moves by the stated amount; the others move by their expected co-movement given the "
        "covariance (conditional normal). Correlations shift in crises: read as a central case, not a bound "
        "(research log H18, H23)."
    )
ep = b["episodes"]
if not ep.empty:
    st.subheader("Past crises replayed with today's weights")
    ep = ep.assign(difference=ep["portfolio (current weights)"] - ep["benchmark"])
    st.dataframe(ep.style.format("{:+.1%}"), use_container_width=True)
    worse = ep[ep["difference"] < 0]
    st.caption(
        "Actual weekly returns of each holding during the episode (holdings that did not exist yet count as cash)."
        + (
            f" Today's weights would have done worse than the benchmark in: {', '.join(worse.index)}."
            if len(worse)
            else ""
        )
    )
st.caption(DISCLAIMER)
footer()
