import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import chart, footer, header, scenario_controls, show_status, sidebar_controls, theme
from macro import plotting as pl
from macro.data import source_label, try_series
from macro.pipeline import build_views, regime_bundle

header(
    "Regime and views",
    "Macro regime, priced vs model, market confirmation and the current view (implications, not recommendations).",
)
ctl = sidebar_controls()
weights = scenario_controls()
th = theme()


@st.cache_resource(show_spinner="Estimating regimes (first run only)…")
def _regimes():
    return regime_bundle()


@st.cache_data(show_spinner="Assembling views…")
def _views(w: tuple):
    return build_views(dict(w))


rb = _regimes()
v = _views(tuple(sorted(weights.items())))
rec = try_series("USREC")

# ------------------------------------------------------------------ regime
st.subheader("Growth × inflation regime (US)")
h = rb["history"]
cur = h.iloc[-1]
show_status(
    "good" if cur["regime"].startswith("Goldilocks") else "warning",
    f"**{cur['regime']}** in {pd.Timestamp(h.index[-1]).to_period('Q')}: 4Q growth {cur['growth']:.1f}% vs trend {cur['trend']:.1f}%, "
    f"core PCE {cur['inflation']:.1f}% vs target {rb['target']:.1f}% (+0.5 margin).",
)
hh = h.loc[ctl["start"] :]
fig = go.Figure()
for k, name in enumerate(sorted(hh["regime"].unique())):
    m = hh[hh["regime"] == name]
    fig.add_trace(
        go.Scatter(
            x=m["growth"] - m["trend"],
            y=m["inflation"],
            mode="markers",
            name=name.split(" (")[0],
            marker={"size": 6, "color": pl.color(k)},
            text=[d.strftime("%Y-Q%q") for d in m.index.to_period("Q").to_timestamp()],
        )
    )
fig.add_trace(
    go.Scatter(
        x=[cur["growth"] - cur["trend"]],
        y=[cur["inflation"]],
        mode="markers",
        name="latest",
        marker={"size": 14, "symbol": "star", "color": "#1f2328"},
    )
)
fig.add_vline(x=0, line_dash="dot")
fig.add_hline(y=rb["target"] + 0.5, line_dash="dot")
fig.update_xaxes(title_text="4Q GDP growth minus potential growth (pp)")
fig.update_yaxes(title_text="core PCE inflation (%)")
pl.base_layout(
    fig,
    "Quarterly regime map since " + ctl["start"][:4],
    source_label("GDPC1", "GDPPOT", "PCEPILFE"),
    pd.Timestamp(h.index[-1]).strftime("%Y-%m"),
    th,
    height=440,
)
chart(fig, hh, key="regime_map")
freq = (100 * h["regime"].value_counts(normalize=True)).round(1).rename("% of quarters")
st.dataframe(freq, use_container_width=True)

ms = rb["markov"]
if "p_high" in ms:
    p = ms["p_high"].loc[ctl["start"] :]
    fig = pl.line_chart(
        p.to_frame("P(high-inflation regime)"),
        f"Markov-switching cross-check: P(high-inflation regime) = {p.iloc[-1]:.2f}",
        source_label("CPILFESL"),
        pd.Timestamp(p.index[-1]).strftime("%Y-%m"),
        yaxis="probability",
        rec=rec,
        theme=th,
    )
    chart(fig, p, key="markov")
    st.caption(
        f"Two-regime model on core CPI (3m annualised): regime means {ms['means'][0]:.2f}% and {ms['means'][1]:.2f}%, "
        f"expected durations {ms['durations'][0]:.0f} and {ms['durations'][1]:.0f} months, N = {ms['n']} months."
    )
else:
    st.warning(ms.get("error", "Markov-switching model unavailable"))

# ------------------------------------------------------------------ priced vs model
st.subheader("Priced vs model")
pvm = v["priced_vs_model"]
pvm["gap (priced − model)"] = pvm["priced"] - pvm["model (median)"]
st.dataframe(pvm.round(2), use_container_width=True, hide_index=True)
st.caption(
    "Fed model = probability-weighted Monte Carlo (Scenarios page); ECB and BoJ = long-run target of the estimated reaction "
    "function. Priced = 2-year yield proxies unless dated OIS values are entered in assumptions.yaml."
)

# ------------------------------------------------------------------ market confirmation
st.subheader("Market-confirmation check")
conf = v["confirmation"]
if conf.empty:
    st.info(f"Model view: {v['view']} — no directional check applied.")
else:
    n_ok = int(conf["consistent"].sum())
    show_status(
        "good" if n_ok >= 4 else "warning" if n_ok >= 2 else "serious",
        f"Model view: **{v['view']}**. {n_ok} of {len(conf)} market signals over the past 4 weeks are consistent with it.",
    )
    st.dataframe(conf.round(2), use_container_width=True)
    div = conf.index[~conf["consistent"]].tolist()
    if div:
        st.caption("Divergences: " + ", ".join(div) + ".")

# ------------------------------------------------------------------ view template
st.subheader("Current view (template for the written notes)")
t = v["template"]
for k, val in t.items():
    st.markdown(f"**{k}**")
    if isinstance(val, list):
        st.markdown("\n".join(f"- {x}" for x in val))
    else:
        st.markdown(val)
footer()
