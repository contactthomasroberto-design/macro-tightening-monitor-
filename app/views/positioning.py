import pandas as pd
import streamlit as st

from components import CACHE_TTL, chart, footer, header, show_status, sidebar_controls, theme
from macro import plotting as pl
from macro.data import source_label
from macro.pipeline import positioning_bundle

header(
    "Positioning",
    "CFTC Traders in Financial Futures: who is long or short rates, equities and currencies, and how crowded.",
)
ctl = sidebar_controls()
th = theme()


@st.cache_resource(ttl=CACHE_TTL, show_spinner=False)
def _bundle():
    return positioning_bundle()


b = _bundle()
if not b["adjusted"]:
    st.warning("No CFTC positioning data available.")
    footer()
    st.stop()
ref = pd.Timestamp(b["as_of"])
st.info(
    f"Reference date (Tuesday positions): **{ref:%Y-%m-%d}**, published about {b['lag_days']} days later (Friday). "
    "Positions are futures-only, by trader category.",
)
tab = b["table"]
st.dataframe(tab.round(1), use_container_width=True)
for name, r in tab[tab["flag"] != ""].iterrows():
    show_status(
        "warning", f"{name}: {r['flag']} ({r['percentile (3y)']:.0f}th percentile of the last 3 years)."
    )
if (tab["flag"] == "").all():
    show_status("good", "No crowding flag (all percentiles between 10 and 90 over 3 years).")

sel = st.multiselect(
    "Series",
    list(b["adjusted"]),
    default=list(b["adjusted"])[:3],
    format_func=lambda s: s.replace("TFF_", ""),
)
for sid in sel:
    s = b["adjusted"][sid].loc[ctl["start"] :]
    p = b["percentiles"][sid].loc[ctl["start"] :]
    df = pd.DataFrame({"net position": s, "3y percentile": p})
    lab = tab.index[tab["id"] == sid][0]
    fig = pl.small_multiples(
        df,
        f"{lab}: {s.iloc[-1]:,.1f}, {p.iloc[-1]:.0f}th percentile",
        source_label(sid),
        s.index[-1].strftime("%Y-%m-%d"),
        ncols=2,
        theme=th,
    )
    chart(fig, df, key=f"pos_{sid}")
st.caption(
    "Rates converted to 10-year-note equivalents with approximate per-contract DV01 ratios (SOFR 3M ≈ 25/70 of a 10Y note); "
    "the OFR Hedge Fund Monitor publishes exact duration-adjusted series and should be preferred when loaded. Equity and FX "
    "converted to USD notional at same-date prices. The macro-thesis check is on the Regime and views page."
)
footer()
