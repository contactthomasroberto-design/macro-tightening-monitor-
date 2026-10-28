import pandas as pd
import streamlit as st

from components import CACHE_TTL, chart, footer, header, result_meta, show_status, theme
from macro import plotting as pl
from macro.data import source_label, try_series
from macro.inflation import MODEL_LABELS
from macro.pipeline import INFL_TARGET_SERIES, inflation_bundle

header(
    "Inflation", "Decomposition, persistence, energy and supply pass-through, expectations, and forecasts."
)
th = theme()
region = st.radio("Region", ["US", "EA", "JP"], horizontal=True, key="infl_region")


@st.cache_resource(ttl=CACHE_TTL, show_spinner="Running inflation models (first run only)…")
def _bundle(r: str):
    return inflation_bundle(r)


b = _bundle(region)
tgt = b["target"]
p = b["panel"]
rec = try_series({"US": "USREC", "EA": "EUROREC"}.get(region, "USREC"))
ids = [INFL_TARGET_SERIES[region]]
src = source_label(*ids)
as_of = pd.Timestamp(b["as_of"]).strftime("%Y-%m")
dec = b["decomposition"]

# ------------------------------------------------------------------ headline numbers
last = dec.dropna(subset=["headline"]).iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Headline yoy", f"{last['headline']:.1f}%", f"{last['headline'] - tgt:+.1f} pp vs target")
if "core" in dec:
    c2.metric("Core yoy", f"{last['core']:.1f}%", f"{last['core'] - tgt:+.1f} pp vs target")
    mc = b["momentum_core"].dropna().iloc[-1]
    c3.metric("Core 3m annualised", f"{mc['3m ann.']:.1f}%")
if "prob_exceed" in b:
    pe = b["prob_exceed"]
    c4.metric(
        f"P(headline > {pe['threshold']:.1f}% in 12m)",
        f"{100 * pe['p']:.0f}%",
        help="Equal-weight combination forecast with Gaussian band calibrated on past out-of-sample errors.",
    )
st.caption(
    f"Target {tgt:.1f}% ({'PCE' if region == 'US' else 'HICP' if region == 'EA' else 'CPI'} is the official target "
    f"measure{'; CPI shown here, PCE in the table view' if region == 'US' else ''}). Data as of {as_of}."
)

# ------------------------------------------------------------------ decomposition
gap_txt = "above" if last["headline"] > tgt else "below"
fig = pl.small_multiples(
    dec[[c for c in ["headline", "core", "energy", "food", "services", "goods"] if c in dec]].loc["2000":],
    f"Headline inflation is {abs(last['headline'] - tgt):.1f} pp {gap_txt} target; components yoy %",
    src,
    as_of,
    ncols=3,
    hline=tgt,
    rec=rec,
    theme=th,
    yaxis="% yoy",
)
chart(fig, dec, key=f"dec_{region}")

if "momentum_core" in b:
    mom = b["momentum_core"].loc["2010":]
    direction = "accelerating" if mom["3m ann."].iloc[-1] > mom["yoy"].iloc[-1] else "decelerating"
    fig = pl.line_chart(
        mom[["3m ann.", "6m ann.", "yoy"]],
        f"Core momentum is {direction}: 3m annualised vs yoy",
        src,
        as_of,
        yaxis="%",
        hline=tgt,
        rec=rec,
        theme=th,
    )
    chart(fig, mom, key=f"mom_{region}")

if "underlying" in b:
    u = b["underlying"].loc["2000":]
    fig = pl.line_chart(
        u,
        "Underlying inflation measures (yoy %)",
        "SYNTHETIC"
        if "SYNTH" in src
        else "FRED (Cleveland Fed median and trimmed-mean CPI, Atlanta Fed sticky CPI, BLS)",
        as_of,
        yaxis="% yoy",
        hline=tgt,
        rec=rec,
        theme=th,
    )
    chart(fig, u, key="underlying")

if "broadening" in b:
    br = b["broadening"]
    s = 100 * br.value.loc["2000":]
    fig = pl.line_chart(
        s.to_frame("share above target"),
        f"{s.iloc[-1]:.0f}% of components run above target (6m annualised)",
        src,
        as_of,
        yaxis="% of components",
        rec=rec,
        theme=th,
    )
    chart(fig, s, key=f"broad_{region}")
    result_meta(br)

# ------------------------------------------------------------------ persistence
if "persistence" in b:
    st.subheader("Persistence")
    pr = b["persistence"]
    roll = pr.extra["rolling"]
    st.markdown(
        f"Core m/m annualised follows an **AR({pr.extra['p']})** with sum of coefficients "
        f"**ρ = {pr.value:.2f}** (90% CI {pr.lower:.2f} to {pr.upper:.2f}); impulse-response half-life "
        f"**{pr.extra['half_life_months']:.0f} month(s)**."
    )
    fig = pl.band_chart(
        roll["rho"],
        roll["lower"],
        roll["upper"],
        f"Rolling {pr.extra['window'] // 12}-year persistence of core inflation",
        src,
        as_of,
        name="ρ (sum of AR coefficients)",
        band_name="90% band",
        theme=th,
    )
    chart(fig, roll, key=f"pers_{region}")
    result_meta(pr)

# ------------------------------------------------------------------ energy pass-through
if "energy_passthrough" in b:
    st.subheader("Energy pass-through")
    ep = b["energy_passthrough"]
    tab = ep.extra["table"]
    st.markdown(
        f"A 10% rise in local-currency oil raises headline-minus-core inflation by "
        f"**{10 * ep.value:.2f} pp** cumulatively over {ep.extra['lags'] + 1} months "
        f"(95% CI {10 * ep.lower:.2f} to {10 * ep.upper:.2f})."
    )
    st.dataframe(tab.round(4), use_container_width=True)
    stable = (
        tab["lower"].iloc[1:].max() <= tab["upper"].iloc[1:].min() if tab["lower"].notna().all() else None
    )
    if stable is not None:
        show_status(
            "good" if stable else "warning",
            "pre- and post-2020 confidence intervals overlap"
            if stable
            else "pass-through differs across samples",
        )
    curves = ep.extra["curves"]
    fig = pl.line_chart(
        pd.DataFrame({k: v["cum"] for k, v in curves.items()}),
        "Cumulative pass-through by lag (pp per 1% oil change)",
        src + "; Brent (EIA via FRED)",
        as_of,
        yaxis="pp",
        theme=th,
    )
    chart(fig, pd.concat(curves, axis=1), key=f"ep_{region}")
    result_meta(ep)

if "supply" in b and b["supply"].value:
    st.subheader("Supply-chain pressure (GSCPI) → prices")
    sp = b["supply"]
    cols = st.columns(len(sp.value))
    for (name, lp), col in zip(sp.value.items(), cols, strict=True):
        with col:
            f = pl.band_chart(
                lp["beta"],
                lp["lower"],
                lp["upper"],
                f"{'Producer prices' if name == 'ppi' else 'Core goods'}: +{lp['beta'].iloc[-1]:.2f}% after 12m",
                source_label("GSCPI") + "; " + src,
                as_of,
                name="response",
                band_name="90% band",
                theme=th,
            )
            f.update_xaxes(title_text="months after shock")
            chart(f, lp, key=f"lp_{name}_{region}")
    result_meta(sp)

# ------------------------------------------------------------------ expectations
if "expectations" in b and b["expectations"].value is not None:
    st.subheader("Expectations anchoring (CIE-style common factor)")
    ef = b["expectations"]
    F = ef.value.to_frame("common factor (this project)")
    if b.get("cie_published") is not None:
        F["Fed Board CIE (published)"] = b["cie_published"].resample("MS").ffill()
    fig = pl.line_chart(
        F,
        f"Common inflation-expectations factor: {ef.value.iloc[-1]:.2f}%",
        source_label(*ef.extra["measures"]),
        as_of,
        yaxis="%",
        hline=tgt,
        theme=th,
    )
    chart(fig, F, key="cie")
    rb = ef.extra["rolling_beta"]
    fig = pl.band_chart(
        rb["beta"],
        rb["lower"],
        rb["upper"],
        f"Sensitivity of the factor to realised inflation ({ef.extra['window']}m rolling)",
        source_label(*ef.extra["measures"]),
        as_of,
        name="β",
        band_name="90% band",
        hline=0,
        theme=th,
    )
    chart(fig, rb, key="cie_beta")
    if ef.extra["deanchoring_flag"]:
        show_status(
            "serious",
            "De-anchoring flag: sensitivity significantly positive and above its pre-2020 95th percentile.",
        )
    else:
        show_status(
            "good", f"No de-anchoring flag (pre-2020 95th percentile of β: {ef.extra['pre_p95']:.3f})."
        )
    st.caption(
        f"Loadings: {', '.join(f'{k} {v:.2f}' for k, v in ef.extra['loadings'].items())} · "
        f"first factor explains {100 * ef.extra['explained_share']:.0f}% of the variance."
    )
    result_meta(ef)

# ------------------------------------------------------------------ forecasts
if "oos" in b:
    st.subheader("Forecasts and out-of-sample evaluation")
    oos, fc = b["oos"], b["forecasts"]
    comb = fc[fc["model"] == "COMB"].set_index("target_date")
    hist = dec["headline"].loc["2018":]
    q = pd.DataFrame(
        {
            0.05: comb["point"] - 1.645 * comb["sigma"],
            0.16: comb["point"] - comb["sigma"],
            0.84: comb["point"] + comb["sigma"],
            0.95: comb["point"] + 1.645 * comb["sigma"],
            0.5: comb["point"],
        }
    )
    fig = pl.fan_chart(
        hist,
        q,
        f"Headline inflation path: {comb['point'].iloc[-1]:.1f}% in 12 months (central)",
        src,
        as_of,
        conditioning="no policy conditioning; oil flat after the month-to-date reading; "
        "symmetric Gaussian bands (68%, 90%) from past out-of-sample errors",
        base_color=pl.ENTITY_BY_REGION[region],
        yaxis="% yoy",
        theme=th,
    )
    chart(fig, comb, key=f"fc_{region}")
    st.caption(
        "How to read: the bands show the range implied by past forecast errors, not the full range of outcomes. "
        "The BoE-style skewed fan (scenario-weighted) is on the Scenarios page."
    )

    h = st.select_slider("Horizon (months)", options=list(oos["scores"].keys()), value=12, key=f"h_{region}")
    tab = oos["scores"][h].rename(index=MODEL_LABELS)
    st.dataframe(tab.round(3), use_container_width=True)
    best = tab["rmse"].idxmin()
    rw = tab.loc["Random walk", "rmse"]
    combo = tab.loc["Equal-weight combination"]
    beats = combo["rmse"] < rw and combo.get("dm_pvalue", 1) < 0.10
    show_status(
        "good" if beats else "warning",
        f"h={h}: combination RMSE {combo['rmse']:.2f} vs random walk {rw:.2f} "
        f"({'significantly better (DM p<0.10)' if beats else 'not significantly better than the random walk'}); "
        f"lowest RMSE: {best}.",
    )
    if "SPF consensus" in tab.index:
        spf_r = tab.loc["SPF consensus", "rmse"]
        st.caption(
            f"SPF benchmark at h=12 (4-quarter-ahead mean CPI forecast mapped to the 12-month-ahead yoy rate, "
            f"an approximation): RMSE {spf_r:.2f}."
        )
    model = st.selectbox(
        "PIT histogram for model",
        [m for m in tab.index if m != "SPF consensus"],
        index=list(tab.index).index("Equal-weight combination"),
        key=f"pit_{region}",
    )
    inv = {v: k for k, v in MODEL_LABELS.items()}
    sub = oos["forecasts"][(oos["forecasts"]["h"] == h) & (oos["forecasts"]["model"] == inv[model])].dropna(
        subset=["actual", "sigma"]
    )
    from scipy import stats

    pit = stats.norm.cdf((sub["actual"] - sub["point"]) / sub["sigma"])
    fig = pl.histogram(
        pit,
        f"PIT of {model} at h={h} (flat = calibrated)",
        src,
        as_of,
        bins=10,
        theme=th,
        expected=len(pit) / 10,
    )
    chart(fig, pd.Series(pit, index=sub["origin"].to_numpy(), name="pit"), key=f"pit_{region}_{h}")
    st.caption(
        f"Pseudo out-of-sample, expanding window from {oos['start'][:7]}, {oos['n_origins']} origins, "
        f"{b['vintage_label']} (release lags respected, revisions not). Specifications tried: 6 candidate models; "
        "AR lag order by BIC among 1-6; elastic-net penalty by time-series CV (3 l1-ratios x 30 penalties). "
        "Overlapping multi-step errors make PIT and DM p-values indicative only."
    )

with st.expander("Limitations"):
    st.markdown(
        "- Latest-vintage data: real-time revisions are not replicated unless ALFRED vintages are loaded.\n"
        "- The mixed-frequency model is a simplified Knotek-Zaman recipe: only oil enters at daily frequency, "
        "and oil is held flat beyond the current month (no futures curve in free data).\n"
        "- Energy pass-through is a reduced-form distributed lag, not a structural estimate.\n"
        "- The expectations factor is a static principal component, not the Fed Board's dynamic CIE.\n"
        "- Japan: headline CPI only (component data not in the catalogue)."
    )
footer(research_series=True)
