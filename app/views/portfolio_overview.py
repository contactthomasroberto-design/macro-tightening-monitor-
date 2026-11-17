import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import chart, footer, header, show_status, sidebar_controls, theme
from macro import plotting as pl
from portfolio_ui import DISCLAIMER, SLEEVE_COLOR, SLEEVE_LABEL, bundle, by_sleeve, name, sleeve

header(
    "Portfolio",
    "Systematic multi-asset alternative fund, long and short across about fifty global instruments, against a "
    "60/40 benchmark: what the rules hold today and what they would trade.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()
cfg = b["config"]
w = b["target"][b["target"].abs() > 1e-4].sort_values(ascending=False)
m = b["metrics"]

if b["stale"]:
    show_status("critical", f"Stale prices, rebalance frozen in: {', '.join(b['stale'])}.")
if not cfg["live"].get("trading_enabled", True):
    show_status("critical", "Kill switch on (config/portfolio.yaml): the paper book is frozen.")
if b["overlay_state"]:
    lv = cfg["model"]["drawdown_overlay"]["levels"][b["overlay_state"] - 1]
    show_status(
        "warning",
        f"Drawdown overlay engaged (level {b['overlay_state']}): risk cap at {lv['scale']:.0%} of the benchmark's.",
    )

r = b["risk"]
c = st.columns(6)
c[0].metric(
    "Gross exposure", f"{b['gross']:.0%}", f"cap {cfg['sleeves']['gross_max']:.0%}", delta_color="off"
)
c[1].metric("Net equity", f"{b['net_equity']:.0%}", "benchmark 60%", delta_color="off")
c[2].metric(
    "Ex-ante volatility",
    f"{r['volatility']:.1%}",
    f"benchmark {r['benchmark volatility']:.1%}",
    delta_color="off",
)
c[3].metric("Tracking error", f"{r['tracking error']:.1%}")
c[4].metric("Weekly VaR 95%", f"{r['VaR 95% (1 week)']:.1%}")
nav = b["paper_nav"]
c[5].metric(
    "Paper NAV",
    f"{nav.iloc[-1]:.4f}" if not nav.empty else "not started",
    f"drawdown {b['paper_drawdown']:.1%}" if not nav.empty else f"from {cfg['live']['start']}",
    delta_color="off",
)
h = b.get("hedge_now") or {}
if h:
    st.caption(
        f"Tail hedge at the next monthly roll: {h['hedge ratio']:.0%} of net equity in one-month 5% out-of-the-money "
        f"S&P 500 puts ({h['hedged share of NAV']:.0%} of NAV), premium {h['premium (% of NAV)']:.2%} of NAV at a VIX of "
        f"{h['VIX']:.1f} (research log H34)."
    )


def book(x: pd.Series) -> pd.DataFrame:
    t = pd.DataFrame(
        {
            "holding": [name(b, a) for a in x.index],
            "sleeve": [SLEEVE_LABEL.get(sleeve(b, a), "") for a in x.index],
            "weight": x.to_numpy(),
            "benchmark": b["w_eq"].reindex(x.index).fillna(0).to_numpy(),
            "risk share": b["risk"]["risk contribution"].reindex(x.index).fillna(0).to_numpy(),
        },
        index=x.index,
    )
    return t.assign(active=t["weight"] - t["benchmark"])


fmt = {"weight": "{:+.1%}", "benchmark": "{:.1%}", "active": "{:+.1%}", "risk share": "{:.0%}"}
left, right = st.columns([3, 2])
with left:
    st.subheader(f"Long book ({(w > 0).sum()} lines, {w[w > 0].sum():.0%})")
    lb = book(w[w > 0])
    st.dataframe(lb.style.format(fmt), use_container_width=True, height=36 * (len(lb) + 1))
    sh = w[w < 0].sort_values()
    st.subheader(f"Short book ({len(sh)} lines, {sh.sum():.0%})")
    if sh.empty:
        st.markdown("No short position today.")
    else:
        st.dataframe(book(sh).style.format(fmt), use_container_width=True, height=36 * (len(sh) + 1))
    st.caption(
        "Benchmark: 60/40 ACWI/AGG mapped onto the universe (the Black-Litterman equilibrium). Risk share: "
        f"contribution to the ex-ante variance. Optimiser: {b['target_status']}. Weekly closes to {b['as_of']:%d %b %Y}."
    )
with right:
    sl = by_sleeve(b, w)
    fig = go.Figure(
        go.Bar(
            y=[SLEEVE_LABEL[s] for s in sl.index][::-1],
            x=sl.to_numpy()[::-1],
            orientation="h",
            marker_color=[SLEEVE_COLOR[s] for s in sl.index][::-1],
            text=[f"{v:+.0%}" for v in sl.to_numpy()[::-1]],
            textposition="outside",
        )
    )
    pl.base_layout(
        fig, "Net exposure by sleeve", "Macro Tightening Monitor", f"{b['as_of']:%Y-%m-%d}", th, height=420
    )
    fig.update_xaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
    ex = b.get("exposures")
    if ex is not None and len(ex):
        st.markdown("**Factor betas (3 years, weekly)**")
        st.dataframe(
            ex.rename(
                {
                    "SPY": "US equities",
                    "IEF": "Treasuries 7-10y",
                    "UUP": "US dollar",
                    "DBC": "Commodities",
                    "GLD": "Gold",
                }
            )
            .rename("beta")
            .to_frame()
            .style.format("{:+.2f}"),
            use_container_width=True,
        )

st.subheader("Paper trades at the next rebalance")
tr = b["trades"]
tr = tr[tr["action"] != "hold"]
due = b["rebalance_due"]
if b["current"].empty:
    st.markdown(
        f"The paper book starts on **{cfg['live']['start']}**: the first rebalance builds the positions below."
    )
st.markdown(
    f"Next paper rebalance: **{due}** (tonight's refresh)."
    if due
    else "No rebalance due: the book rebalances every week, and at once when the drawdown overlay changes."
)
if not tr.empty:
    st.dataframe(
        tr.assign(holding=[name(b, a) for a in tr.index])[
            ["holding", "current", "target", "trade", "action"]
        ].style.format({"current": "{:+.1%}", "target": "{:+.1%}", "trade": "{:+.1%}"}),
        use_container_width=True,
    )
st.caption(
    f"Trades below {cfg['model']['no_trade_band']:.2%} of NAV are skipped; costs and borrow are in the optimiser's objective."
)

if not nav.empty:
    bn = (1 + b["benchmark"].loc[nav.index[0] :]).cumprod()
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
    f"**Simulated since {b['benchmark'].index[0]:%Y}** (walk-forward, weekly, net of costs, borrow and hedge): "
    f"{full['annual return']:.1%} a year, maximum drawdown {full['max drawdown']:.1%} against "
    f"{m.loc['max drawdown', 'benchmark 60/40']:.1%} for the benchmark, Sharpe {full['Sharpe']:.2f} against "
    f"{m.loc['Sharpe', 'benchmark 60/40']:.2f}. Details: Backtest."
)
st.subheader("Performance by period")
perf = b.get("performance")
if perf is not None and not perf.empty:
    st.dataframe(perf.style.format("{:+.2%}", na_rep="—"), use_container_width=True)
    cal = b.get("calendar_returns")
    if cal is not None and not cal.empty:
        st.markdown("**By year and month (model, walk-forward backtest; current year to date)**")
        st.dataframe(
            cal.style.format("{:+.1%}", na_rep="").map(
                lambda v: "" if pd.isna(v) else ("color: #1a7f37" if v > 0 else "color: #cf222e")
            ),
            use_container_width=True,
        )
    st.caption(
        "Returns in USD after trading costs, borrow and the tail hedge. The model column is the 20-year walk-forward "
        "backtest (weekly rebalance, no look-ahead); the paper book column appears once the paper book has started "
        f"({cfg['live']['start']}). Backtest returns are hypothetical and overstate what a real fund would have earned."
    )
st.caption(DISCLAIMER)
footer()
