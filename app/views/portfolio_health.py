import pandas as pd
import streamlit as st

from components import chart, footer, header, show_status, sidebar_controls, theme
from macro import fund_checks as fchk
from macro import plotting as pl
from macro.config import ROOT
from portfolio_ui import DISCLAIMER, bundle

header(
    "Model health",
    "Is the machine behaving? Weight stability, risk forecasts against outcomes, limits it leans on, and data checks.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()
h = b.get("health") or {}
if not h:
    st.info("Health indicators arrive with the next portfolio refresh.")
    st.stop()

c = st.columns(4)
c[0].metric(
    "Turnover, last 13 rebalances",
    f"{h['turnover last 13 rebalances']:.1%}",
    f"history {h['turnover all history']:.1%}",
    delta_color="off",
)
c[1].metric(
    "Realised / predicted volatility",
    f"{h['vol bias ratio']:.2f}",
    "1.00 = well calibrated",
    delta_color="off",
)
c[2].metric(
    "Limits relaxed, last 52 weeks",
    f"{h['relaxed last 52']}",
    f"all history {h['relaxed share']:.0%}",
    delta_color="off",
)
c[3].metric("Today's optimiser status", h["target status"])

bias = h["vol bias ratio"]
show_status(
    "good" if 0.8 <= bias <= 1.25 else "warning",
    f"Median ratio of realised to predicted volatility {bias:.2f}: "
    + (
        "the risk model is roughly calibrated."
        if 0.8 <= bias <= 1.25
        else "the risk model under-estimates risk."
        if bias > 1.25
        else "the risk model over-estimates risk."
    ),
)
if h["relaxed last 52"]:
    show_status(
        "warning",
        f"The optimiser had to relax a limit at {h['relaxed last 52']} of the last 52 rebalances: the mandate and "
        "the views pull apart. Each relaxation is in the backtest log (status column).",
    )

st.subheader("Weight stability")
turn = h["turnover"]
if len(turn):
    df = pd.DataFrame(
        {"sum of absolute weight changes": turn, "13-rebalance average": turn.rolling(13).mean()}
    )
    fig = pl.line_chart(
        df,
        "Weight change at each rebalance",
        "Macro Tightening Monitor; backtest",
        f"{df.index[-1]:%Y-%m-%d}",
        yaxis="share of NAV",
        theme=th,
    )
    fig.update_yaxes(tickformat=".0%")
    chart(fig, df, key="pf_health_turn", full_history=True)
    st.caption(
        "Sum over lines of |w(t) − w(t−1)| after the no-trade band (twice the one-way turnover). Spikes are "
        "regime changes or the drawdown overlay; a high level throughout means the signals are noisy."
    )

pvr = h["predicted vs realised"]
if not pvr.empty:
    st.subheader("Predicted against realised volatility")
    fig = pl.line_chart(
        pvr[["predicted", "realised"]],
        "Ex-ante volatility at the rebalance and volatility realised over the next 26 weeks",
        "Macro Tightening Monitor; backtest",
        f"{pvr.index[-1]:%Y-%m-%d}",
        yaxis="annualised volatility",
        theme=th,
    )
    fig.update_yaxes(tickformat=".0%")
    chart(fig, pvr, key="pf_health_vol", full_history=True)
    st.caption(
        "Ex ante: sample covariance of the trailing three years applied to the weights (every fourth rebalance). "
        "Realised: standard deviation of the portfolio's weekly returns over the following 26 weeks."
    )

st.subheader("Limits the portfolio sits on today")
bc = h["binding"]
if not bc.empty:
    on = bc[bc["binding"]]
    st.dataframe(
        bc.set_index("limit").style.format({"value": "{:.3f}", "bound": "{:.3f}"}),
        use_container_width=True,
    )
    st.caption(
        f"{len(on)} limits binding: "
        + (", ".join(on["limit"]) if len(on) else "none")
        + ". A binding limit means the views want more than the mandate allows: the limit, not the model, "
        "sets that exposure."
    )
sc = h["status counts"]
if len(sc):
    st.caption("Optimiser status over the backtest: " + ", ".join(f"{k} {v}" for k, v in sc.items()) + ".")

st.subheader("Paper book against the backtest")
pv = h.get("paper vs backtest") or {}
if pv.get("weeks", 0) >= 2:
    st.dataframe(pd.Series(pv, name="value").to_frame(), use_container_width=True)
else:
    st.caption(
        f"The paper book starts on {b['config']['live']['start']}: the comparison needs at least two weeks of it."
    )

st.subheader("Price anomalies (last 30 days)")
an = fchk.read_anomalies(ROOT / "archive" / "price_anomalies.csv", days=30)
if an.empty:
    st.caption(
        "None recorded. The two-hourly monitor flags daily moves beyond 6 trailing-year standard deviations that "
        "the sector proxy did not share, and same-day closes that differ by more than 2% between Yahoo and Stooq."
    )
else:
    st.dataframe(an[["date", "asset", "kind", "detail"]], use_container_width=True, hide_index=True)
st.caption(DISCLAIMER)
footer()
