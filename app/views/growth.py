import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import chart, footer, header, result_meta, show_status, sidebar_controls, theme
from macro import plotting as pl
from macro.data import source_label, try_series
from macro.growth import GROWTH_SPEC
from macro.pipeline import growth_bundle

header(
    "Growth and recession risk",
    "Nowcast with news decomposition, Growth-at-Risk, and 12-month recession probabilities.",
)
ctl = sidebar_controls()
th = theme()


@st.cache_resource(
    show_spinner="Running nowcast, Growth-at-Risk and recession models (first run takes ~2 minutes)…"
)
def _bundle():
    return growth_bundle()


b = _bundle()
rec = try_series("USREC")
as_of = pd.Timestamp(b["as_of"]).strftime("%Y-%m-%d")
nc_src = source_label(*GROWTH_SPEC, "GDPC1")

# ------------------------------------------------------------------ nowcast
st.subheader("GDP nowcast")
nc = b["nowcast"]
c1, c2, c3 = st.columns(3)
c1.metric(f"Nowcast {nc['target']} (annualised q/q)", f"{nc['point']:.1f}%")
c2.metric("68% band", f"{nc['lo68']:.1f}% to {nc['hi68']:.1f}%")
c3.metric("50% band", f"{nc['lo50']:.1f}% to {nc['hi50']:.1f}%")
st.caption(
    "Mixed-frequency dynamic factor model (statsmodels DynamicFactorMQ; factors Global, Soft, Nominal, Labor), "
    f"{len(GROWTH_SPEC)} monthly series plus quarterly GDP, data published by {as_of} (release lags applied)."
)
ext = b.get("external_nowcasts") or {}
if ext:
    parts = []
    if "Atlanta Fed GDPNow" in ext:
        parts.append(f"Atlanta Fed GDPNow for {nc['target']}: {ext['Atlanta Fed GDPNow']:.1f}%")
    if "WEI week" in ext:
        parts.append(
            f"Weekly Economic Index: {ext['Weekly Economic Index (y/y, latest week)']:.2f}% y/y "
            f"(week of {ext['WEI week']})"
        )
    st.caption(
        "External benchmarks (published, not inputs to this model): "
        + "; ".join(parts)
        + ". "
        + source_label("GDPNOW", "WEI")
    )

w = b["weekly"]
news_cols = [c for c in w.columns if c.startswith("news: ")]
fig = go.Figure()
fig.add_trace(go.Scatter(x=w.index, y=w["hi68"], line={"width": 0}, showlegend=False, hoverinfo="skip"))
fig.add_trace(
    go.Scatter(
        x=w.index,
        y=w["lo68"],
        fill="tonexty",
        fillcolor=pl.fan_colors(pl.ENTITY["fed"], 2)[0],
        line={"width": 0},
        name="68% band",
    )
)
fig.add_trace(go.Scatter(x=w.index, y=w["hi50"], line={"width": 0}, showlegend=False, hoverinfo="skip"))
fig.add_trace(
    go.Scatter(
        x=w.index,
        y=w["lo50"],
        fill="tonexty",
        fillcolor=pl.fan_colors(pl.ENTITY["fed"], 2)[1],
        line={"width": 0},
        name="50% band",
    )
)
fig.add_trace(
    go.Scatter(
        x=w.index,
        y=w["nowcast"],
        mode="lines+markers",
        name="nowcast",
        line={"width": 2, "color": pl.ENTITY["fed"]},
    )
)
fig.update_yaxes(title_text="% annualised")
pl.base_layout(
    fig,
    f"Nowcast for {w['target'].iloc[-1]}: {w['nowcast'].iloc[-1]:.1f}% after the latest week's releases",
    nc_src,
    as_of,
    th,
)
chart(fig, w[["target", "nowcast", "lo50", "hi50", "lo68", "hi68"]], key="nowcast_path")

if news_cols:
    contrib = w[news_cols].fillna(0.0)
    fig = go.Figure()
    for k, c in enumerate(news_cols):
        fig.add_trace(
            go.Bar(x=contrib.index, y=contrib[c], name=c.replace("news: ", ""), marker_color=pl.color(k))
        )
    fig.add_trace(
        go.Scatter(
            x=w.index,
            y=w["change"],
            mode="markers",
            name="total change",
            marker={"color": "#1f2328", "size": 8},
        )
    )
    fig.update_layout(barmode="relative")
    fig.update_yaxes(title_text="pp")
    last = contrib.iloc[-1]
    top = last.abs().idxmax().replace("news: ", "") if last.abs().sum() > 0 else "no release"
    pl.base_layout(
        fig, f"What moved the nowcast: last week driven mostly by {top}", nc_src, as_of, th, height=400
    )
    chart(fig, contrib, key="news")
    st.caption(
        "News = (released value − model expectation) × model weight, summed by release category; 'revisions' collects "
        "revised data. Contributions add up to the weekly change in the nowcast. Weeks where the target quarter changed "
        "(GDP release) start a new decomposition."
    )

# ------------------------------------------------------------------ real-time evaluation
st.subheader("Real-time evaluation")
rt = b["realtime"]
sc = rt["scores"]
st.dataframe(sc.round(3), use_container_width=True)
pre = sc.loc["pre-release"]
beats = pre["rmse DFM"] < pre["rmse AR(1)"] and pre["DM vs AR p"] < 0.10
show_status(
    "good" if beats else "warning",
    f"Just before the advance release the DFM's RMSE is {pre['rmse DFM']:.2f} pp vs {pre['rmse AR(1)']:.2f} for the AR(1) "
    f"({'significantly better' if beats else 'not significantly better at 10%'}; N = {int(pre['n'])} quarters).",
)
t = rt["table"]
tp = t[t["horizon"] == "pre-release"].set_index("quarter")
tp.index = tp.index.to_timestamp()
fig = pl.line_chart(
    tp[["actual", "nowcast", "AR(1)"]].loc[ctl["start"] :],
    "Nowcast just before the advance release vs outcome",
    nc_src,
    as_of,
    yaxis="% annualised",
    theme=th,
    colors=["#6a737d", pl.ENTITY["fed"], pl.SERIES_ORDER[2]],
)
chart(fig, tp, key="rt_eval")
st.caption(
    f"Pseudo real-time: data sets rebuilt with publication lags at each date; parameters re-estimated every 5 years "
    f"({rt['refits']} estimations); outcomes are latest-vintage GDP ({b['vintage_label']}). SPF = mean current-quarter forecast. "
    "Specifications tried: 1 factor structure fixed a priori."
)

# ------------------------------------------------------------------ Growth-at-Risk
st.subheader("Growth-at-Risk")
cols = st.columns(2)
for (h, g), col in zip(b["gar"].items(), cols, strict=True):
    with col:
        d = g.extra["dist"]
        q = g.extra["quantiles"]
        xs = np.linspace(q.iloc[0] - 4, q.iloc[-1] + 3, 300)
        fig = go.Figure(
            go.Scatter(
                x=xs,
                y=d.pdf(xs),
                name="conditional density",
                line={"color": pl.ENTITY["fed"], "width": 2},
                fill="tozeroy",
                fillcolor=pl.fan_colors(pl.ENTITY["fed"], 1)[0],
            )
        )
        fig.add_vline(x=q[0.05], line_dash="dash", annotation_text="5%")
        fig.add_vline(x=g.extra["expected_shortfall_5"], line_dash="dot", annotation_text="ES 5%")
        fig.update_xaxes(title_text=f"average annualised GDP growth, next {h} quarter(s)")
        pl.base_layout(
            fig,
            f"{h}Q ahead: 5% quantile {q[0.05]:.1f}%, expected shortfall {g.extra['expected_shortfall_5']:.1f}%",
            source_label("GDPC1", "NFCI"),
            pd.Timestamp(g.extra["date"]).to_period("Q").strftime("%Y-Q%q"),
            th,
            height=380,
        )
        chart(fig, q.rename("conditional quantile"), key=f"gar_{h}")
        st.dataframe(g.extra["coefficients"].round(3), use_container_width=True)
        bt = b["gar_backtest"][h]["summary"]
        if bt:
            better = bt["mean_log_score"] > bt["mean_log_score_uncond"]
            show_status(
                "good" if better else "warning",
                f"Backtest (N={bt['n']}): mean log score {bt['mean_log_score']:.2f} vs {bt['mean_log_score_uncond']:.2f} "
                f"unconditional; 90% coverage {100 * bt['coverage_90']:.0f}%; PIT KS p = {bt['pit_ks_p']:.2f}.",
            )
st.caption(
    "Downside risk should move with financial conditions (NFCI coefficient more negative at the 5% quantile than at the "
    "median), upside more stable. Skewed t: Jones-Faddy family (approximation of the paper's skew t)."
)
bt4 = b["gar_backtest"][4]["table"]
if not bt4.empty:
    fig = pl.line_chart(
        bt4[["actual", "median", "q05", "q95"]].loc[ctl["start"] :],
        "Recursive 4Q-ahead quantiles vs outcome",
        source_label("GDPC1", "NFCI"),
        as_of,
        yaxis="%",
        theme=th,
        colors=["#6a737d", pl.ENTITY["fed"], pl.STATUS["critical"][0], pl.SERIES_ORDER[3]],
    )
    chart(fig, bt4, key="gar_bt")
    fig = pl.histogram(
        bt4["pit"],
        "PIT of the 4Q-ahead GaR distribution (flat = calibrated)",
        source_label("GDPC1", "NFCI"),
        as_of,
        bins=10,
        theme=th,
        expected=len(bt4) / 10,
    )
    chart(fig, bt4["pit"], key="gar_pit")

# ------------------------------------------------------------------ recession
st.subheader("Recession probability (12 months ahead)")
r = b["recession"]
cur = r.extra["current"]
rows = [{"model": k, "probability": v["p"], "5%": v.get("lo"), "95%": v.get("hi")} for k, v in cur.items()]
st.dataframe(pd.DataFrame(rows).set_index("model").round(3), use_container_width=True)
st.markdown(
    f"Headline (extended probit): **{100 * r.value:.0f}%** (90% block-bootstrap band {100 * r.lower:.0f}%–{100 * r.upper:.0f}%). "
    f"Estimated on **{r.extra['episodes']} recession episodes** (N = {r.n_obs} months)."
)
oos = r.extra["oos"]
fig = pl.line_chart(
    oos.drop(columns="y").loc[ctl["start"] :],
    "Out-of-sample 12-month-ahead recession probabilities",
    source_label("T10Y3M", "BAA10Y", "UNRATE", "NFCI", "USREC"),
    as_of,
    yaxis="probability",
    rec=rec,
    theme=th,
)
chart(fig, oos, key="rec_oos")
st.dataframe(r.extra["scores"].round(3), use_container_width=True)
best_auc = r.extra["scores"]["AUC"].max()
show_status(
    "good" if best_auc > 0.7 else "warning",
    f"Best out-of-sample AUC {best_auc:.2f} (0.5 = no skill); Brier vs climatology shown above. "
    f"Expanding window from {r.extra['oos_start'][:4]}.",
)
with st.expander("Calibration tables"):
    for name, cal in r.extra["calibration"].items():
        st.markdown(f"**{name}**")
        st.dataframe(cal.round(3), use_container_width=True, hide_index=True)
with st.expander("Probit coefficients (full sample)"):
    st.dataframe(pd.DataFrame(r.extra["coefficients"]).round(3), use_container_width=True)
result_meta(r)

sahm = b["sahm"].loc[ctl["start"] :]
trig = bool(sahm["triggered"].iloc[-1])
fig = pl.line_chart(
    sahm[["sahm"]].rename(columns={"sahm": "Sahm indicator"}),
    f"Sahm rule {'triggered' if trig else 'not triggered'}: {sahm['sahm'].iloc[-1]:.2f} pp (threshold 0.50)",
    source_label("UNRATE"),
    as_of,
    yaxis="pp",
    rec=rec,
    theme=th,
    hline=0.5,
)
chart(fig, sahm, key="sahm")

ea = b["ea_recession"]
if ea and "current" in ea:
    c = ea["current"]
    st.markdown(
        f"**Euro area** (probit on the AAA 2s10s slope and the 6-month change in unemployment): "
        f"{100 * c['p']:.0f}% (90% band {100 * c['lo']:.0f}%–{100 * c['hi']:.0f}%), {ea['episodes']} episodes, N = {ea['n']} months."
    )

with st.expander("Limitations"):
    st.markdown(
        "- Latest-vintage GDP as outcome; ALFRED vintages not yet used in the nowcast evaluation.\n"
        "- Few recessions (N shown): probabilities and AUCs are imprecise. NBER dates arrive with long lags.\n"
        "- The nowcast panel is much smaller than the NY Fed's (about 38 series).\n"
        "- Growth-at-Risk uses a different skew-t family than the paper."
    )
footer()
