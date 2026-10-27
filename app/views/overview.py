import streamlit as st

from components import footer, header, scenario_controls, show_status, sidebar_controls, status_chip
from macro.config import stale_assumptions
from macro.data import as_of_label, try_series
from macro.pipeline import build_views
from macro.views import format_value

header(
    "Macro Tightening Monitor",
    "Are the Fed, the ECB and the BoJ right to tighten, how much is left, and how does it transmit?",
)
ctl = sidebar_controls()
weights = scenario_controls()


@st.cache_data(show_spinner="Loading the latest results (first run computes every module, a few minutes)…")
def _views(w: tuple):
    return build_views(dict(w))


v = _views(tuple(sorted(weights.items())))
src_dates = {
    k: as_of_label(try_series(k))
    for k in ("DFF", "CPIAUCSL", "EA_DFR", "EA_HICP", "JP_POLICY", "DGS10", "SPX")
}
st.caption("As of (per source): " + " · ".join(f"{k} {d}" for k, d in src_dates.items()))
stale = stale_assumptions()
if stale:
    st.warning(
        f"Market-pricing assumptions missing or older than 30 days: {', '.join(stale)} (config/assumptions.yaml). "
        "2-year yields are used as proxies.",
        icon="⚠️",
    )

st.subheader("Scorecard")
sc = v["scorecard"]
cols = st.columns(3)
for col, bank in zip(cols, ["FED", "ECB", "BOJ"], strict=True):
    with col:
        st.markdown(f"### {bank}")
        for _, r in sc[sc["bank"] == bank].iterrows():
            txt = format_value(r["value"], r["unit"])
            st.markdown(
                status_chip(
                    r["status"], f"{r['metric']}: **{txt}**" + (f" — {r['note']}" if r["note"] else "")
                ),
                unsafe_allow_html=True,
            )

st.subheader("Commentary")
for c in v["comments"].values():
    st.markdown(f"- {c}")
st.markdown(f"- Model view for the Fed: **{v['view']}**. " + v["template"]["What is priced"])

st.subheader("What changed since last week")
ch = v["changes"].copy()
ch["change"] = ch["change"].round(2)
c1, c2 = st.columns([2, 1])
c1.dataframe(ch, use_container_width=True)
nc = v["nowcast_change"]
c2.metric("GDP nowcast, weekly change", f"{nc:+.2f} pp" if nc == nc else "n/a (target quarter changed)")
if not v["confirmation"].empty:
    n_ok = int(v["confirmation"]["consistent"].sum())
    show_status(
        "good" if n_ok >= 4 else "warning",
        f"Market confirmation: {n_ok}/{len(v['confirmation'])} signals consistent with the model view.",
    )
st.caption("Details on each page. Status colours always come with an icon and a label.")
footer()
