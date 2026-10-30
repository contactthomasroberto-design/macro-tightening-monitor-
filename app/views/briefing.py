import pandas as pd
import streamlit as st

from components import CACHE_TTL, footer, header, show_status, sidebar_controls
from macro import signposts as sp
from macro.data import try_series
from macro.pipeline import backtest_bundle, forecast_book_bundle, leading_bundle, markets_bundle

header(
    "Briefing",
    "One page, read in a minute: thresholds that would change the view, what moved, risks, and how much the "
    "models are worth.",
)
ctl = sidebar_controls()


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def _signposts():
    return sp.evaluate(try_series)


@st.cache_resource(ttl=CACHE_TTL, show_spinner="Loading results…")
def _bundles():
    return markets_bundle(), leading_bundle(), forecast_book_bundle(), backtest_bundle()


mk, ld, fb, bt = _bundles()

# ------------------------------------------------------------------ signposts
st.subheader("Signposts")
sg = _signposts()
crossed = sg[sg["crossed"] == True]  # noqa: E712
if crossed.empty:
    show_status("good", "No signpost crossed. The view in the latest research note stands.")
else:
    for _, r in crossed.iterrows():
        show_status(
            "critical",
            f"**{r['label']}** at {r['latest']:.2f}{r['unit']} is {r['op']} {r['threshold']}"
            f"{r['unit']}: {r['meaning']}.",
        )
tab = sg[["label", "latest", "op", "threshold", "distance", "date", "meaning"]].copy()
tab.insert(
    1,
    "status",
    [
        "crossed" if c else ("close" if d is not None and d == d and abs(d) / (abs(t) + 1e-9) < 0.1 else "")
        for c, d, t in zip(sg["crossed"], tab["distance"], tab["threshold"], strict=True)
    ],
)
for _, r in tab[tab["status"] == "close"].iterrows():
    show_status(
        "warning",
        f"**{r['label']}** at {r['latest']:.2f} is close to its threshold ({r['op']} {r['threshold']:g}): "
        f"{r['meaning']}.",
    )
st.dataframe(
    tab.set_index("label").style.format(
        {"latest": "{:.2f}", "threshold": "{:g}", "distance": "{:+.2f}"}, na_rep=""
    ),
    use_container_width=True,
)
st.caption(
    "Distance: how far the latest value is from the threshold, in the signpost's unit. 'close': within 10% of "
    "the threshold. A newly crossed signpost also opens a GitHub issue (e-mailed to the owner)."
)

c1, c2 = st.columns(2)
# ------------------------------------------------------------------ what moved
with c1:
    st.subheader("What moved (1 month, in σ)")
    d = mk["dashboard"]
    if not d.empty:
        top = d.loc[d["z 1M"].abs().sort_values(ascending=False).index[:6], ["z 1M", "1M", "unit"]]
        for name, r in top.iterrows():
            st.markdown(f"- **{name}**: {r['1M']:+.2f} {r['unit']} ({r['z 1M']:+.1f}σ)")
    s = mk["stress"].value
    if s is not None:
        st.markdown(f"Stress index **{s.iloc[-1]:+.2f}** (z), {s.iloc[-1] - s.iloc[-22]:+.2f} over a month.")
    sp_ = mk["regime_spells"]
    if sp_ is not None:
        st.markdown(f"Cross-asset regime: **{sp_['current']}** since {sp_['since']:%d %b %Y}.")

# ------------------------------------------------------------------ recession
with c2:
    st.subheader("Recession risk, 12 months")
    lt = ld["table"]
    if not lt.empty:
        best = lt["AUC"].idxmax()
        st.markdown(
            f"- Best out-of-sample market model ({best}): **{100 * lt.loc[best, 'probability now']:.0f}%**"
        )
        fed = ld["fed_ebp_prob"]
        if fed is not None and not fed.dropna().empty:
            st.markdown(
                f"- Fed Board EBP model: **{100 * fed.dropna().iloc[-1]:.0f}%** ({fed.dropna().index[-1]:%b %Y})"
            )
        st.markdown(
            f"- 10Y-3M spread model: {100 * lt.loc['10Y-3M spread', 'probability now']:.0f}% (weak out of "
            f"sample: AUC {lt.loc['10Y-3M spread', 'AUC']:.2f})"
        )

# ------------------------------------------------------------------ honesty box
st.subheader("Do the models beat the market?")
f = bt["fed"]
fs, ft = f["scores"], f["tests"]
inf = bt["inflation"]
msg = [
    f"**Fed path, 12 months**: the 1-year Treasury yield beats our policy rule (RMSE {fs.loc['market (1Y yield)', 'RMSE']:.2f} "
    f"vs {fs.loc['rule', 'RMSE']:.2f} pp, {int(fs.loc['rule', 'n'])} months); the rule adds no information to the market "
    f"(encompassing slope {ft.loc['rule', 'slope b']:+.2f}, p = {ft.loc['rule', 'p (b > 0)']:.2f}).",
]
if not inf["scores"].empty:
    isc, its = inf["scores"], inf["tests"]
    msg.append(
        f"**Inflation, 12 months**: our combination and the SPF median are statistically tied (RMSE "
        f"{isc.loc['our combination', 'RMSE']:.2f} vs {isc.loc['SPF median', 'RMSE']:.2f}; DM p = "
        f"{its.loc['our combination', 'DM p']:.2f})."
    )
ftab = fb["table"]
if not ftab.empty:
    skill = ftab[ftab["BSS 90% low"] > 0].index.tolist()
    msg.append(
        f"**Directional forecasts, 13 weeks**: demonstrated skill on {len(skill)} of {len(ftab)} variables"
        + (f" ({', '.join(skill)})" if skill else "")
        + "; the others do no better than the historical frequency."
    )
for m in msg:
    st.markdown(f"- {m}")
st.caption(
    "Read the market's pricing first; use the models to understand it and to stress it, not to bet against it. "
    "Details: Governance → Against the market, Forecast book."
)

# ------------------------------------------------------------------ forecast book
if not ftab.empty:
    st.subheader("Forecast book: probability of a rise in 13 weeks")
    show = ftab[
        ["P(higher in 13 weeks)", "Brier skill vs base rate", "BSS 90% low", "BSS 90% high", "as of"]
    ].copy()
    show["as of"] = pd.to_datetime(show["as of"]).dt.date
    show["skill"] = ["demonstrated" if lo > 0 else "none shown" for lo in show["BSS 90% low"]]
    st.dataframe(
        show.style.format(
            {
                "P(higher in 13 weeks)": "{:.0%}",
                "Brier skill vs base rate": "{:+.3f}",
                "BSS 90% low": "{:+.3f}",
                "BSS 90% high": "{:+.3f}",
            }
        ),
        use_container_width=True,
    )
    st.caption(
        "Probabilities from momentum, value and carry signals (research log H22). A probability near 50% with "
        "no demonstrated skill says: no edge. Recorded every week and scored at maturity."
    )
st.caption(f"Data as of {pd.Timestamp(mk['as_of']):%d %b %Y}.")
footer()
