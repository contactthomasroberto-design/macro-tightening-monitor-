import pandas as pd
import streamlit as st

from components import (
    CACHE_TTL,
    chart,
    footer,
    header,
    scenario_controls,
    show_status,
    sidebar_controls,
    theme,
)
from macro import plotting as pl
from macro.data import source_label
from macro.fans import HOW_TO_READ
from macro.pipeline import scenario_bundle, scenario_results

header(
    "Scenarios and fans",
    "Four scenarios, a quarterly engine, 10,000 Monte Carlo paths per scenario, and BoE-style fan charts.",
)
ctl = sidebar_controls()
weights = scenario_controls()
th = theme()


@st.cache_resource(
    ttl=CACHE_TTL, show_spinner="Running the scenario engine and Monte Carlo (first run only)…"
)
def _bundle():
    return scenario_bundle()


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _results(w: tuple):
    return scenario_results(_bundle(), dict(w))


sb = _bundle()
r = _results(tuple(sorted(weights.items())))
src = source_label("PCEPILFE", "UNRATE", "NROU", "DCOILBRENTEU", "DFF", "DGS2", "DGS10")
as_of = pd.Timestamp(sb["as_of"]).to_period("Q").strftime("%Y-Q%q")
init = sb["init"]

st.subheader("Scenario outcomes")
st.dataframe(r["table"].round(2), use_container_width=True)
st.caption(
    "Scenario inputs (oil, unemployment path, non-energy inflation impulses, term premium) are subjective narratives in "
    "config/scenarios.yaml — editable probabilities in the sidebar. Medians over 10,000 paths per scenario."
)

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**Probability of at least k more 25bp moves within 4 quarters** (current {init['i']:.2f}%)")
    st.dataframe(r["moves"].round(3), use_container_width=True)
with c2:
    st.metric("Recession probability (Sahm-type trigger within 8Q)", f"{100 * r['recession_prob']:.0f}%")
    rv = r["reverse"]
    st.markdown("**Reverse stress test**")
    if rv["p_hawkish"] is None:
        st.markdown(
            f"Priced rate in 12 months ({sb['priced_12m']:.2f}%) lies outside the range spanned by the scenarios "
            f"({rv['range'][0]:.2f}%–{rv['range'][1]:.2f}%): pricing is more extreme than any scenario."
        )
    else:
        st.markdown(
            f"Current pricing ({sb['priced_12m']:.2f}%, {sb['priced_src']}) is consistent with **{100 * rv['p_hawkish']:.0f}%** "
            "probability on the hawkish group (sticky + energy shock)."
        )

st.subheader("Fan charts (central projection = mode)")
fans = r["fans"]
fan_start = max(pd.Timestamp(ctl["start"]), pd.Timestamp(sb["as_of"]) - pd.DateOffset(years=6))
hist_i = sb["policy_hist"].loc[fan_start:]
hist_pi = sb["history"]["pi"].loc[fan_start:]
gdp_hist = None
specs = [
    (
        "i",
        "Fed funds rate",
        hist_i,
        "policy follows the estimated reaction function with a maximum step per quarter; scenario-weighted skew",
    ),
    (
        "pi",
        "Core PCE inflation (yoy)",
        hist_pi,
        "policy follows the estimated reaction function; oil per scenario",
    ),
    (
        "growth",
        "Real GDP growth (Okun-implied, annualised)",
        None,
        "growth implied by unemployment paths via Okun's law around CBO potential growth",
    ),
]
for key, label, hist, cond in specs:
    fq = fans[key]
    q = fq[[c for c in fq.columns if isinstance(c, float)]].copy()
    q["mode"] = fq["mode"]
    h = hist if hist is not None else pd.Series(dtype=float)
    end = fq["mode"].iloc[-1]
    fig = pl.fan_chart(
        h,
        q,
        f"{label}: central path {end:.2f}% after 8 quarters (skew {fq['gamma'].iloc[-1]:+.2f})",
        src,
        as_of,
        conditioning=cond,
        base_color=pl.ENTITY["fed"],
        yaxis="%",
        theme=th,
    )
    chart(fig, fq, key=f"fan_{key}")
st.info(HOW_TO_READ, icon="📖")
st.caption(
    "Width: dispersion of the modal scenario's Monte Carlo paths (bootstrap of historical one-step errors). Skew: probability-"
    "weighted mean minus mode across scenarios (two-piece normal). Bands are equal-tailed 10%…90% intervals; the BoE draws "
    "bands that always include the mode, which differs slightly under skew."
)

st.subheader("Market mapping (sensitivities, not forecasts)")
st.dataframe(r["mapping"].round(1), use_container_width=True, hide_index=True)
st.caption(
    f"2Y and 10Y betas from quarterly changes on changes in the policy rate (2Y β = {sb['beta2'][0]:.2f}, 10Y β = "
    f"{sb['beta10'][0]:.2f}); equities via the S&P 500 real-yield beta (Transmission page). First row = probability-weighted "
    "change in the expected policy rate at 4 quarters."
)

st.subheader("Engine parameters")
c1, c2 = st.columns(2)
c1.markdown("**Phillips curve (quarterly, core PCE yoy)**")
c1.dataframe(sb["phillips"].round(3), use_container_width=True)
c1.caption(f"N = {sb['phillips_n']} quarters, HAC s.e.")
c2.markdown("**Reaction function (from the Policy page)**")
c2.dataframe(sb["rf_table"].round(3), use_container_width=True)
show_status(
    "warning", "Scenario probabilities and paths are judgemental inputs; results are conditional on them."
)
footer()
