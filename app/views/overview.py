import streamlit as st

from components import (
    CACHE_TTL,
    footer,
    header,
    live_strip,
    scenario_controls,
    show_status,
    sidebar_controls,
    status_chip,
    tradingview_ticker,
)
from macro import panels
from macro.config import stale_assumptions
from macro.data import as_of_label, source_label, try_series
from macro.pipeline import build_views
from macro.views import format_value

header(
    "Macro Tightening Monitor",
    "Are the Fed, the ECB and the BoJ right to tighten, how much is left, and how does it transmit?",
)
ctl = sidebar_controls()
weights = scenario_controls()
if st.sidebar.toggle(
    "Market ticker (TradingView)",
    value=True,
    help="Near-real-time prices from TradingView's free widget. Display only: the models use public data.",
):
    tradingview_ticker()
live_strip()


@st.cache_data(
    ttl=CACHE_TTL, show_spinner="Loading the latest results (first run computes every module, a few minutes)…"
)
def _views(w: tuple):
    return build_views(dict(w))


v = _views(tuple(sorted(weights.items())))
fed_priced = panels.market_priced("fed")

tab = st.segmented_control(
    "View",
    ["Scorecard", "Commentary", "What changed", "Data notes"],
    default="Scorecard",
    key="ov_view",
    label_visibility="collapsed",
)

if tab in (None, "Scorecard"):
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
    if not v["confirmation"].empty:
        n_ok = int(v["confirmation"]["consistent"].sum())
        show_status(
            "good" if n_ok >= 4 else "warning",
            f"Market confirmation: {n_ok}/{len(v['confirmation'])} signals consistent with the model view.",
        )

elif tab == "Commentary":
    for c in v["comments"].values():
        st.markdown(f"- {c}")
    st.markdown(f"- Model view for the Fed: **{v['view']}**. " + v["template"]["What is priced"])
    if fed_priced is not None:
        st.caption(
            f"Fed: market-priced 3-month average fed funds rate in 12 months {fed_priced['value']:.2f}% "
            f"({fed_priced['source']}, {fed_priced['as_of']}). Risk-neutral: includes risk premia."
        )

elif tab == "What changed":
    ch = v["changes"].copy()
    ch["change"] = ch["change"].round(2)
    c1, c2 = st.columns([2, 1])
    c1.dataframe(ch, use_container_width=True)
    nc = v["nowcast_change"]
    c2.metric("GDP nowcast, weekly change", f"{nc:+.2f} pp" if nc == nc else "n/a (target quarter changed)")

else:
    src_dates = {
        k: as_of_label(try_series(k))
        for k in ("DFF", "CPIAUCSL", "EA_DFR", "EA_HICP", "JP_POLICY", "DGS10", "SPX")
    }
    st.markdown("**Latest observation by source:** " + " · ".join(f"{k} {d}" for k, d in src_dates.items()))
    overnight = {"SOFR": "SOFR", "€STR": "EA_ESTR", "Japan call rate": "JP_CALL_D"}
    on_txt = [
        f"{lab} {s.dropna().iloc[-1]:.2f}% ({as_of_label(s)})"
        for lab, sid in overnight.items()
        if (s := try_series(sid)) is not None and not s.dropna().empty
    ]
    if on_txt:
        st.markdown(
            "**Overnight rates:** " + " · ".join(on_txt) + ". " + source_label("SOFR", "EA_ESTR", "JP_CALL_D")
        )
    stale = [k for k in stale_assumptions() if not (k == "fed_terminal_rate" and fed_priced is not None)]
    if stale:
        st.warning(
            f"Market-pricing assumptions missing or older than 30 days: {', '.join(stale)} "
            "(config/assumptions.yaml). 2-year yields are used as proxies."
        )
    st.caption("Status colours always come with a label. Details on each page.")
footer()
