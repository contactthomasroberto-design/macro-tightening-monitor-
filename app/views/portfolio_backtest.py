import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import chart, footer, header, show_status, sidebar_controls, theme
from macro import plotting as pl
from macro import portfolio as pf
from portfolio_ui import DISCLAIMER, SLEEVE_COLOR, SLEEVE_LABEL, bundle, sleeve

header(
    "Backtest",
    "Walk-forward simulation since 2005: rebalanced monthly with the data available at each date, net of costs.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()
runs, bench, m = b["backtests"], b["benchmark"], b["metrics"]
full = runs["full model"]["returns"]

dd_ok = m.loc["max drawdown", "full model"] >= m.loc["max drawdown", "benchmark 60/40"]
sh_ok = m.loc["Sharpe", "full model"] >= m.loc["Sharpe", "benchmark 60/40"]
show_status(
    "good" if dd_ok and sh_ok else "warning",
    f"H27: maximum drawdown {m.loc['max drawdown', 'full model']:.1%} against {m.loc['max drawdown', 'benchmark 60/40']:.1%} "
    f"({'no worse' if dd_ok else 'worse'}), Sharpe {m.loc['Sharpe', 'full model']:.2f} against "
    f"{m.loc['Sharpe', 'benchmark 60/40']:.2f} ({'at least equal' if sh_ok else 'lower'}).",
)
show_status(
    "good" if b["deflated_sharpe"] > 0.95 else "warning",
    f"H31: deflated Sharpe ratio of the excess return {b['deflated_sharpe']:.2f} over {b['trials']} configurations "
    "(probability that the edge over the benchmark is not luck from trying several variants; threshold 0.95).",
)

nav = pd.DataFrame(
    {"portfolio": (1 + full).cumprod(), "benchmark 60/40": (1 + bench.reindex(full.index)).cumprod()}
)
fig = pl.line_chart(
    nav,
    "Growth of 1 dollar",
    "Macro Tightening Monitor; weekly, net of costs",
    f"{nav.index[-1]:%Y-%m-%d}",
    yaxis="NAV (log)",
    theme=th,
)
fig.update_yaxes(type="log")
chart(fig, nav, key="pf_bt_nav", full_history=True)
dd = pd.DataFrame({"portfolio": pf.drawdown(full), "benchmark 60/40": pf.drawdown(bench.reindex(full.index))})
fig = pl.line_chart(
    dd,
    "Drawdown from the previous peak",
    "Macro Tightening Monitor",
    f"{dd.index[-1]:%Y-%m-%d}",
    yaxis="drawdown",
    theme=th,
)
fig.update_yaxes(tickformat=".0%")
chart(fig, dd, key="pf_bt_dd", full_history=True)

st.subheader("Metrics, with ablations")
fmt = {
    k: "{:.1%}" for k in ("annual return", "volatility", "max drawdown", "worst 52 weeks", "tracking error")
}
st.dataframe(
    m.T.astype(float).style.format(
        fmt
        | {
            "Sharpe": "{:.2f}",
            "Calmar": "{:.2f}",
            "information ratio": "{:.2f}",
            "beta to benchmark": "{:.2f}",
        },
        na_rep="",
    ),
    use_container_width=True,
)
st.caption(
    "Each ablation reruns the whole simulation without one component (H28: the overlay and trend views should cut "
    "the maximum drawdown by a quarter at a cost below 1 point of annual return). Sharpe over the T-bill rate. "
    "Before ACWI exists (2008) the benchmark uses 0.66 S&P 500 + 0.21 EAFE + 0.13 emerging markets."
)

st.subheader("Against the textbook constructions")
alt = b.get("alternatives")
if alt is not None:
    st.dataframe(
        alt.T.astype(float).style.format(
            fmt
            | {
                "Sharpe": "{:.2f}",
                "Calmar": "{:.2f}",
                "information ratio": "{:.2f}",
                "beta to benchmark": "{:.2f}",
            },
            na_rep="",
        ),
        use_container_width=True,
    )
    st.caption(
        "Same universe, costs and monthly rebalance, no views and no constraints beyond long-only: equal weight; "
        "minimum variance; equal risk contribution (Maillard, Roncalli and Teïletche, 2010); hierarchical risk "
        "parity (López de Prado, 2016). They are counted as trials in the deflated Sharpe ratio. A model that "
        "cannot beat them on drawdown and Sharpe after costs adds complexity without value."
    )

st.subheader("Against funds one can buy")
fb = b.get("fund_benchmarks")
if fb is not None and not fb.empty:
    labels = b.get("fund_benchmark_labels", {})
    num = fb.drop(index=["weeks", "first week"], errors="ignore").T.astype(float)
    num.index = [labels.get(k, k) for k in num.index]
    st.dataframe(
        num.style.format(
            fmt
            | {
                "Sharpe": "{:.2f}",
                "Calmar": "{:.2f}",
                "information ratio": "{:.2f}",
                "beta to benchmark": "{:.2f}",
            },
            na_rep="",
        ),
        use_container_width=True,
    )
    st.caption(
        f"Common history of all series: {int(fb.loc['weeks'].iloc[0])} weeks from {fb.loc['first week'].iloc[0]}, "
        "net of each fund's fees (ETF prices with dividends reinvested). Managed futures (DBMF), risk parity "
        "(RPAR) and hedge-fund replication ETFs (QAI, HDG): if the model does no better than products an investor "
        "can simply buy, its complexity does not pay. Funds with less than a year of history are left out."
    )
else:
    st.caption("The fund benchmarks' prices are not loaded yet (next refresh).")

wts = runs["full model"]["weights"]
sl = wts.T.groupby([sleeve(b, a) for a in wts.columns]).sum().T
fig = go.Figure()
for s_ in [x for x in SLEEVE_LABEL if x in sl]:
    fig.add_trace(
        go.Scatter(
            x=sl.index,
            y=sl[s_],
            stackgroup="one",
            name=SLEEVE_LABEL[s_],
            mode="lines",
            line={"width": 0.5, "color": SLEEVE_COLOR[s_]},
            fillcolor=SLEEVE_COLOR[s_],
        )
    )
pl.base_layout(
    fig, "Allocation by sleeve at each rebalance", "Macro Tightening Monitor", f"{sl.index[-1]:%Y-%m-%d}", th
)
fig.update_yaxes(tickformat=".0%")
chart(fig, sl, key="pf_bt_sleeves", full_history=True)
log = runs["full model"]["log"]
st.caption(
    f"{len(log)} rebalances; average one-way turnover {log['turnover'].mean():.1%} per rebalance, costs "
    f"{log['cost'].sum() / (len(full) / 52):.2%} a year. Optimiser status: "
    + ", ".join(f"{k} {v}" for k, v in log["status"].value_counts().items())
    + f". Drawdown overlay engaged at {int((log['overlay'] > 0).sum())} rebalances."
)
st.caption(DISCLAIMER)
footer()
