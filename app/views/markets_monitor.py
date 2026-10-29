import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import chart, footer, header, show_status, sidebar_controls, theme, tradingview_ticker
from macro import plotting as pl
from macro.data import source_label
from macro.markets import REGIMES
from markets_ui import NAVY, RED, adds_to_stress, bundle, dashboard_table, ordinal

header(
    "Cross-asset monitor",
    "What moved, by how much relative to its own history, and how stressed markets are.",
)
ctl = sidebar_controls()
th = theme()
if st.sidebar.toggle("Market ticker (TradingView)", value=True, key="tv_markets"):
    tradingview_ticker()

b = bundle()
d = b["dashboard"]
if d.empty:
    st.warning("No market data available.")
    footer()
    st.stop()
as_of = pd.Timestamp(b["as_of"]).strftime("%Y-%m-%d")

# ------------------------------------------------------------------ headline
stress = b["stress"]
sp = b["regime_spells"]
c1, c2, c3 = st.columns(3)
if stress.value is not None:
    s_now = float(stress.value.iloc[-1])
    s_1m = float(stress.value.iloc[-22]) if len(stress.value) > 22 else float("nan")
    pct = float((stress.value <= s_now).mean() * 100)
    c1.metric("Stress index (z)", f"{s_now:+.2f}", f"{s_now - s_1m:+.2f} over 1 month", delta_color="inverse")
    c1.caption(f"{ordinal(pct)} percentile since {stress.value.index[0]:%Y}")
if sp is not None:
    c2.metric(
        "Cross-asset regime (3 months)", sp["current"], f"since {sp['since']:%d %b %Y}", delta_color="off"
    )
    c2.caption(REGIMES[sp["current"]])
big = d.loc[d["z 1M"].abs().sort_values(ascending=False).index[:3], "z 1M"]
c3.markdown("**Largest 1-month moves**  \n" + "  \n".join(f"{i}: **{z:+.1f}σ**" for i, z in big.items()))
c3.caption("Move over 21 business days divided by the typical 1-month move of the past 3 years.")

# ------------------------------------------------------------------ table
st.subheader("Monitor")
st.dataframe(dashboard_table(d), use_container_width=True, height=36 * (len(d) + 1))
st.caption(
    "Yields and spreads: levels in % or bp, moves in bp. Prices: log returns in %. Volatility indices: points. "
    "σ shading: red when the move adds to risk aversion (spreads or volatility up, equities down, dollar up), "
    "navy otherwise. Level percentile over 10 years (3 years for the ICE BofA spreads: FRED serves only their "
    "last three years). 'Stale' marks a series three or more business days behind the newest one. "
    + source_label(*d["id"].tolist())
)

# ------------------------------------------------------------------ z-scores chart
z = d["z 1M"].dropna().sort_values()
fig = go.Figure(
    go.Bar(
        x=z.values,
        y=z.index,
        orientation="h",
        marker_color=[
            f"rgb{RED}" if adds_to_stress(v, int(d.loc[i, "risk"])) else f"rgb{NAVY}" for i, v in z.items()
        ],
        text=[f"{v:+.1f}" for v in z.values],
        textposition="outside",
    )
)
fig.add_vline(x=0, line_width=1, line_color=pl.THEMES[th]["muted"])
for x in (-2, 2):
    fig.add_vline(x=x, line_width=1, line_dash="dot", line_color=pl.THEMES[th]["muted"])
top = z.abs().idxmax()
pl.base_layout(
    fig,
    f"1-month moves in standard deviations: largest is {top} ({z[top]:+.1f}σ)",
    "Macro Tightening Monitor calculations on the series above",
    as_of,
    th,
    height=40 + 24 * len(z) + 120,
)
fig.update_xaxes(title_text="standard deviations of 1-month moves (past 3 years)")
st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

# ------------------------------------------------------------------ stress
st.subheader("Stress index")
if stress.value is not None:
    comp = stress.extra["components"]
    df = pd.concat({"Composite": stress.value, **{c: comp[c] for c in comp}}, axis=1)
    fig = pl.line_chart(
        df.resample("W-FRI").last(),
        f"Market stress is {'above' if s_now > 0 else 'below'} its 5-year norm ({s_now:+.2f} standard deviations)",
        source_label(*stress.sources) + "; rolling 5-year z-scores, equal weights",
        stress.as_of,
        yaxis="z-score",
        theme=th,
        hline=0,
    )
    chart(fig, df, key="stress")
    contrib = stress.extra["contributions"]
    st.caption(
        "Contributions to the latest reading: "
        + ", ".join(f"{k} {v:+.2f}" for k, v in contrib.sort_values(ascending=False).items())
        + ". Components with long histories only: the ICE BofA spreads are left out of the index because "
        "FRED serves only their last three years."
    )
    chk = b["stress_check"]
    if chk is not None and not chk.empty:
        best = float(chk["corr (4-week changes)"].max())
        show_status(
            "good" if best >= 0.5 else "warning",
            "Validation against published stress indices (weekly): "
            + "; ".join(
                f"{k}: {r['corr (levels)']:.2f} in levels, {r['corr (4-week changes)']:.2f} in 4-week changes "
                f"({r['weeks']} weeks)"
                for k, r in chk.iterrows()
            ),
        )
footer()
