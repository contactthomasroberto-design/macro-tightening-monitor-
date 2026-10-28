import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import CACHE_TTL, chart, footer, header, result_meta, show_status, sidebar_controls, theme
from macro import plotting as pl
from macro.curves import REGIMES
from macro.data import source_label, try_series
from macro.pipeline import curves_bundle

header(
    "Curves and term premium",
    "Slopes, what drives the 10-year yield, curve regimes, euro sovereign stress and the global duration factor.",
)
ctl = sidebar_controls()
th = theme()


@st.cache_resource(ttl=CACHE_TTL, show_spinner="Computing curve analytics (first run only)…")
def _bundle():
    return curves_bundle()


b = _bundle()
as_of = pd.Timestamp(b["as_of"]).strftime("%Y-%m-%d")
rec = try_series("USREC")
us_src = source_label("DGS3MO", "DGS2", "DGS5", "DGS10", "DGS30")

# ------------------------------------------------------------------ US slopes
st.subheader("US curve")
sp = b["spreads"].loc[ctl["start"] :]
last = sp.iloc[-1]
inv = [c for c in ("3m10y", "2s10s") if last[c] < 0]
title = (
    f"The curve is inverted on {' and '.join(inv)} ({', '.join(f'{c} {last[c]:.0f}bp' for c in inv)})"
    if inv
    else f"The curve is positively sloped: 3m10y {last['3m10y']:.0f}bp, 2s10s {last['2s10s']:.0f}bp"
)
fig = pl.small_multiples(
    sp.resample("W-FRI").last(), title, us_src, as_of, ncols=2, hline=0, rec=rec, theme=th, yaxis="bp"
)
chart(fig, sp, key="us_spreads")

# ------------------------------------------------------------------ 10Y decomposition
st.subheader("What is in the 10-year yield?")
rb = b["decomp"]["real_be"].loc[ctl["start"] :].resample("W-FRI").last()
fig = pl.small_multiples(
    rb[["10y", "real", "breakeven"]].rename(
        columns={"real": "real yield (TIPS)", "breakeven": "10Y breakeven"}
    ),
    f"10Y {rb['10y'].iloc[-1]:.2f}% = real {rb['real'].iloc[-1]:.2f}% + breakeven {rb['breakeven'].iloc[-1]:.2f}%",
    source_label("DGS10", "DFII10", "T10YIE"),
    as_of,
    ncols=3,
    rec=rec,
    theme=th,
    yaxis="%",
)
chart(fig, rb, key="real_be")
tps = b["decomp"]["tp"]
if tps:
    cols = st.columns(len(tps))
    for (name, d), c in zip(tps.items(), cols, strict=True):
        with c:
            dd = d.loc[ctl["start"] :].resample("W-FRI").last()
            fig = pl.line_chart(
                dd[["expected short rate", "term premium"]],
                f"{name}: term premium {dd['term premium'].iloc[-1]:.2f}%",
                source_label("THREEFYTP10" if "Kim" in name else "ACMTP10", "DGS10"),
                as_of,
                yaxis="%",
                rec=rec,
                theme=th,
                hline=0,
                height=380,
            )
            chart(fig, dd, key=f"tp_{name[:3]}")
    st.caption(
        "Term premia are model estimates published by the Fed Board (Kim-Wright) and the NY Fed (ACM); they differ by model. "
        "Expected short rate = 10Y yield minus the model's term premium. Research series, not official statistics."
    )
else:
    st.info("Published term-premium series unavailable.")

# ------------------------------------------------------------------ regimes
st.subheader("Curve regimes")
reg = b["regimes"]
cur = reg.iloc[-1]
show_status(
    "warning" if "bear" in cur["regime"] else "good",
    f"Last 21 business days: **{cur['regime']}** (slope {cur['d_slope_bp']:+.0f}bp, level {cur['d_level_bp']:+.0f}bp).",
)
r = reg.loc[ctl["start"] :].resample("W-FRI").last()
fig = go.Figure()
for k, name in enumerate(REGIMES):
    m = r[r["regime"] == name]
    fig.add_trace(
        go.Scatter(
            x=m.index, y=m["d_slope_bp"], mode="markers", name=name, marker={"size": 4, "color": pl.color(k)}
        )
    )
fig.update_yaxes(title_text="21-day change in 2s10s (bp)")
pl.base_layout(fig, "Regime history (weekly sample of rolling 21-day moves)", us_src, as_of, th, height=380)
chart(fig, r, key="regimes")
st.dataframe(
    b["regime_freq"].rename(
        columns={"condition true": "Fed hiking (rate up over 6m)", "condition false": "otherwise"}
    ),
    use_container_width=True,
)
st.caption(
    "Share of days (%) in each regime. Bull/bear = yields falling/rising on average; steepener/flattener = 2s10s widening/narrowing; "
    "range-bound = both moves under 5bp. N = number of business days in the sample: "
    f"{len(reg):,}."
)

# ------------------------------------------------------------------ euro sovereigns
st.subheader("Euro-area sovereign stress")
sov = b["stress"]
lat = sov["latest"]
flags = lat.index[lat["level flag"] | lat["speed flag"]].tolist()
if flags:
    show_status("serious", f"Stress flag on: {', '.join(flags)}")
else:
    show_status("good", "No sovereign stress flag (level z ≤ 2, percentile ≤ 95, 3-month speed z ≤ 2).")
st.dataframe(lat.round(2), use_container_width=True)
s = b["sovereign"].loc[ctl["start"] :]
fig = pl.line_chart(
    s,
    f"BTP-Bund {lat.loc['BTP-Bund', 'spread (bp)']:.0f}bp, at the {lat.loc['BTP-Bund', 'percentile']:.0f}th percentile of its history",
    source_label("DE_10Y", "FR_10Y", "IT_10Y", "ES_10Y"),
    pd.Timestamp(s.index[-1]).strftime("%Y-%m"),
    yaxis="bp",
    colors=[pl.SERIES_ORDER[0], pl.SERIES_ORDER[3], pl.SERIES_ORDER[2]],
    theme=th,
)
chart(fig, s, key="sov")
z = sov["z"].loc[ctl["start"] :]
fig = pl.line_chart(
    z,
    "Expanding-window z-scores (information up to each date only)",
    source_label("DE_10Y", "IT_10Y"),
    pd.Timestamp(s.index[-1]).strftime("%Y-%m"),
    yaxis="z",
    hline=2,
    theme=th,
)
chart(fig, z, key="sovz")
ea = b["ea_curve"].loc[ctl["start"] :].dropna(how="all")
fig = pl.line_chart(
    ea,
    "Euro-area curve: AAA 2Y and 10Y, Bund 10Y",
    source_label("EA_YC_2Y", "EA_YC_10Y", "DE_10Y"),
    pd.Timestamp(ea.index[-1]).strftime("%Y-%m"),
    yaxis="%",
    colors=[pl.ENTITY["ecb"], pl.SERIES_ORDER[0], pl.SERIES_ORDER[1]],
    theme=th,
)
chart(fig, ea, key="ea_curve")

# ------------------------------------------------------------------ global duration
st.subheader("Global duration factor")
dur = b["duration"]
rs = dur.extra["rolling_share"].loc[ctl["start"] :]
fig = pl.line_chart(
    (100 * rs).to_frame("PC1 share of variance (%)"),
    f"One common factor explains {100 * rs.iloc[-1]:.0f}% of monthly 10Y moves across US, DE, JP, FR, IT "
    f"({dur.extra['window']}m rolling)",
    source_label("DGS10", "DE_10Y", "JP_10Y", "FR_10Y", "IT_10Y"),
    pd.Timestamp(rs.index[-1]).strftime("%Y-%m"),
    yaxis="%",
    theme=th,
)
chart(fig, rs, key="dur")
st.caption(
    f"Full-sample PC1 share {100 * dur.value:.0f}%; loadings: "
    + ", ".join(f"{k} {v:.2f}" for k, v in dur.extra["loadings"].items())
)
result_meta(dur)

# ------------------------------------------------------------------ Japan
st.subheader("Japan: JGB 10Y")
jp = b["jgb"].loc[ctl["start"] :]
fig = pl.line_chart(
    pd.DataFrame({"JGB 10Y": jp, "12m change": jp.diff(12)}),
    f"JGB 10Y at {jp.iloc[-1]:.2f}%",
    source_label("JP_10Y"),
    pd.Timestamp(jp.index[-1]).strftime("%Y-%m"),
    yaxis="%",
    colors=[pl.ENTITY["boj"], pl.SERIES_ORDER[0]],
    theme=th,
    hline=0,
)
ref = b["jgb_reference"]
if ref and ref.get("value") is not None:
    fig.add_hline(
        y=float(ref["value"]),
        line_dash="dot",
        annotation_text=f"policy reference ({ref.get('source')}, {ref.get('as_of')})",
    )
chart(fig, jp, key="jgb")
if not (ref and ref.get("value") is not None):
    st.caption("No BoJ yield-curve reference level entered in assumptions.yaml (none shown).")
st.caption(
    "JGB series from OECD MEI via FRED is monthly and flagged `verify` for staleness; replace with BoJ/MoF data if stale."
)

with st.expander("Limitations"):
    st.markdown(
        "- Euro sovereign yields are monthly long-term rates (convergence-criterion series), not daily benchmarks.\n"
        "- Term-premium estimates are model-dependent and are revised.\n"
        "- Regime thresholds (21 days, 5bp) are fixed a priori; results are sensitive to them.\n"
        "- The duration factor is estimated on a common sample, limited by the shortest series."
    )
footer(research_series=True)
