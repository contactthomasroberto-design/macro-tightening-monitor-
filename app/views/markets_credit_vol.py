import pandas as pd
import streamlit as st

from components import chart, footer, header, sidebar_controls, theme
from macro import plotting as pl
from macro.data import source_label, try_series
from macro.markets import business_daily, percentile_of_last
from markets_ui import bundle, ordinal

header(
    "Credit and volatility",
    "Credit spreads, implied against realised volatility in equities and rates.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()
as_of = pd.Timestamp(b["as_of"]).strftime("%Y-%m-%d")
rec = try_series("USREC")

# ------------------------------------------------------------------ credit
st.subheader("Credit spreads")
cr = {
    "Baa minus 10Y Treasury (Moody's)": try_series("BAA10Y"),
    "IG OAS (ICE BofA)": try_series("BAMLC0A0CM"),
    "HY OAS (ICE BofA)": try_series("BAMLH0A0HYM2"),
}
cr = {k: business_daily(v) * 100 for k, v in cr.items() if v is not None}
if cr:
    df = pd.concat(cr, axis=1)
    baa = (
        df["Baa minus 10Y Treasury (Moody's)"].dropna() if "Baa minus 10Y Treasury (Moody's)" in df else None
    )
    title = "Credit spreads"
    if baa is not None and not baa.empty:
        p = percentile_of_last(baa, 30)
        title = (
            f"Credit is {'tight' if p < 25 else 'wide' if p > 75 else 'near its norm'}: Baa-Treasury spread "
            f"{baa.iloc[-1]:.0f} bp, {ordinal(p)} percentile since {max(baa.index[0], baa.index[-1] - pd.DateOffset(years=30)):%Y}"
        )
    fig = pl.line_chart(
        df.resample("W-FRI").last(),
        title,
        source_label("BAA10Y", "BAMLC0A0CM", "BAMLH0A0HYM2"),
        as_of,
        yaxis="bp",
        rec=rec,
        theme=th,
    )
    chart(fig, df, key="credit")
    st.caption(
        "FRED serves only the last three years of the ICE BofA option-adjusted spreads; the Moody's Baa "
        "spread (from 1986) gives the long history. HY OAS: spread of US high-yield bonds over Treasuries, "
        "adjusted for embedded options."
    )

# ------------------------------------------------------------------ equity vol
st.subheader("Equity volatility: implied against realised")
vp = b["vol_premium"]
if vp is not None:
    vp = vp.dropna()
    prem = (vp.iloc[:, 0] - vp.iloc[:, 1]).rename("Premium (implied minus realised)")
    p = percentile_of_last(prem, 10)
    fig = pl.line_chart(
        pd.concat([vp, prem], axis=1).resample("W-FRI").last(),
        f"Options price {prem.iloc[-1]:+.1f} vol points over realised volatility ({ordinal(p)} percentile over 10 years)",
        source_label("VIX", "SPX") + "; realised: 21-day standard deviation of daily log returns, annualised",
        as_of,
        yaxis="volatility, % a year",
        theme=th,
        hline=0,
    )
    chart(fig, vp, key="vrp")
    st.caption(
        "The VIX prices the next 30 days; realised volatility measures the past 21 trading days, so the gap mixes "
        "the volatility risk premium with expected changes in volatility. A negative gap is rare and usually "
        "means realised volatility has just spiked."
    )

# ------------------------------------------------------------------ rates vol
st.subheader("Rates volatility: implied against realised")
rv = b["rates_vol"]
if rv is not None:
    rv = rv.dropna()
    ratio_s = (rv.iloc[:, 0] / rv.iloc[:, 1]).replace([float("inf")], float("nan")).dropna()
    ratio = float(ratio_s.iloc[-1])
    fig = pl.line_chart(
        rv.resample("W-FRI").last(),
        f"Rates options price {rv.iloc[-1, 0]:.0f} bp a year against {rv.iloc[-1, 1]:.0f} bp realised on the 10-year",
        source_label("MOVE", "DGS10") + "; realised: 21-day standard deviation of daily changes, annualised",
        as_of,
        yaxis="bp a year",
        theme=th,
    )
    chart(fig, rv, key="ratesvol")
    st.caption(
        "The MOVE index is a basket of 1-month Treasury option volatilities across maturities (2 to 30 years), "
        "so the comparison with the 10-year alone is indicative."
    )
    st.markdown(
        f"Implied rates volatility is **{ratio:.2f} times** realised volatility on the 10-year, "
        f"{ordinal(percentile_of_last(ratio_s, 10))} percentile of that ratio over 10 years."
    )
footer()
