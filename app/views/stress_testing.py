import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import CACHE_TTL, footer, header, sidebar_controls, theme
from macro import plotting as pl
from macro import stress_test as stt
from macro.pipeline import stress_bundle
from markets_ui import NAVY, RED, fmt_move

header(
    "Stress testing",
    "What the rest of the market does if one asset moves, how past crises looked, and the common factors.",
)
ctl = sidebar_controls()
th = theme()


@st.cache_resource(ttl=CACHE_TTL, show_spinner="Estimating covariances and backtests…")
def _bundle():
    return stress_bundle()


b = _bundle()
names, kinds = b["names"], b["kinds"]
label = lambda i: names.get(i, i)  # noqa: E731
view = st.segmented_control(
    "View",
    ["Conditional scenario", "Historical episodes", "Market factors"],
    default="Conditional scenario",
    key="stress_view",
)

# ================================================================== conditional scenario
if view in (None, "Conditional scenario"):
    PRESETS = {
        "Rates shock: US 10Y +50 bp": {"DGS10": 50.0},
        "Oil shock: Brent +25%": {"BRENT_FUT": 25.0},
        "Equity drawdown: S&P 500 −10%": {"SPX": -10.0},
        "Dollar surge: broad dollar +4%": {"DTWEXBGS": 4.0},
        "Stagflation: Brent +20%, US 10Y +40 bp": {"BRENT_FUT": 20.0, "DGS10": 40.0},
        "Risk-off: S&P 500 −8%, VIX +10": {"SPX": -8.0, "VIX": 10.0},
        "Custom": {},
    }
    c1, c2, c3 = st.columns([2, 1, 2])
    preset = c1.selectbox("Scenario", list(PRESETS), key="st_preset")
    weeks = c2.number_input("Over (weeks)", 1, 26, 4, key="st_weeks")
    window = c3.selectbox("Correlations estimated on", list(b["covariances"]), key="st_window")
    cov = b["covariances"][window]
    shocks = dict(PRESETS[preset])
    if preset == "Custom":
        ids = [i for i in cov.index]
        picks = st.multiselect(
            "Shocked assets", ids, default=["DGS10"], format_func=label, key="st_custom_ids"
        )
        for i in picks:
            shocks[i] = st.number_input(f"{label(i)} ({stt.unit_of(kinds[i])})", value=0.0, key=f"st_val_{i}")
    shocks = {k: v for k, v in shocks.items() if k in cov.index}
    if not shocks:
        st.info("Choose at least one shocked asset.")
    else:
        cd = stt.conditional(cov, shocks, float(weeks))
        cd.index = [label(i) for i in cd.index]
        units = {label(i): stt.unit_of(kinds[i]) for i in cov.index}
        order = cd["expected move"].abs().div(cd["68% high"] - cd["expected move"]).sort_values().index
        cd = cd.loc[order]
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                y=cd.index,
                x=cd["expected move"],
                orientation="h",
                marker_color=f"rgb{NAVY}",
                name="expected move",
                error_x={
                    "type": "data",
                    "symmetric": False,
                    "array": cd["68% high"] - cd["expected move"],
                    "arrayminus": cd["expected move"] - cd["68% low"],
                    "color": f"rgb{RED}",
                },
            )
        )
        fig.add_vline(x=0, line_width=1, line_color=pl.THEMES[th]["muted"])
        shock_txt = ", ".join(f"{label(k)} {fmt_move(v, stt.unit_of(kinds[k]))}" for k, v in shocks.items())
        pl.base_layout(
            fig,
            f"If {shock_txt} over {weeks} week{'s' if weeks > 1 else ''}: expected moves and 68% ranges",
            f"Macro Tightening Monitor; weekly changes, covariance: {window.lower()}",
            f"{b['as_of']:%Y-%m-%d}",
            th,
            height=60 + 26 * len(cd) + 120,
        )
        fig.update_xaxes(
            title_text="move in each asset's unit (bp for yields and spreads, % for prices, points for VIX/MOVE)"
        )
        st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
        show = cd.copy()
        show.insert(0, "unit", [units[i] for i in show.index])
        with st.expander("Table"):
            st.dataframe(
                show.style.format(
                    {c: "{:+.2f}" for c in show.columns if c != "unit"}
                    | {"share of risk explained": "{:.0%}"}
                ),
                use_container_width=True,
            )
        cov_pool = b["coverage"]["pooled"]
        if cov_pool:
            st.caption(
                f"Out-of-sample check ({cov_pool['weeks']} weeks from {cov_pool['from']}, covariance from the previous "
                f"2 years, conditioning on the S&P 500 and the US 10Y): {100 * cov_pool['inside ±1 s.d.']:.0f}% of "
                f"realised moves fell inside the ±1 s.d. range (68% expected) and {100 * cov_pool['inside ±1.96 s.d.']:.0f}% "
                "inside ±1.96 s.d. (95% expected). Assumes normal, independent weekly changes; real tails are fatter. "
                f"High-inflation window: {b['hi_infl_weeks']} weeks since 1990."
            )

# ================================================================== episodes
elif view == "Historical episodes":
    an = b["analogs"]
    if not an.empty:
        top = an.index[0]
        st.markdown(
            f"**Closest past episode to the last 13 weeks: {top}** (correlation {an.iloc[0, 1]:+.2f} over "
            f"{an.iloc[0, 2]} assets). Moves are scaled by each asset's typical weekly move and the episode length."
        )
        st.dataframe(an.style.format({"similarity (correlation)": "{:+.2f}"}), use_container_width=True)
    mv = b["episodes"].copy()
    mv.index = [label(i) for i in mv.index]
    units = pd.Series({label(i): stt.unit_of(kinds[i]) for i in kinds})
    disp = mv.apply(lambda col: [fmt_move(v, units.get(i, "")) for i, v in col.items()])
    st.markdown(
        "**Moves during each episode** (bp for yields and spreads, % for prices, points for VIX/MOVE)"
    )
    st.dataframe(disp, use_container_width=True, height=36 * (len(disp) + 1))
    st.caption(
        "Dates: "
        + "; ".join(f"{n} {a} to {e}" for n, a, e, _ in stt.EPISODES)
        + ". Blank: the series did not exist yet."
    )

# ================================================================== factors
else:
    f = b["factors"]
    ex = f["explained"]
    st.markdown(
        f"Principal components of standardised weekly changes in {len(f['assets'])} assets over {f['weeks']} weeks "
        f"(from {f['from']:%b %Y}). The first two factors explain {100 * ex.iloc[:2].sum():.0f}% of the variance."
    )
    load = f["loadings"].copy()
    load.index = [label(i) for i in load.index]
    tops = {
        c: ", ".join(f"{i} {v:+.2f}" for i, v in load[c].abs().sort_values(ascending=False).head(4).items())
        for c in load
    }
    summary = pd.DataFrame(
        {
            "share of variance": ex,
            "half-sample stability (|cos|)": f["stability"],
            "largest loadings (absolute)": pd.Series(tops),
        }
    )
    st.dataframe(
        summary.style.format({"share of variance": "{:.0%}", "half-sample stability (|cos|)": "{:.2f}"}),
        use_container_width=True,
    )
    st.caption(
        f"Pre-registered expectation (research log H19): factor 1 would be risk-on/risk-off and stable. It is not: "
        "factor 1 is a global rates-level factor and risk appetite is factor 2; with close shares of variance the two "
        f"rotate between half-samples. The plane they span is stable (post hoc check: {f['plane_stability']:.2f}, 1 = identical)."
    )
    fig = go.Figure(
        go.Heatmap(
            z=load.to_numpy(),
            x=list(load.columns),
            y=list(load.index),
            zmid=0,
            colorscale=[[0, f"rgb{RED}"], [0.5, "white"], [1, f"rgb{NAVY}"]],
            text=np.round(load.to_numpy(), 2),
            texttemplate="%{text}",
        )
    )
    pl.base_layout(
        fig,
        "Factor loadings",
        "Macro Tightening Monitor; weekly changes, standardised",
        None,
        th,
        height=60 + 24 * len(load) + 120,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})
    sc = f["scores_13w"]
    figs = pl.line_chart(
        sc,
        "Factor scores, cumulated over 13 weeks",
        "Macro Tightening Monitor",
        f"{sc.index[-1]:%Y-%m-%d}",
        yaxis="standardised units",
        theme=th,
        hline=0,
    )
    st.plotly_chart(figs, use_container_width=True, config={"displaylogo": False})
footer()
