import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import chart, footer, header, show_status, sidebar_controls, theme
from macro import plotting as pl
from portfolio_ui import DISCLAIMER, SLEEVE_COLOR, SLEEVE_LABEL, bundle, by_sleeve, name

header(
    "Portfolio",
    "Systematic balanced portfolio against a 60/40 global benchmark: what the rules hold today and what they "
    "would trade.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()
cfg = b["config"]
w = b["target"][b["target"] > 1e-4].sort_values(ascending=False)
m = b["metrics"]

if b["stale"]:
    show_status("critical", f"Stale prices, trading frozen in: {', '.join(b['stale'])}.")
if not cfg["live"].get("trading_enabled", True):
    show_status("critical", "Kill switch on (config/portfolio.yaml): the paper book is frozen.")
if b["overlay_state"]:
    show_status(
        "warning",
        f"Drawdown overlay engaged (level {b['overlay_state']}): risk cut to "
        f"{cfg['model']['drawdown_overlay']['levels'][b['overlay_state'] - 1]['scale']:.0%} of the benchmark's.",
    )

c = st.columns(5)
r = b["risk"]
c[0].metric(
    "Ex-ante volatility",
    f"{r['volatility']:.1%}",
    f"benchmark {r['benchmark volatility']:.1%}",
    delta_color="off",
)
c[1].metric("Tracking error", f"{r['tracking error']:.1%}")
c[2].metric("Weekly VaR 95%", f"{r['VaR 95% (1 week)']:.1%}")
c[3].metric("Semiconductors", f"{by_sleeve(b, w).get('semis', 0):.1%}", "sleeve 5-15%", delta_color="off")
nav = b["paper_nav"]
c[4].metric(
    "Paper NAV",
    f"{nav.iloc[-1]:.4f}" if not nav.empty else "not started",
    f"drawdown {b['paper_drawdown']:.1%}" if not nav.empty else f"first rebalance {cfg['live']['start']}",
    delta_color="off",
)

left, right = st.columns([3, 2])
with left:
    st.subheader("Target weights")
    tab = pd.DataFrame(
        {
            "holding": [name(b, a) for a in w.index],
            "weight": w.to_numpy(),
            "benchmark": b["w_eq"].reindex(w.index).fillna(0).to_numpy(),
            "risk share": b["risk"]["risk contribution"].reindex(w.index).fillna(0).to_numpy(),
        },
        index=w.index,
    )
    tab["active"] = tab["weight"] - tab["benchmark"]
    st.dataframe(
        tab.style.format(
            {"weight": "{:.1%}", "benchmark": "{:.1%}", "active": "{:+.1%}", "risk share": "{:.0%}"}
        ),
        use_container_width=True,
        height=36 * (len(tab) + 1),
    )
    st.caption(
        "Benchmark: the 60/40 ACWI/AGG benchmark mapped onto the universe (the Black-Litterman equilibrium). "
        "Risk share: contribution to the portfolio's ex-ante variance. "
        f"Optimiser: {b['target_status']}. Data to {b['as_of']:%d %b %Y} (weekly closes)."
    )
with right:
    sl = by_sleeve(b, w)
    fig = go.Figure(
        go.Pie(
            labels=[SLEEVE_LABEL[s] for s in sl.index],
            values=sl.to_numpy(),
            hole=0.55,
            sort=False,
            marker={"colors": [SLEEVE_COLOR[s] for s in sl.index]},
        )
    )
    pl.base_layout(fig, "By sleeve", "Macro Tightening Monitor", f"{b['as_of']:%Y-%m-%d}", th, height=360)
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

st.subheader("Paper trades at the next rebalance")
tr = b["trades"]
tr = tr[tr["action"] != "hold"]
due = b["rebalance_due"]
if b["current"].empty:
    st.markdown(
        f"The paper book starts on **{cfg['live']['start']}**: the first rebalance buys the target weights below."
    )
st.markdown(
    f"Next paper rebalance: **{due}** (tonight's refresh)."
    if due
    else "No rebalance due: the book rebalances on the first refresh of each month, or when the drawdown overlay changes."
)
if not tr.empty:
    st.dataframe(
        tr.assign(holding=[name(b, a) for a in tr.index])[
            ["holding", "current", "target", "trade", "action"]
        ].style.format({"current": "{:.1%}", "target": "{:.1%}", "trade": "{:+.1%}"}),
        use_container_width=True,
    )
st.caption(f"Trades below {cfg['model']['no_trade_band']:.1%} of NAV are skipped (no-trade band).")

if not nav.empty:
    bench = b["benchmark"]
    bn = (1 + bench.loc[nav.index[0] :]).cumprod()
    df = pd.DataFrame({"paper portfolio": nav, "benchmark 60/40": bn.reindex(nav.index, method="ffill")})
    fig = pl.line_chart(
        df,
        "Paper NAV since the first rebalance",
        "Macro Tightening Monitor",
        f"{nav.index[-1]:%Y-%m-%d}",
        yaxis="NAV",
        theme=th,
    )
    chart(fig, df, key="pf_nav", full_history=True)

full = m["full model"]
st.markdown(
    f"**Simulated since {b['benchmark'].index[0]:%Y}** (walk-forward, net of costs): {full['annual return']:.1%} a year, "
    f"maximum drawdown {full['max drawdown']:.1%} against {m.loc['max drawdown', 'benchmark 60/40']:.1%} for the "
    f"benchmark, Sharpe {full['Sharpe']:.2f} against {m.loc['Sharpe', 'benchmark 60/40']:.2f}. Details: Backtest."
)
st.caption(DISCLAIMER)
footer()
