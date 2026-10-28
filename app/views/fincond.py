import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import CACHE_TTL, chart, footer, header, result_meta, show_status, sidebar_controls, theme
from macro import plotting as pl
from macro.config import assumptions
from macro.data import source_label, try_series
from macro.fincond import VARIABLES
from macro.panels import FCI_IDS
from macro.pipeline import fincond_bundle

header(
    "Financial conditions",
    "How much tightening is left? Financial conditions as an impulse on growth, and the gap to neutral.",
)
ctl = sidebar_controls()
th = theme()


@st.cache_resource(
    ttl=CACHE_TTL, show_spinner="Estimating financial-conditions sensitivities (first run only)…"
)
def _bundle():
    return fincond_bundle()


b = _bundle()
f1, f3 = b["fci_1y"], b["fci_3y"]
src = source_label(*FCI_IDS.values(), "GDPC1")
as_of = pd.Timestamp(b["as_of"]).to_period("Q").strftime("%Y-Q%q")
rec = try_series("USREC")

st.info(
    "**Version shown: FCI-lite (this project).** Seven variables as in the Fed Board's FCI-G (policy rate, 10Y yield, "
    "30Y mortgage rate, corporate Baa yield, equities, house prices, broad dollar), but growth weights are estimated "
    "statistically here, not taken from the FRB/US model. It is **not the Fed's index**. "
    + (
        "The published FCI-G is shown alongside for comparison."
        if b["fcig_available"]
        else "The published FCI-G could not be loaded (place it in data/manual/FCIG_1Y.csv)."
    ),
)

# ------------------------------------------------------------------ level and decomposition
now = float(f1.value.iloc[-1])
word = "headwind" if now > 0 else "tailwind"
c1, c2, c3 = st.columns(3)
c1.metric(
    "FCI-lite, 1-year lookback",
    f"{now:+.2f} pp",
    help="Effect on real GDP growth over the next 4 quarters; positive = headwind",
)
c1.caption(f"90% bootstrap band {f1.lower:+.2f} to {f1.upper:+.2f}")
c2.metric("FCI-lite, 3-year lookback", f"{float(f3.value.iloc[-1]):+.2f} pp")
c2.caption(f"90% band {f3.lower:+.2f} to {f3.upper:+.2f}")
g = b["gap"]
c3.metric(
    "Gap to neutral conditions",
    f"{g['gap']:+.2f} pp",
    help="FCI level that closes the output gap minus current FCI",
)

lines = pd.concat({"FCI-lite 1y": f1.value, "FCI-lite 3y": f3.value}, axis=1).loc[ctl["start"] :]
if b["fcig_available"]:
    lines["Fed Board FCI-G 1y (published)"] = b["panel"]["fcig"].resample("QS").mean()
fig = pl.line_chart(
    lines,
    f"Financial conditions are a {abs(now):.2f} pp {word} to growth over the next year (FCI-lite)",
    src,
    as_of,
    yaxis="pp of GDP growth (+ = headwind)",
    rec=rec,
    theme=th,
    hline=0,
)
chart(fig, lines, key="fci_lines")

contrib = f1.extra["contributions"].loc[ctl["start"] :].iloc[-24:]
fig = go.Figure()
for k, col in enumerate(contrib.columns):
    fig.add_trace(go.Bar(x=contrib.index, y=contrib[col], name=VARIABLES[col][0], marker_color=pl.color(k)))
fig.add_trace(
    go.Scatter(
        x=contrib.index, y=contrib.sum(axis=1), name="FCI-lite 1y", line={"color": "#1f2328", "width": 2}
    )
)
fig.update_layout(barmode="relative")
top = contrib.iloc[-1].abs().idxmax()
pl.base_layout(
    fig,
    f"Largest contributor today: {VARIABLES[top][0].lower()} ({contrib.iloc[-1][top]:+.2f} pp)",
    src,
    as_of,
    th,
    height=440,
)
chart(fig, contrib, key="fci_decomp")

st.markdown(
    "**Estimated growth sensitivities** (effect on next-year GDP growth, pp, of a 1-unit change over the lookback)"
)
bt = f1.extra["betas"][["label", "unit", "beta", "lower", "upper"]].set_index("label")
st.dataframe(bt.round(4), use_container_width=True)
result_meta(f1)

# ------------------------------------------------------------------ gap to neutral
st.subheader("How much tightening is left?")
st.markdown(
    f"The output gap is **{g['output_gap']:+.2f}%**. Closing it over **{g['horizon_q']} quarters** requires financial "
    f"conditions worth **{g['fci_target']:+.2f} pp** of growth per year; current FCI-lite is **{g['fci_now']:+.2f} pp**, "
    f"so the gap is **{g['gap']:+.2f} pp** ({'more tightening needed' if g['gap'] > 0 else 'conditions already tighter than needed'})."
)
fig = go.Figure(
    go.Bar(
        x=["Current FCI-lite", "FCI consistent with closing the gap"],
        y=[g["fci_now"], g["fci_target"]],
        marker_color=[pl.ENTITY["fed"], pl.SERIES_ORDER[0]],
        error_y={
            "type": "data",
            "symmetric": False,
            "array": [f1.upper - now, 0],
            "arrayminus": [now - f1.lower, 0],
        },
    )
)
pl.base_layout(fig, f"Gap to neutral financial conditions: {g['gap']:+.2f} pp", src, as_of, th, height=360)
chart(fig, pd.Series({"current": g["fci_now"], "target": g["fci_target"]}), key="fci_gap")

st.markdown(
    "**Equivalences — not forecasts.** The change in a single variable that would, on its own, close the gap:"
)
eq = b["equivalences"]
st.dataframe(eq.drop(columns=["key"]).round(2), use_container_width=True)
for name, r in eq.iterrows():
    if not r["reliable"]:
        show_status(
            "warning",
            f"{name}: the sign of its growth sensitivity flips in {100 * r['sign_unstable_share']:.0f}% "
            "of bootstrap draws — equivalence not reliable.",
        )
comb = eq.attrs.get("combination")
if comb is not None:
    st.markdown("Combination (equal shares across reliable variables):")
    st.dataframe(comb.round(2), use_container_width=True)
st.caption(
    f"Bands: 16th-84th percentile over bootstrap draws, widened by ±{100 * assumptions()['fincond']['fci_multiplier_uncertainty']:.0f}% "
    "judgemental multiplier uncertainty (assumptions.yaml). Sensitivities, not price targets."
)

# ------------------------------------------------------------------ projection
st.subheader("Projected FCI path")
proj = b["projection"]
fig = pl.line_chart(
    proj,
    "FCI-lite fades as past moves roll out of the 1-year window unless conditions tighten further",
    src,
    as_of,
    yaxis="pp (+ = headwind)",
    theme=th,
    hline=0,
)
chart(fig, proj, key="fci_proj")
st.caption(
    "Paths reach their end-point over four quarters and stay there; other variables held at their last level. "
    "Scenario-engine paths are used on the Scenarios page."
)

# ------------------------------------------------------------------ index comparison
st.subheader("Do conclusions depend on the index?")
comp = b["comparison"]
st.dataframe(comp.round(2), use_container_width=True)
verdicts = set(comp["verdict"])
show_status(
    "good" if len(verdicts) == 1 else "warning",
    "All indices agree."
    if len(verdicts) == 1
    else "Indices disagree: statistical indices (NFCI, factor) measure stress and spreads, while impulse-type indices "
    "(FCI-lite, FCI-G) measure the growth drag from past moves — conclusions depend on the index choice.",
)
iq = b["indices_q"].loc[ctl["start"] :]
z = (iq - iq.mean()) / iq.std()
fig = pl.line_chart(
    z,
    "Financial-conditions indices, standardised (higher = tighter)",
    source_label("NFCI", "BAA10Y", "VIXCLS", "T10Y3M", *FCI_IDS.values()),
    as_of,
    yaxis="z-score",
    rec=rec,
    theme=th,
)
chart(fig, iq, key="fci_compare")

with st.expander("Limitations"):
    st.markdown(
        "- Statistical weights from a short sample with few recessions; collinear rate variables (ridge shrinkage).\n"
        "- The broad dollar index starts in 2006 in live data, which shortens the estimation sample.\n"
        "- Moody's Baa replaces the ICE BBB yield used by FCI-G (ICE history on FRED may be truncated).\n"
        "- The neutral-conditions mapping (FCI* = y·4/H) is a simplification of the practitioner approach.\n"
        "- Equivalences are partial-equilibrium sensitivities, not forecasts or targets."
    )
footer(research_series=True)
