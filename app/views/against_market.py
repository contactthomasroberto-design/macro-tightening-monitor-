import streamlit as st

from components import CACHE_TTL, chart, footer, header, sidebar_controls, theme
from macro import plotting as pl
from macro.data import source_label, try_series
from macro.pipeline import backtest_bundle

header(
    "Against the market",
    "Do the models add anything to market prices and to the professional consensus? Backtests since 1990.",
)
ctl = sidebar_controls()
th = theme()


@st.cache_resource(ttl=CACHE_TTL, show_spinner="Running backtests…")
def _bundle():
    return backtest_bundle()


b = _bundle()
fmt = {"RMSE": "{:.3f}", "MAE": "{:.3f}", "bias (forecast − realised)": "{:+.3f}"}
tfmt = {
    "DM stat (+ = forecast better)": "{:+.2f}",
    "DM p": "{:.3f}",
    "slope b": "{:+.2f}",
    "t": "{:+.2f}",
    "p (b > 0)": "{:.3f}",
    "outcome on forecast's side": "{:.0%}",
}

st.subheader("Fed path: average fed funds rate over the next 12 months")
f = b["fed"]
st.dataframe(f["scores"].style.format(fmt), use_container_width=True)
st.dataframe(f["tests"].style.format(tfmt), use_container_width=True)
st.markdown(
    "- **Market**: the 1-year Treasury yield at the forecast date. **Rule**: a partial-adjustment policy rule "
    "re-estimated every month on data available then (inputs lagged for publication), iterated 12 months ahead "
    "with inflation and the output gap held constant. **No change**: today's fed funds rate.\n"
    "- **Encompassing slope b**: regression of the market's error on the rule's disagreement with the market. "
    "b > 0 would mean the rule knows something the market does not; b ≈ 0 means it does not.\n"
    "- Latest-vintage (revised) inflation and GDP flatter the rule: a real-time test would be harder still."
)
fc = f["forecasts"].copy()
fig = pl.line_chart(
    fc[["realised", "market (1Y yield)", "rule"]],
    "Forecasts of the next 12 months' average fed funds rate, dated at the forecast",
    source_label("DFF", "DGS1", "PCEPILFE", "GDPC1", "GDPPOT"),
    f"{fc.index[-1]:%Y-%m-%d}",
    yaxis="%",
    rec=try_series("USREC"),
    theme=th,
)
chart(fig, fc, key="bt_fed", full_history=True)

st.subheader("Inflation: our 12-month CPI forecast against the professional consensus")
inf = b["inflation"]
if inf["scores"].empty:
    st.info("SPF forecasts not available.")
else:
    st.dataframe(inf["scores"].style.format(fmt), use_container_width=True)
    st.dataframe(inf["tests"].style.format(tfmt), use_container_width=True)
    st.caption(
        "Same origins and target (CPI inflation over the next 12 months); SPF: Philadelphia Fed Survey of "
        "Professional Forecasters, median. Diebold-Mariano with the Harvey-Leybourne-Newbold correction."
    )
st.caption("Pre-registered hypotheses H20 and H21 and their results: docs/research_log.md.")
footer()
