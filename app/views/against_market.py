import pandas as pd
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
    "- Latest-vintage (revised) inflation and GDP flatter the rule: the real-time test below is the fair one."
)
rt = b.get("fed_realtime")
st.markdown("**Real-time test** (the rule sees only the data published at each date, ALFRED vintages)")
if rt is None:
    st.info(
        "Pending: needs the ALFRED vintages of core PCE, real GDP and potential GDP, downloaded by the refresh "
        "workflow once the repository secret FRED_API_KEY exists (free key, fredaccount.stlouisfed.org). "
        "Research log H26."
    )
else:
    st.dataframe(rt["scores"].style.format(fmt), use_container_width=True)
    st.dataframe(rt["tests"].style.format(tfmt), use_container_width=True)
    st.caption(
        "First vintages used: "
        + ", ".join(f"{k} {v}" for k, v in rt["first vintage"].items())
        + ". Origins before a series' first vintage are dropped."
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
st.subheader("Inflation: are the uncertainty bands honest?")
iv = b.get("intervals")
if iv is not None and not iv.empty:
    show = iv.set_index(["model", "h"]).rename_axis(["model", "horizon (months)"])
    st.dataframe(
        show.style.format(
            {c: "{:.0%}" for c in show.columns if c.startswith("coverage")}
            | {
                "PIT p (all origins)": "{:.3f}",
                "PIT p (non-overlapping, median)": "{:.3f}",
            }
        ),
        use_container_width=True,
    )
    c12 = iv[(iv["model"] == "COMB") & (iv["h"] == 12)].iloc[0]
    mi = b.get("interval_misses", pd.Series(dtype=int))
    yrs = ", ".join(f"{y} ({n})" for y, n in mi.items())
    st.markdown(
        f"At 12 months the 68% band holds **{c12['coverage normal 68']:.0%}** of outcomes (slightly too wide) and "
        f"the 95% band only **{c12['coverage normal 95']:.0%}** (too narrow: the tails are underestimated). Using "
        f"the empirical quantiles of past errors instead gives {c12['coverage empirical 95']:.0%}: the shape of the "
        f"distribution is not the problem. The {int(mi.sum())} misses of the 95% band are clustered by forecast "
        f"year: {yrs}; that is regime breaks (oil and the financial crisis, Covid, the reopening), not a steady "
        "under-statement. Read the 95% band as the range outside a regime break, not as a bound."
    )
    st.caption(
        "Coverage: share of realised outcomes inside the band, each band built only from errors known at the "
        "forecast date. PIT p: Kolmogorov-Smirnov test of uniformity of the probability integral transform; the "
        "all-origins test rejects because overlapping 12-month forecasts are autocorrelated, the non-overlapping "
        "subsamples (one origin every h months) do not reject. Research log H25."
    )
st.caption("Pre-registered hypotheses H20, H21, H25, H26 and their results: docs/research_log.md.")
footer()
