import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import chart, footer, header, result_meta, show_status, sidebar_controls, theme
from macro import plotting as pl
from macro.data import source_label, try_series
from macro.pipeline import AI_BASKET, transmission_bundle

header("Transmission", "How tightening reaches stocks, bonds, the dollar and rate-sensitive equities.")
ctl = sidebar_controls()
th = theme()


@st.cache_resource(show_spinner="Computing transmission analytics (first run only)…")
def _bundle():
    return transmission_bundle()


b = _bundle()
as_of = pd.Timestamp(b["as_of"]).strftime("%Y-%m-%d")
rec = try_series("USREC")

# ------------------------------------------------------------------ stock-bond correlation
st.subheader("Stock-bond correlation by inflation regime")
sb = b["stock_bond"]
hi = sb.loc["core > 3%"] if "core > 3%" in sb.index else None
title = (
    f"With core inflation above 3%, stocks and bonds move together (correlation {hi['corr']:.2f})"
    if hi is not None and hi["corr"] == hi["corr"] and hi["lower"] > 0
    else "Stock-bond correlation by core-inflation regime"
)
fig = go.Figure(
    go.Bar(
        x=sb.index,
        y=sb["corr"],
        marker_color=[pl.color(k) for k in range(len(sb))],
        error_y={
            "type": "data",
            "symmetric": False,
            "array": sb["upper"] - sb["corr"],
            "arrayminus": sb["corr"] - sb["lower"],
        },
        text=[f"N={n}" for n in sb["n_months"]],
        textposition="outside",
    )
)
fig.update_yaxes(title_text="correlation of monthly equity and bond returns")
pl.base_layout(fig, title, source_label("SPX", "DGS10", "CPILFESL"), as_of, th, height=380)
chart(fig, sb, key="sb")
st.caption(
    "Bond return proxied by minus the monthly change in the 10Y yield; 90% moving-block bootstrap intervals; N = months."
)
roll = b["stock_bond_rolling"].loc[ctl["start"] :]
fig = pl.line_chart(
    roll.to_frame("24m rolling correlation"),
    f"Rolling stock-bond correlation: {roll.iloc[-1]:.2f}",
    source_label("SPX", "DGS10"),
    as_of,
    yaxis="correlation",
    rec=rec,
    theme=th,
    hline=0,
)
chart(fig, roll, key="sb_roll")

# ------------------------------------------------------------------ event study
st.subheader("Event study around policy-rate changes")
kind = st.radio("Event type", ["hike", "cut"], horizontal=True, key="ev_kind")
es = b["event_study"][kind]
n_ev = b["n_events"].get(kind, 0)
names = list(es)
cols = st.columns(3)
for k, name in enumerate(names):
    d = es[name]
    with cols[k % 3]:
        unit = "bp" if "yield" in name else "%"
        f = pl.band_chart(
            d["mean"],
            d["lower"],
            d["upper"],
            f"{name}: {d['mean'].iloc[-1]:+.2f}{unit} by day +5",
            source_label("DFEDTARU", "DGS2", "DGS10", "SPX", "SX5E", "SOX", "DTWEXBGS"),
            as_of,
            name="mean",
            band_name="90% CI",
            theme=th,
            hline=0,
        )
        f.update_xaxes(title_text="business days around the decision")
        f.update_layout(height=320)
        chart(f, d, key=f"ev_{kind}_{k}")
st.caption(
    f"N = {n_ev} {kind}s detected from changes in the target rate. Cumulative change from day −6; 90% bootstrap intervals "
    "over events. Changes are not surprises: many were fully priced (see the local projections below)."
)

# ------------------------------------------------------------------ real-yield sensitivity
st.subheader("How duration-like are equities?")
bt = b["real_betas"]
allr = bt[bt["regime"] == "all"].set_index("asset")
fig = go.Figure(
    go.Bar(
        x=allr.index,
        y=allr["b_real"],
        marker_color=[pl.color(k) for k in range(len(allr))],
        error_y={"type": "data", "array": 1.645 * allr["se_real"]},
    )
)
fig.update_yaxes(title_text="% return per +1pp real yield")
most = allr["b_real"].idxmin()
pl.base_layout(
    fig,
    f"Most real-yield sensitive: {most} ({allr.loc[most, 'b_real']:.1f}% per +1pp)",
    source_label("SPX", "SOX", "DFII10", "T10YIE", *AI_BASKET),
    as_of,
    th,
    height=380,
)
chart(fig, bt, key="real_betas")
st.dataframe(bt.round(2), use_container_width=True, hide_index=True)
st.caption(
    "Weekly returns on weekly changes in the 10Y TIPS yield and the 10Y breakeven, HAC s.e., full sample and by core-inflation "
    "regime. AI leaders = equal-weight NVDA, MSFT, GOOGL, AMZN, META over the dates each is listed (Yahoo, personal-use terms)."
)
rb = b["rolling_betas"]
sel = st.selectbox("Rolling beta for", list(rb), key="rb_sel")
r = rb[sel].loc[ctl["start"] :]
fig = pl.band_chart(
    r["b_real"],
    r["lower"],
    r["upper"],
    f"{sel}: rolling 1-year real-yield beta",
    source_label("DFII10", "T10YIE"),
    as_of,
    name="β real",
    band_name="90% band",
    theme=th,
    hline=0,
)
chart(fig, r, key="rb_chart")

# ------------------------------------------------------------------ local projections
st.subheader("Responses to a policy-surprise proxy")
lp = b["lp"]
cols = st.columns(len(lp)) if lp else []
for (name, d), c in zip(lp.items(), cols, strict=True):
    with c:
        unit = "bp" if "yield" in name else "%"
        f = pl.band_chart(
            d["beta"],
            d["lower"],
            d["upper"],
            f"{name}: {d['beta'].iloc[-1]:+.1f}{unit} after 20 days per 1pp",
            source_label("DGS2", "DGS10", "SPX", "DTWEXBGS"),
            as_of,
            name="response",
            band_name="90% CI",
            theme=th,
            hline=0,
        )
        f.update_xaxes(title_text="business days")
        f.update_layout(height=330)
        chart(f, d, key=f"lp_{name}")
st.caption(
    "Proxy = 1-day change in the 2Y yield on decision days (mixes policy surprises and information effects; decision days "
    "without a rate change are not in the sample). HC1 s.e.; N in the table view."
)

# ------------------------------------------------------------------ FX
st.subheader("FX and rate differentials")
for name, res in b["fx"].items():
    p = res.extra["path"].loc[ctl["start"] :]
    fig = pl.band_chart(
        p["implied"],
        p["lower"],
        p["upper"],
        f"{name} is {res.value:+.1f}% vs its differential-implied level",
        source_label(name),
        pd.Timestamp(p.index[-1]).strftime("%Y-%m"),
        name="differential-implied",
        band_name="90% band",
        theme=th,
    )
    fig.add_trace(
        go.Scatter(x=p.index, y=p["actual"], name="spot", mode="lines", line={"color": "#1f2328", "width": 2})
    )
    chart(fig, p, key=f"fx_{name}")
    lv, ch = res.extra["levels"], res.extra["changes"]
    st.caption(
        f"{res.extra['diff_label']}: levels β = {lv['b']:.2f} (s.e. {lv['se']:.2f}, R² {lv['r2']:.2f}); changes β = {ch['b']:.2f} "
        f"(s.e. {ch['se']:.2f}, R² {ch['r2']:.2f}). Levels regressions of persistent series can be spurious — compare with the changes."
    )
    result_meta(res)
show_status("warning", "Sensitivities, not forecasts: no trading signal is implied.")
footer()
