import pandas as pd
import streamlit as st

from components import footer, header, sidebar_controls
from portfolio_ui import DISCLAIMER, bundle, name, score_css

header(
    "Why these weights",
    "From the benchmark's equilibrium to the target: the views of each signal family and what they change.",
)
ctl = sidebar_controls()
b = bundle()
cfg = b["config"]
conf = cfg["model"]["confidence"]

st.subheader("Views by signal family (score from −1 to +1)")
v = pd.DataFrame(b["views"]).reindex(b["w_eq"].index)
v.index = [name(b, a) for a in v.index]
v.columns = [f"{c} (confidence {conf.get(c, 0):.0%})" for c in v.columns]
st.dataframe(
    v.style.format("{:+.2f}", na_rep="").map(score_css),
    use_container_width=True,
)
st.caption(
    "Trend: 12-month return skipping the last month, over its volatility. Macro: recession risk (excess bond "
    "premium), inflation (core CPI 3-month annualised against 2.5%) and market stress, with fixed signs by asset "
    "class. Micro: semiconductor names only (see Signals). News: shown, weight 0 until it passes its "
    "out-of-sample test (H30). Confidence: weight of the family in Black-Litterman, fixed before the backtest."
)

st.subheader("Expected excess returns: equilibrium, views, posterior (annual)")
mu = pd.DataFrame(
    {
        "equilibrium π": b["pi"],
        **{f"from {k}": c for k, c in b["view_contribution"].items()},
        "posterior μ": b["mu"],
        "weight": b["target"].reindex(b["mu"].index).fillna(0),
        "benchmark": b["w_eq"].reindex(b["mu"].index).fillna(0),
    }
)
mu.index = [name(b, a) for a in mu.index]
st.dataframe(
    mu.style.format(
        {c: "{:+.2%}" for c in mu.columns if c not in ("weight", "benchmark")}
        | {"weight": "{:.1%}", "benchmark": "{:.1%}"}
    ),
    use_container_width=True,
)
st.caption(
    "π = δ Σ w (He-Litterman reverse optimisation, δ = 2.5): the returns that make the benchmark optimal. "
    "'From trend' etc.: change in the posterior when that family is added to the others. The optimiser then "
    "maximises μ'w − δ/2 w'Σw under the constraints in Rules. Expected returns are model quantities, not forecasts."
)

st.subheader("Macro inputs now")
mn = b["macro_now"]
if not mn.empty:
    cols = st.columns(len(mn))
    lab = {"recession": "Recession risk (EBP)", "inflation": "Inflation pressure", "stress": "Market stress"}
    for c, (k, val) in zip(cols, mn.items(), strict=True):
        c.metric(lab.get(k, k), f"{val:+.2f}", help="Scaled to [−1, +1]; positive = more of it")
st.caption(DISCLAIMER)
footer()
