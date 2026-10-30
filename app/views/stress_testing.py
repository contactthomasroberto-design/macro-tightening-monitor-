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
    "What the rest of the market does if one asset moves, and how past crises looked.",
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
    ["Conditional scenario", "Historical episodes"],
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
    dist = st.radio(
        "Distribution",
        ["Normal", f"Student-t (fat tails, {b['tail_dof']:.1f} degrees of freedom)"],
        horizontal=True,
        key="st_dist",
    )
    nu = None if dist == "Normal" else b["tail_dof"]
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
        cd = stt.conditional(cov, shocks, float(weeks), nu=nu)
        typical = np.sqrt(np.diag(cov.loc[cd.index, cd.index].to_numpy()) * float(weeks))
        cd["move in typical moves"] = cd["expected move"] / typical
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
        cn, ct = b["coverage"]["pooled"], b["coverage_t"]["pooled"]
        if cn:
            st.caption(
                f"Out-of-sample check ({cn['weeks']} weeks from {cn['from']}, covariance from the previous 2 years, "
                f"conditioning on the S&P 500 and the US 10Y): normal bands held {100 * cn['inside 68% band']:.0f}% "
                f"of realised moves in the 68% band and {100 * cn['inside 95% band']:.0f}% in the 95% band; Student-t "
                f"bands {100 * ct['inside 68% band']:.0f}% and {100 * ct['inside 95% band']:.0f}%. Fat tails do not fix "
                "the 95% band: the miss comes from correlations that shift, not from the shape of the distribution "
                "(research log H23). 'Move in typical moves': the expected move divided by the asset's usual move "
                f"over the same weeks. High-inflation window: {b['hi_infl_weeks']} weeks since 1990."
            )

# ================================================================== episodes
elif view == "Historical episodes":
    an = b["analogs"]
    if not an.empty:
        an = an.assign(coverage=an["assets compared"].map(lambda n: "full" if n >= 15 else "partial"))
        full = an[an["coverage"] == "full"]
        partial = an[an["coverage"] == "partial"]
        top = full.index[0] if not full.empty else an.index[0]
        note = (
            " Episodes before most series existed are compared on fewer assets and ranked apart: "
            + ", ".join(
                f"{i} ({r['similarity (correlation)']:+.2f} on {r['assets compared']} assets)"
                for i, r in partial.iterrows()
            )
            + "."
            if not partial.empty
            else ""
        )
        st.markdown(
            f"**Closest past episode to the last 13 weeks: {top}** (correlation "
            f"{an.loc[top, 'similarity (correlation)']:+.2f} over {an.loc[top, 'assets compared']} assets). Moves "
            "are scaled by each asset's typical weekly move and the episode length." + note
        )
        st.dataframe(an.style.format({"similarity (correlation)": "{:+.2f}"}), use_container_width=True)
    mv = b["episodes"].copy()
    mv.index = [label(i) for i in mv.index]
    units = pd.Series({label(i): stt.unit_of(kinds[i]) for i in kinds})
    disp = mv.apply(lambda col: [fmt_move(v, units.get(i, "")) for i, v in col.items()])
    st.markdown(
        "**Moves during each episode** (bp for yields and spreads, log % for prices, points for VIX/MOVE)"
    )
    st.dataframe(disp, use_container_width=True, height=36 * (len(disp) + 1))
    st.caption(
        "Dates: "
        + "; ".join(f"{n} {a} to {e}" for n, a, e, _ in stt.EPISODES)
        + ". Blank: the series did not exist yet."
    )

footer()
