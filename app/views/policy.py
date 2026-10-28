import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import chart, footer, header, result_meta, show_status, sidebar_controls, theme
from macro import panels
from macro import plotting as pl
from macro import policy as pol
from macro.config import assumptions
from macro.data import source_label, try_series
from macro.pipeline import cross_bank_bundle, policy_bundle

header(
    "Policy",
    "Are the central banks behind the curve? Rules, r* uncertainty and an estimated reaction function.",
)
ctl = sidebar_controls()
th = theme()
bank = st.radio("Central bank", ["fed", "ecb", "boj"], horizontal=True, format_func=str.upper, key="pol_bank")
color = pl.ENTITY[bank]


@st.cache_resource(show_spinner="Estimating reaction functions (first run only)…")
def _bundle(b: str):
    return policy_bundle(b)


@st.cache_resource(show_spinner=False)
def _cross():
    return cross_bank_bundle()


b = _bundle(bank)
pp = b["panel"]
ids = pp["ids"]
cb = assumptions()["central_banks"][bank]
pi_star = float(cb["inflation_target"])
q = pp["quarterly"]
cur = b["current"]
src = source_label(*[ids[k] for k in ("rate", "infl", "unemp", "gdp", "pot") if k in ids])
as_of = pd.Timestamp(cur["date"]).strftime("%Y-%m")
rec = try_series({"fed": "USREC", "ecb": "EUROREC"}.get(bank, "USREC"))
lo, hi = ctl["rstar_range"]

# ------------------------------------------------------------------ r* inputs
st.subheader("r* is an input with a range, not a point")
pub = b["rstar_published"]
cols = st.columns(max(len(pub), 1) + 1)
for (sid, v), c in zip(pub.items(), cols, strict=False):
    ref = pd.Timestamp(v["date"]).strftime("%Y-%m")
    c.metric(
        sid.replace("_", " "),
        f"{v['value']:.2f}%",
        help=f"Latest published estimate (reference period {ref})",
    )
cols[-1].metric("User range", f"{lo:.2f}% to {hi:.2f}%")
if not pub:
    st.info("No published r* estimate for this bank in the catalogue: only the user range is used.")
mid = (lo + hi) / 2

# ------------------------------------------------------------------ rule prescriptions
paths = pol.rule_paths(q, mid, ctl["rules"], pi_star)
hist = pd.concat([q["i"].rename("Actual policy rate"), paths], axis=1).loc[ctl["start"] :]
taylor_now = pol.taylor(
    cur["pi"], cur["y"], mid, pi_star, ctl["rules"]["taylor1993"]["a_pi"], ctl["rules"]["taylor1993"]["a_gap"]
)
gap_now = cur["i"] - taylor_now
word = "below" if gap_now < 0 else "above"
fig = pl.line_chart(
    hist,
    f"{bank.upper()} policy rate is {abs(gap_now):.2f} pp {word} the Taylor (1993) prescription (r* = {mid:.2f}%)",
    src,
    as_of,
    yaxis="%",
    colors=[color, *pl.SERIES_ORDER],
    rec=rec,
    theme=th,
)
chart(fig, hist, key=f"rules_{bank}")
st.caption(
    f"Inflation measure: {ids['infl_label']} yoy; {pp['gap_note']}. Prescriptions are unconstrained by the lower bound. "
    "Inertial and first-difference rules start from the previous quarter's actual rate."
)

# ------------------------------------------------------------------ heatmap
st.subheader("Does the conclusion survive r* uncertainty?")
rgrid = np.round(np.arange(lo, hi + 1e-9, ctl["rstar_step"]), 2)
agrid = np.round(np.arange(1.0, 2.51, 0.25), 2)
heat = pol.rstar_heatmap(
    cur["pi"], cur["y"], cur["i"], rgrid, agrid, pi_star, ctl["rules"]["taylor1993"]["a_gap"]
)
robust, side = pol.conclusion_robust(heat)
fig = go.Figure(
    go.Heatmap(
        z=heat.to_numpy(),
        x=[f"{r:.2f}" for r in heat.columns],
        y=[f"{a:.2f}" for a in heat.index],
        colorscale="RdBu_r",
        zmid=0,
        colorbar={"title": "rule − actual (pp)"},
        text=np.round(heat.to_numpy(), 2),
        texttemplate="%{text}",
    )
)
fig.update_xaxes(title_text="r* (%)", type="category")
fig.update_yaxes(title_text="inflation coefficient a_π", type="category")
verdict = (
    f"Across the whole r* range the rule is {side} the actual rate"
    if robust
    else "The sign of the policy gap depends on r* and the inflation coefficient"
)
pl.base_layout(fig, verdict, src, as_of, th, height=420)
chart(fig, heat, key=f"heat_{bank}")
if robust:
    show_status(
        "good" if side == "below" else "warning",
        f"Robust: Taylor prescription {side} the actual rate for every (r*, a_π) in the grid "
        f"({'policy at least as tight as the rule' if side == 'below' else 'policy looser than the rule: behind the curve on this metric'}).",
    )
else:
    show_status(
        "warning",
        "Not robust: the headline conclusion does not hold across the r* range. No single verdict is given.",
    )

# ------------------------------------------------------------------ stance
st.subheader("Real policy rate vs r*")
stance = pol.policy_stance(cur["i"], cur["pi"], (lo, hi))
real = (pp["monthly"]["i"] - pp["monthly"]["pi"]).loc[ctl["start"] :]
fig = pl.line_chart(
    real.to_frame("real policy rate (i − π)"),
    f"Real policy rate {stance['real_rate']:.2f}%: {stance['stance']}",
    src,
    as_of,
    yaxis="%",
    colors=[color],
    rec=rec,
    theme=th,
)
fig.add_hrect(y0=lo, y1=hi, fillcolor="rgba(120,120,120,0.15)", line_width=0, annotation_text="r* range")
chart(fig, real, key=f"real_{bank}")

# ------------------------------------------------------------------ priced vs prescribed
st.subheader("Priced vs prescribed")
mp = panels.market_priced(bank, assumptions()["market_pricing"].get(f"{bank}_terminal_rate"))
if cur["y2"] is not None or (mp and mp.get("value") is not None):
    priced, priced_src = pol.priced_rate_proxy(cur["y2"] if cur["y2"] is not None else np.nan, cur["i"], mp)
    presc = {}
    for r in (lo, mid, hi):
        presc[f"Taylor (1993), r*={r:.2f}"] = pol.taylor(
            cur["pi"],
            cur["y"],
            r,
            pi_star,
            ctl["rules"]["taylor1993"]["a_pi"],
            ctl["rules"]["taylor1993"]["a_gap"],
        )
    rf = b["rf_full"]
    if rf.value is not None:
        t = rf.value["estimate"]
        c_gap = t["c (output gap)"] if t["c (output gap)"] == t["c (output gap)"] else 0.0
        presc["Estimated reaction function (long-run target)"] = (
            t["a"] + t["b (inflation)"] * cur["pi"] + c_gap * cur["y"]
        )
    tab = pol.priced_vs_prescribed(cur["i"], priced, presc, step=cb["step_bp"] / 100)
    st.dataframe(tab.round(2), use_container_width=True)
    st.caption(
        f"Priced path source: {priced_src}. Moves in {cb['step_bp']}bp steps. Not forecasts of policy decisions."
    )
    inf_rev = [
        pol.reverse_inflation(
            priced,
            cur["y"],
            r,
            pi_star,
            ctl["rules"]["taylor1993"]["a_pi"],
            ctl["rules"]["taylor1993"]["a_gap"],
        )
        for r in (lo, hi)
    ]
    st.markdown(
        f"**Reverse view.** With the current output gap ({cur['y']:.1f}%), current pricing is consistent with "
        f"{ids['infl_label']} inflation between **{min(inf_rev):.1f}%** and **{max(inf_rev):.1f}%** under the Taylor "
        f"rule across the r* range (actual: {cur['pi']:.1f}%)."
    )
else:
    st.info(
        "No priced path available (no 2-year yield in the catalogue for this bank and no dated OIS entry in assumptions.yaml)."
    )

# ------------------------------------------------------------------ reaction function
st.subheader("Estimated reaction function")
st.latex(r"i_t = \rho\, i_{t-1} + (1-\rho)\,(a + b\,\pi_t + c\,y_t) + \varepsilon_t")
tabs = {
    "Full sample": b["rf_full"],
    "Pre-2008": b["rf_pre2008"],
    "Post-2008 (excl. lower bound)": b["rf_post2008"],
}
rows = []
for name, r in tabs.items():
    if r.value is None:
        continue
    t = r.value
    rows.append(
        {
            "sample": name,
            "N (quarters)": r.n_obs,
            "ρ": t.loc["rho", "estimate"],
            "b (inflation)": t.loc["b (inflation)", "estimate"],
            "b 90% CI": f"[{t.loc['b (inflation)', 'lower']:.2f}, {t.loc['b (inflation)', 'upper']:.2f}]",
            "c (gap)": t.loc["c (output gap)", "estimate"],
            "P(b ≤ 1)": r.extra["taylor_principle_p"],
        }
    )
st.dataframe(pd.DataFrame(rows).set_index("sample").round(3), use_container_width=True)
rf = b["rf_full"]
if rf.value is not None:
    ok = rf.extra["taylor_principle_p"] < 0.05
    show_status(
        "good" if ok else "warning",
        f"Taylor principle (b > 1) {'holds' if ok else 'is not established'} in the full sample "
        f"(one-sided p = {rf.extra['taylor_principle_p']:.3f}).",
    )
    result_meta(rf)
roll = b["rf_rolling"]
if not roll.empty:
    fig = pl.band_chart(
        roll["b"],
        roll["lower"],
        roll["upper"],
        "Rolling 12-year inflation response b",
        src,
        as_of,
        name="b",
        band_name="90% band",
        base_color=color,
        hline=1.0,
        theme=th,
    )
    chart(fig, roll, key=f"rfroll_{bank}")

# ------------------------------------------------------------------ cross-bank
st.subheader("Cross-bank synchronisation and FX")
cx = _cross()
rates = cx["rates"].loc[ctl["start"] :]
fig = pl.line_chart(
    rates.rename(columns=str.upper),
    "Policy rates: Fed, ECB, BoJ",
    source_label("DFF", "EA_DFR", "JP_POLICY"),
    pd.Timestamp(cx["as_of"]).strftime("%Y-%m"),
    yaxis="%",
    colors=[pl.ENTITY[k] for k in rates.columns],
    theme=th,
)
chart(fig, rates, key="rates3")
sync = cx["sync"].loc[ctl["start"] :]
fig = pl.small_multiples(
    sync.rename(
        columns={
            "hiking_share": "share of banks hiking (12m)",
            "avg_corr_12m_changes": "avg correlation of 12m changes (36m)",
        }
    ),
    f"Synchronisation: {100 * sync['hiking_share'].iloc[-1]:.0f}% of the three banks raised rates over the past year",
    source_label("DFF", "EA_DFR", "JP_POLICY"),
    pd.Timestamp(cx["as_of"]).strftime("%Y-%m"),
    ncols=2,
    theme=th,
)
chart(fig, sync, key="sync")
for pair, v in cx["fx"].items():
    be = v["beta"]
    if be.empty:
        continue
    fig = pl.band_chart(
        be["beta"],
        be["lower"],
        be["upper"],
        f"{pair}: weekly % change per 1pp change in {v['label']} (2y rolling)",
        source_label(pair),
        pd.Timestamp(be.index[-1]).strftime("%Y-%m"),
        name="β",
        band_name="90% band",
        hline=0,
        theme=th,
    )
    chart(fig, be, key=f"fx_{pair}")

with st.expander("Limitations"):
    st.markdown(
        "- r* is unobservable; published estimates have wide confidence bands and are revised. Hence the range.\n"
        "- The output gap is model-dependent (CBO potential for the US, Okun proxy for the euro area, none for Japan).\n"
        "- The 2-year yield is a crude proxy for the priced path (term premium ignored); OIS paths are not free.\n"
        "- Reaction-function estimates suffer from the lower bound and from few hiking cycles; samples are split for that reason.\n"
        "- Rule prescriptions are benchmarks, not forecasts of decisions."
    )
footer()
