import pandas as pd
import streamlit as st

from components import footer, header, sidebar_controls
from portfolio_ui import DISCLAIMER, SLEEVE_LABEL, bundle, name, score_css, sleeve

header(
    "Market scanner",
    "Every instrument of the universe scored by every signal family, held or not: where the opportunities and "
    "the risks are across the whole market.",
)
ctl = sidebar_controls()
b = bundle()
conf = b["config"]["model"]["confidence"] | {"news": b.get("news_confidence", 0.0)}
v = pd.DataFrame(b["views"]).reindex(b["mu"].index)
c = pd.Series({k: conf.get(k, 0.0) for k in v.columns})
combined = (v.fillna(0) * c).sum(axis=1) / (v.notna() * c).sum(axis=1).replace(0, float("nan"))
tab = v.assign(**{"combined (confidence-weighted)": combined})
tab.insert(0, "sleeve", [SLEEVE_LABEL.get(sleeve(b, a), "") for a in tab.index])
tab["weight"] = b["target"].reindex(tab.index).fillna(0)
tab["active vs benchmark"] = tab["weight"] - b["w_eq"].reindex(tab.index).fillna(0)
tab.index = [name(b, a) for a in tab.index]
sl = st.multiselect("Sleeves", sorted(tab["sleeve"].unique()), key="scan_sleeves")
if sl:
    tab = tab[tab["sleeve"].isin(sl)]
tab = tab.sort_values("combined (confidence-weighted)", ascending=False)
num = [x for x in tab.columns if x not in ("sleeve", "weight", "active vs benchmark")]
st.dataframe(
    tab.style.format(
        {x: "{:+.2f}" for x in num} | {"weight": "{:+.1%}", "active vs benchmark": "{:+.1%}"}, na_rep=""
    ).map(score_css, subset=num),
    use_container_width=True,
    height=36 * (len(tab) + 1),
)
held = tab["weight"].abs() > 0.005
opp = tab[~held & (tab["combined (confidence-weighted)"].abs() > 0.3)]
if not opp.empty:
    st.markdown(
        "**Strong signals on instruments the fund does not hold** (constraints, risk or costs kept them out): "
        + ", ".join(f"{i} ({r['combined (confidence-weighted)']:+.2f})" for i, r in opp.iterrows())
    )
st.caption(
    "Scores from −1 to +1 per family: trend (12-1 month momentum), macro (recession, inflation, stress with fixed "
    "signs), regime (average return in the current growth-inflation quadrant, shrunk), value (5-year reversal within "
    "peers), carry (term spreads, real yields, credit spreads, rate differentials), micro (semiconductor names), house "
    "(dated published views of banks and asset managers), news (gated by H32). Combined: weighted by each family's "
    "Black-Litterman confidence. The weights come from the optimiser, which also weighs risk, correlations and costs."
)
st.caption(DISCLAIMER)
footer()
