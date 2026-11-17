import pandas as pd
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

rb = b.get("risk_budget")
if rb is not None and not rb.empty:
    st.subheader("Risk budget by return source")
    fig = go.Figure()
    for col, op in (("ex-ante share", 1.0), ("realised share (3y)", 0.45)):
        fig.add_bar(y=rb.index, x=rb[col], orientation="h", name=col, marker_color=f"rgba{(*NAVY, op)}")
    pl.base_layout(
        fig,
        "Share of portfolio variance by return source",
        "Macro Tightening Monitor",
        f"{b['as_of']:%Y-%m-%d}",
        th,
        height=120 + 34 * len(rb),
    )
    fig.update_layout(barmode="group")
    fig.update_xaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
    with st.expander("Risk budget table"):
        st.dataframe(rb.style.format("{:.1%}"), use_container_width=True)
    st.caption(
        "Euler contributions (weight × marginal risk) summed by source; the shares add up to 100%, a negative share "
        "is a source that hedges the rest. Ex ante with the model covariance, realised with the sample covariance of "
        "the last 3 years. Sources follow the sleeve of each line (config/portfolio.yaml, risk_sources overrides)."
    )


def _style_table(res: dict):
    return res["loadings"].style.format({"loading": "{:+.2f}", "t-stat": "{:+.1f}"})


se, ad = b.get("style_exposures"), b.get("alpha_decomposition")
if se and not se["loadings"].empty:
    exp = st.expander("Style exposures and alpha after styles (H46)")
    c = exp.columns(2)
    with c[0]:
        st.markdown("**Today's weights** (last 3 years, excess of T-bills)")
        st.dataframe(_style_table(se), use_container_width=True)
        st.caption(f"R² {se['R²']:.0%} over {se['weeks']} weeks.")
    if ad and not ad["loadings"].empty:
        with c[1]:
            st.markdown("**Backtest active return** (versus the 60/40)")
            st.dataframe(_style_table(ad), use_container_width=True)
            st.caption(
                f"Alpha after styles {ad['alpha (annual)']:+.1%} a year (t {ad['alpha t']:+.1f}), "
                f"R² {ad['R²']:.0%}, {ad['weeks']} weeks (research log H46)."
            )
    exp.caption(
        "Weekly regression on long-short factors built from ETFs: market (S&P 500 minus T-bills), value, momentum, "
        "quality, equal weight and minimum volatility (each minus the S&P 500); Newey-West t-statistics. A return "
        "explained by these loadings could be bought with ETFs: only the alpha is the model's own."
    )


def _bars(df: pd.DataFrame, title: str, limit: float | None = None) -> None:
    """Fund vs benchmark loss per scenario, horizontal bars, worst first."""
    df = df.sort_values("fund")
    fig = go.Figure()
    fig.add_bar(y=df.index, x=df["fund"], orientation="h", name="Fund", marker_color=f"rgb{NAVY}")
    fig.add_bar(
        y=df.index, x=df["benchmark"], orientation="h", name="Benchmark 60/40", marker_color="#b8c2cc"
    )
    if limit is not None:
        fig.add_vline(
            x=limit, line_dash="dot", line_color="#c0392b", annotation_text="limit", annotation_position="top"
        )
    fig.update_layout(
        barmode="group",
        height=90 + 46 * len(df),
        margin=dict(l=0, r=10, t=30, b=0),
        title=title,
        legend=dict(orientation="h", y=-0.12),
        xaxis_tickformat=".0%",
    )
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})


st.subheader("Stress tests")
fs = b.get("forward_stress")
ep = b["episodes"]
c1, c2 = st.columns(2)
if fs is not None and not fs.empty:
    n_breach = int(fs["breach"].astype(bool).sum())
    with c1:
        (st.error if n_breach else st.success)(
            f"{n_breach} forward scenario(s) beyond the mandate's limits"
            if n_breach
            else "All forward scenarios within limits"
        )
        _bars(
            fs.rename(columns={"book": "fund"})[["fund", "benchmark"]].astype(float),
            "Forward scenarios (loss in % of NAV)",
            float(fs["limit"].astype(float).max()),
        )
if not ep.empty:
    with c2:
        worse = ep[ep["portfolio (current weights)"] < ep["benchmark"]]
        (st.warning if len(worse) else st.success)(
            f"Today's book does worse than the 60/40 in {len(worse)} of {len(ep)} past crises"
            if len(worse)
            else "Today's book beats the 60/40 in every past crisis replayed"
        )
        _bars(
            ep.rename(columns={"portfolio (current weights)": "fund"})[["fund", "benchmark"]].astype(float),
            "Past crises replayed with today's weights",
        )
st.caption(
    "Forward scenarios: hypothetical shocks sized on past episodes (config/stress_scenarios.yaml), other assets move by "
    "their expected co-move, tail-hedge puts pay below their strike. Limits: 15% of NAV and the benchmark's loss plus "
    "2 points; a breach opens an issue for the committee. Correlations rise in crises: read as a central case."
)
with st.expander("Scenario detail"):
    if fs is not None and not fs.empty:
        st.dataframe(
            fs.style.format(
                {
                    "book": "{:+.1%}",
                    "of which tail hedge": "{:+.1%}",
                    "benchmark": "{:+.1%}",
                    "limit": "{:.0%}",
                }
            ),
            use_container_width=True,
        )
    sc = b["scenarios"]
    if not sc.empty:
        st.markdown("**One-week shocks, current weights (%)**")
        st.dataframe(
            sc.rename("portfolio move (%)").to_frame().style.format("{:+.2f}"), use_container_width=True
        )

pms = b.get("post_mortems") or []
st.subheader("Loss reviews")
if not pms:
    st.success("No position has cost more than 1% of NAV over the last four weeks.")
else:
    for pm in pms:
        st.warning(
            f"**{name(b, pm['asset'])}**: {pm['loss']:+.2%} of NAV over 4 weeks. {pm['verdict'].capitalize()}."
        )
    st.caption(
        "Automatic first read; the full review is in docs/research/postmortems/ and completed by the committee."
    )
st.caption(DISCLAIMER)
footer()
