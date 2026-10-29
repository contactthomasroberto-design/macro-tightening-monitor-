import pandas as pd
import streamlit as st

from components import CACHE_TTL, chart, footer, header, sidebar_controls, theme
from macro import plotting as pl
from macro.data import source_label, try_series
from macro.pipeline import build_views, growth_bundle, inflation_bundle
from markets_ui import bundle

header(
    "Priced against our models",
    "What markets price for policy rates, inflation and recession, set against the project's models and surveys.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()


@st.cache_data(ttl=CACHE_TTL, show_spinner="Loading model results…")
def _views():
    return build_views()


@st.cache_resource(ttl=CACHE_TTL, show_spinner=False)
def _growth():
    return growth_bundle()


@st.cache_resource(ttl=CACHE_TTL, show_spinner=False)
def _inflation():
    return inflation_bundle("US")


def _last(sid: str) -> tuple[float, str] | None:
    s = try_series(sid)
    if s is None or s.dropna().empty:
        return None
    s = s.dropna()
    return float(s.iloc[-1]), f"{s.index[-1]:%Y-%m-%d}"


st.info(
    "A gap between a market price and a model is not a mispricing: market prices include risk premia "
    "(term, inflation, liquidity), and the models have their own errors (shown as bands where they exist). "
    "The table says where they differ, not what to do about it."
)

# ------------------------------------------------------------------ policy
st.subheader("Policy rates")
v = _views()
pvm = v["priced_vs_model"].copy()
pvm["gap (priced minus model)"] = pvm["priced"] - pvm["model (median)"]
st.dataframe(
    pvm.set_index(["bank", "item"]).style.format(
        {
            c: "{:.2f}"
            for c in (
                "priced",
                "model (median)",
                "model 68% low",
                "model 68% high",
                "gap (priced minus model)",
            )
        },
        na_rep="",
    ),
    use_container_width=True,
)
st.caption(
    "Fed: market path from the Atlanta Fed Market Probability Tracker (SOFR options, risk-neutral mean of the 3-month "
    "average rate in 12 months) against the median of the scenario engine; ECB and BoJ: 2-year yields as proxies "
    "(no free OIS curve) against the estimated reaction function's long-run target."
)

# ------------------------------------------------------------------ inflation
st.subheader("Inflation: market compensation, surveys and models")
rows = []
ib = _inflation()
pe = ib.get("prob_exceed")
one_year = [
    (
        "Our model (CPI, 12 months ahead)",
        (pe["point"], "latest") if pe else None,
        "forecast combination, out-of-sample tested",
    ),
    ("Professional forecasters (CPI, next 4 quarters)", _last("SPF_CPI_1Y"), "Philadelphia Fed SPF, median"),
    ("Households (next 12 months)", _last("MICH"), "University of Michigan survey, median"),
]
long_run = [
    (
        "Market: 10-year breakeven",
        _last("T10YIE"),
        "nominal minus TIPS yield; includes inflation risk and liquidity premia",
    ),
    ("Market: 5-year, 5 years ahead", _last("T5YIFR"), "forward breakeven"),
    ("Professional forecasters (CPI, 10 years)", _last("SPF_CPI10"), "Philadelphia Fed SPF, median"),
    (
        "Cleveland Fed model (10 years)",
        _last("EXPINF10YR"),
        "survey, swaps and yields combined; excludes risk premia",
    ),
]
for horizon, items in (("Next 12 months", one_year), ("Long run", long_run)):
    for name, val, note in items:
        if val is None:
            continue
        rows.append({"horizon": horizon, "measure": name, "value (%)": val[0], "as of": val[1], "note": note})
inf_tab = pd.DataFrame(rows).set_index(["horizon", "measure"])
st.dataframe(inf_tab.style.format({"value (%)": "{:.2f}"}), use_container_width=True)
st.caption(
    "There is no free market measure of 1-year inflation (inflation swaps are not public), so the short horizon "
    "compares the model with surveys. Breakevens are CPI-based; the Fed targets PCE inflation, which runs about "
    "0.3 point below CPI on average. "
    + source_label("T10YIE", "T5YIFR", "SPF_CPI10", "EXPINF10YR", "SPF_CPI_1Y", "MICH")
)
lr = (
    pd.concat({k: s for k in ("T10YIE", "T5YIFR", "EXPINF10YR") if (s := try_series(k)) is not None}, axis=1)
    .resample("ME")
    .last()
)
if not lr.empty:
    lr.columns = [
        {"T10YIE": "10Y breakeven", "T5YIFR": "5y5y forward", "EXPINF10YR": "Cleveland Fed 10Y"}[c]
        for c in lr
    ]
    fig = pl.line_chart(
        lr,
        f"Long-run inflation compensation: 10-year breakeven {lr['10Y breakeven'].dropna().iloc[-1]:.2f}%",
        source_label("T10YIE", "T5YIFR", "EXPINF10YR"),
        f"{lr.dropna(how='all').index[-1]:%Y-%m-%d}",
        yaxis="%",
        theme=th,
        hline=2.0,
    )
    chart(fig, lr, key="lr_infl")

# ------------------------------------------------------------------ recession
st.subheader("Recession: the yield curve against our model")
cr = b["curve_recession"]
g = _growth()
rec_model = float(g["recession"].value) if g.get("recession") is not None else None
if cr is not None and cr.value is not None:
    e = cr.extra
    c1, c2, c3 = st.columns(3)
    c1.metric(f"Curve-implied, recession in {e['target_month']:%b %Y}", f"{100 * cr.value:.0f}%")
    if rec_model is not None:
        c2.metric("Our recession model, next 12 months", f"{100 * rec_model:.0f}%")
    c3.metric("10Y minus 3M spread (monthly average)", f"{100 * e['spread_now']:.0f} bp")
    st.caption(
        f"Curve model: probit of an NBER recession 12 months ahead on the 10-year minus 3-month Treasury spread "
        f"(Estrella and Mishkin; the New York Fed's model). Estimated here: slope {e['b']:.2f} "
        f"(s.e. {e['se']['spread']:.2f}), {cr.n_obs} months, pseudo-R² {e['pseudo_r2']:.2f}, in-sample AUC "
        f"{e['auc']:.2f}. Our model combines more indicators (see Growth and recession risk). The two answer "
        "slightly different questions: a recession in a given month a year ahead, against a recession starting "
        "within the next 12 months."
    )
    hist = e["history"].rename("Curve-implied probability").to_frame() * 100
    fig = pl.line_chart(
        hist,
        f"The curve puts the probability of recession in {e['target_month']:%B %Y} at {100 * cr.value:.0f}%",
        source_label("T10Y3M", "USREC") + "; probability dated at the month it refers to",
        cr.as_of,
        yaxis="%",
        rec=try_series("USREC"),
        theme=th,
    )
    chart(fig, hist, key="curve_rec")

# ------------------------------------------------------------------ growth
st.subheader("Growth: nowcasts")
nc = g["nowcast"]
ext = g.get("external_nowcasts", {})
gr = [{"source": f"Our dynamic factor model ({nc['target']})", "real GDP growth, % annualised": nc["point"]}]
gr += [
    {"source": k, "real GDP growth, % annualised": v} for k, v in ext.items() if "GDPNow" in k or "SPF" in k
]
spf = _last("SPF_RGDP_1Y")
if spf is not None:
    gr.append(
        {
            "source": "Professional forecasters, next 4 quarters (mean)",
            "real GDP growth, % annualised": spf[0],
        }
    )
st.dataframe(pd.DataFrame(gr).set_index("source").style.format("{:.1f}"), use_container_width=True)
st.caption("Markets do not price GDP directly; the comparison is between nowcasts and surveys.")
footer()
