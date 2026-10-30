import pandas as pd
import streamlit as st

from components import CACHE_TTL, chart, footer, header, sidebar_controls, theme
from macro import forecast_book as fbk
from macro import plotting as pl
from macro.config import ROOT
from macro.pipeline import forecast_book_bundle, forecast_book_inputs

header(
    "Forecast book",
    "Probabilities of a rise over 13 weeks from momentum, value and carry, scored out of sample and live.",
)
ctl = sidebar_controls()
th = theme()


@st.cache_resource(ttl=CACHE_TTL, show_spinner="Scoring the forecast book…")
def _bundle():
    return forecast_book_bundle()


b = _bundle()
tab = b["table"]
if tab.empty:
    st.warning("Not enough data for the forecast book.")
    footer()
    st.stop()

view = st.segmented_control("View", ["Scores", "Calibration", "Live record"], default="Scores", key="fb_view")
if view in (None, "Scores"):
    show = tab[
        [
            "P(higher in 13 weeks)",
            "AUC",
            "Brier skill vs base rate",
            "BSS 90% low",
            "BSS 90% high",
            "hit rate",
            "weeks",
            "from",
        ]
    ]
    st.dataframe(
        show.style.format(
            {
                "P(higher in 13 weeks)": "{:.0%}",
                "AUC": "{:.2f}",
                "Brier skill vs base rate": "{:+.3f}",
                "BSS 90% low": "{:+.3f}",
                "BSS 90% high": "{:+.3f}",
                "hit rate": "{:.0%}",
            }
        ),
        use_container_width=True,
    )
    with st.expander("Signals today and coefficients"):
        st.dataframe(tab[["signals today", "coefficients"]].astype(str), use_container_width=True)
    st.markdown(
        "- Signals fixed in advance (research log H22): 26-week momentum, 5-year value z-score, carry "
        "(term spread, rate differentials, the spread itself; none for Brent).\n"
        "- Pseudo out of sample: each week from 2005, the logistic model is fitted only on weeks whose 13-week "
        "outcome was known. Brier skill > 0 means better than the historical frequency of rises; the 90% interval "
        "comes from a 26-week block bootstrap.\n"
        "- Hit rate alone misleads when one direction dominates (equities rise most quarters): read the skill score."
    )
elif view == "Calibration":
    var = st.selectbox("Variable", list(b["reliability"]), key="fb_var")
    rel = b["reliability"][var]
    st.dataframe(
        rel.style.format({"mean_forecast": "{:.0%}", "observed": "{:.0%}"}), use_container_width=True
    )
    st.caption("A calibrated model: observed frequency close to the mean forecast in every bin.")
    o = b["oos"][var]
    roll = pd.concat({"forecast probability": o["p"], "base rate": o["base rate"]}, axis=1)
    fig = pl.line_chart(
        roll,
        f"{var}: out-of-sample probability of a rise in 13 weeks",
        "Macro Tightening Monitor",
        f"{o.index[-1]:%Y-%m-%d}",
        yaxis="probability",
        theme=th,
        hline=0.5,
    )
    chart(fig, roll, key="fb_prob", full_history=True)
else:
    path = ROOT / "archive" / "forecast_book.csv"
    if not path.exists():
        st.info(
            "The live record starts with the next scheduled refresh: each week's probabilities are archived and "
            "scored when their 13 weeks are over."
        )
    else:
        arc = pd.read_csv(path)
        lv, _ = forecast_book_inputs()
        sc = fbk.score_archive(arc, lv)
        st.markdown(f"{len(arc)} forecasts recorded since {arc['week'].min()}; {len(sc)} matured.")
        if not sc.empty:
            st.metric("Live Brier score (lower is better; 0.25 = coin toss)", f"{sc['brier'].mean():.3f}")
            st.dataframe(sc.tail(50), use_container_width=True)
        st.dataframe(arc.tail(30), use_container_width=True)
footer()
