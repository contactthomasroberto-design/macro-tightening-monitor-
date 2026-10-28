import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import CACHE_TTL, chart, footer, header, show_status, sidebar_controls, theme
from macro import plotting as pl
from macro.pipeline import history_bundle

header(
    "Historical cycles",
    "How often have tightening cycles ended in recession? Two centuries, 170 countries, annual data "
    "(Global Macro Database).",
)
sidebar_controls()
th = theme()


@st.cache_resource(
    ttl=CACHE_TTL, show_spinner="Loading the Global Macro Database and dating the cycles (first run only)…"
)
def _bundle():
    return history_bundle()


try:
    b = _bundle()
except Exception as exc:  # the panel is optional: the page explains instead of failing
    show_status("warning", f"Global Macro Database unavailable: {exc}")
    footer()
    st.stop()

src = f"Global Macro Database, release {b['version']}"
as_of = str(b["last_actual_year"])
st.info(
    f"{b['licence']} Cite: {b['citation']}. Years after {b['last_actual_year']} are projections in the "
    "database and are excluded.",
)
cyc = b["cycles"]
done = cyc.dropna(subset=["recession_after"])
st.caption(
    f"{len(cyc)} tightening cycles in {b['n_countries']} countries; {len(done)} with a complete outcome window. "
    "Cycle = trough-to-peak rise of the policy rate (central-bank rate, else short rate) of at least 1pp, ended "
    "by a fall of 0.5pp. Recession after = real GDP falls in at least one year from the peak year to two years "
    "after. Annual data: short cycles and short recessions are missed; read the shares as orders of magnitude."
)

# ------------------------------------------------------------------ where we stand
st.subheader("Where the Fed, the euro area and the BoJ stand")
cur = b["current"]
if len(cur):
    rows = []
    for iso, r in cur.iterrows():
        sim = b["similar"].get(iso, {})
        rows.append(
            {
                "country": r["country"] + (" (euro-area proxy)" if iso == "DEU" else ""),
                "stage": r["stage"],
                "trough → peak": f"{r['trough']} → {r['peak']}",
                "rise (pp)": r["rise (pp)"],
                "inflation at peak (%)": r["inflation at peak"],
                f"rate {r['latest year']} (%)": r["rate now"],
                "similar past cycles (N)": sim.get("n"),
                "share of those ending in recession": sim.get("share"),
                "95% interval": (f"{sim['lo']:.0%} to {sim['hi']:.0%}" if sim.get("n") else "n/a"),
            }
        )
    st.dataframe(pd.DataFrame(rows).round(2), use_container_width=True, hide_index=True)
    st.caption(
        f"Latest realised year {b['last_actual_year']}. 'Similar' = past cycles within ±1pp of the same rise and "
        "±2pp of the same inflation at the peak. Germany stands in for the euro area (the database has no "
        "aggregate). Base rates, not forecasts: they ignore everything else we know about today."
    )

# ------------------------------------------------------------------ base rates
st.subheader("Base rates: share of cycles followed by recession")


def _bar(tab: pd.DataFrame, by: str, title: str, key: str) -> None:
    t = tab.set_index(by)
    fig = go.Figure(
        go.Bar(
            x=[str(i) for i in t.index],
            y=100 * t["share ending in recession"],
            error_y={
                "type": "data",
                "symmetric": False,
                "array": 100 * (t["95% high"] - t["share ending in recession"]),
                "arrayminus": 100 * (t["share ending in recession"] - t["95% low"]),
            },
            marker_color=pl.color(0),
            text=[f"N={n}" for n in t["cycles (N)"]],
            textposition="outside",
        )
    )
    fig.update_yaxes(title_text="% of cycles", range=[0, 100])
    pl.base_layout(fig, title, src, as_of, th, height=380, note="Error bars: 95% Wilson interval.")
    chart(fig, t.round(3), key=key)


c1, c2 = st.columns(2)
with c1:
    _bar(b["by_rise"], "rise bucket", "By size of the cycle", "hist_rise")
with c2:
    _bar(b["by_inflation"], "inflation at peak", "By inflation at the peak", "hist_infl")
_bar(b["by_era"], "era", "By era (start of the cycle)", "hist_era")
ex = b["by_era_ex2020"].set_index("era")["share ending in recession"]
base = b["by_era"].set_index("era")["share ending in recession"]
st.caption(
    "Robustness, 2020 not counted as a recession year (a pandemic, not a policy recession): post-GFC share "
    f"{base.iloc[-1] if len(base) else np.nan:.0%} → {ex.get(base.index[-1], np.nan) if len(base) else np.nan:.0%}."
)

# ------------------------------------------------------------------ size vs outcome
st.subheader("Size of the cycle and what followed")
d = done[done["infl_at_peak"].abs() < 50]
fig = go.Figure()
for k, (lab, m) in enumerate(
    [
        ("no recession", d[~d["recession_after"].astype(bool)]),
        ("recession", d[d["recession_after"].astype(bool)]),
    ]
):
    fig.add_trace(
        go.Scatter(
            x=m["rise_pp"],
            y=m["min_growth_after"],
            mode="markers",
            name=lab,
            marker={"size": 6, "color": pl.color(k), "opacity": 0.6},
            text=[f"{c} {t}-{p}" for c, t, p in zip(m["country"], m["trough"], m["peak"], strict=True)],
        )
    )
fig.add_hline(y=0, line_dash="dot")
fig.update_xaxes(title_text="cumulative rise of the policy rate (pp)", type="log")
fig.update_yaxes(title_text="lowest annual GDP growth, peak to peak+2 (%)", range=[-15, 15])
pl.base_layout(fig, "Each dot is one tightening cycle", src, as_of, th, height=460)
chart(
    fig,
    d[["country", "trough", "peak", "rise_pp", "infl_at_peak", "min_growth_after", "recession_after"]],
    key="hist_scatter",
)

lg = b["logit"]
if lg:
    tab = pd.DataFrame(
        {"coefficient": lg["params"], "s.e. (clustered by country)": lg["se"], "p-value": lg["p"]}
    )
    st.markdown(
        f"**Logit: P(recession after) on cycle characteristics** (N = {lg['n']} cycles, {lg['countries']} countries)"
    )
    st.dataframe(tab.round(3), use_container_width=True)
    st.caption(
        "Hyperinflation episodes (inflation at the peak above 100%) dropped. Coefficients are associations in "
        "a heterogeneous panel, not causal effects; one specification only (logged in the research log)."
    )

with st.expander("All cycles for a country"):
    iso = st.selectbox("Country", sorted(cyc["country"].unique()), index=None, placeholder="Choose a country")
    if iso:
        st.dataframe(cyc[cyc["country"] == iso].round(2), use_container_width=True, hide_index=True)

footer(research_series=True)
