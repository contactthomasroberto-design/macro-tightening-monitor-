import pandas as pd
import streamlit as st

from components import CACHE_TTL, chart, footer, header, sidebar_controls, theme
from macro import plotting as pl
from macro.data import source_label
from macro.pipeline import leading_bundle

header(
    "Recession signals from markets",
    "Yield-curve and credit-market recession models, compared out of sample, against the Fed Board's own.",
)
ctl = sidebar_controls()
th = theme()


@st.cache_resource(ttl=CACHE_TTL, show_spinner="Estimating recession models…")
def _bundle():
    return leading_bundle()


b = _bundle()
tab = b["table"]
if tab.empty:
    st.warning("Not enough data for the recession models.")
    footer()
    st.stop()
src = source_label("DGS10", "DGS3MO", "DGS2", "DGS1", "EBP", "USREC")
best = tab["AUC"].idxmax()

# ------------------------------------------------------------------ headline
cols = st.columns(len(tab) + 1)
for c, (name, r) in zip(cols, tab.iterrows(), strict=False):
    c.metric(
        name, f"{100 * r['probability now']:.0f}%", f"AUC {r['AUC']:.2f} out of sample", delta_color="off"
    )
fed = b["fed_ebp_prob"]
if fed is not None and not fed.dropna().empty:
    f = fed.dropna()
    cols[-1].metric(
        "Fed Board EBP model (published)",
        f"{100 * f.iloc[-1]:.0f}%",
        f"{f.index[-1]:%b %Y}",
        delta_color="off",
    )
st.caption(
    "Probability of an NBER recession starting in the next 12 months, from probits estimated on all months whose "
    f"outcome is known. Best out-of-sample discrimination: **{best}**. Five models, fixed before estimation "
    "(research log H17)."
)

view = st.segmented_control(
    "View",
    ["Out-of-sample scores", "Probabilities over time", "Signals"],
    default="Out-of-sample scores",
    key="rec_view",
)

if view in (None, "Out-of-sample scores"):
    show = tab[
        [
            "AUC",
            "Brier",
            "Brier skill vs base rate",
            "BSS 90% low",
            "BSS 90% high",
            "log score",
            "OOS months",
            "OOS from",
            "coefficients (HAC t)",
            "pseudo R²",
        ]
    ]
    st.dataframe(
        show.style.format(
            {
                "AUC": "{:.2f}",
                "Brier": "{:.3f}",
                "Brier skill vs base rate": "{:+.2f}",
                "BSS 90% low": "{:+.2f}",
                "BSS 90% high": "{:+.2f}",
                "log score": "{:.3f}",
                "pseudo R²": "{:.2f}",
            }
        ),
        use_container_width=True,
    )
    st.markdown(
        "- **AUC**: chance that the model ranks a pre-recession month above a normal month (0.5 = coin toss).\n"
        "- **Brier skill**: improvement of the squared error over always forecasting the historical frequency "
        "(0 = no skill); the 90% interval comes from a moving-block bootstrap (24-month blocks).\n"
        "- Pseudo out of sample: at each month from 1990, each model is re-estimated only on months whose 12-month "
        "outcome was already known, then forecasts. Two optimisms remain: NBER dates are announced months later, "
        "and the excess bond premium's whole history is revised each month."
    )
elif view == "Probabilities over time":
    oos = pd.concat({k: v["p"] * 100 for k, v in b["oos"].items()}, axis=1)
    if fed is not None:
        oos["Fed Board EBP model (published, in-sample)"] = fed.dropna().resample("MS").last() * 100
    fig = pl.line_chart(
        oos.loc["1990-01-01":],
        "Out-of-sample recession probabilities, next 12 months",
        src + "; Fed Board staff (EBP model)",
        f"{oos.dropna(how='all').index[-1]:%Y-%m-%d}",
        yaxis="%",
        rec=b["usrec"],
        theme=th,
    )
    chart(fig, oos, key="rec_oos", full_history=True)
    st.caption(
        "Shaded: NBER recessions. Each line is what the model would have said at the time, with the data then "
        "available for estimation (latest vintage of the inputs)."
    )
else:
    X = b["features"].loc["1980-01-01":]
    X.columns = ["10Y minus 3M", "Near-term forward spread (2·y2 − y1 − 3M)", "Excess bond premium"]
    fig = pl.line_chart(
        X,
        "The three signals: spreads in percentage points, EBP in percentage points of spread",
        src,
        f"{X.dropna(how='all').index[-1]:%Y-%m-%d}",
        yaxis="pp",
        rec=b["usrec"],
        theme=th,
        hline=0,
    )
    chart(fig, X, key="rec_signals", full_history=True)
    st.caption(
        "Near-term forward spread: Engstrom and Sharpe (Fed Board, 2018) use the forward 3-month rate six quarters "
        "ahead; the free proxy here is the one-year rate one year ahead implied by 1- and 2-year yields. Excess bond "
        "premium: Gilchrist and Zakrajšek, published monthly by Fed Board staff."
    )
footer()
