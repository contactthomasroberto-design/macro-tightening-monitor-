import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import CACHE_TTL, footer, header, sidebar_controls, theme
from macro import plotting as pl
from macro import scenarios as scn
from macro.pipeline import scenario_bundle, scenario_results

header(
    "Scenario simulator",
    "Set your own shocks and run them through the quarterly engine: policy rate, inflation, unemployment and the 10-year.",
)
ctl = sidebar_controls()
th = theme()
N_PATHS = 5000


@st.cache_resource(ttl=CACHE_TTL, show_spinner="Loading the scenario engine…")
def _bundle():
    return scenario_bundle()


sb = _bundle()
init, params, fut = sb["init"], sb["params"], sb["future"]
Q = len(fut)


def ramp(peak: float, peak_q: int, fade: bool) -> list[float]:
    """Linear rise to `peak` at quarter `peak_q`, then flat or back to zero by the end."""
    up = [peak * (t + 1) / peak_q for t in range(peak_q)]
    rest = Q - peak_q
    down = [peak * (1 - (k + 1) / rest) for k in range(rest)] if fade and rest else [peak] * rest
    return [round(x, 4) for x in up + down]


st.caption(
    f"Starting point (latest data): core PCE inflation {init['pi']:.2f}%, unemployment {init['u']:.2f}%, "
    f"policy rate {init['i']:.2f}%, 10-year term premium {init['tp']:.2f}%. Engine estimated on "
    f"{params.n_obs} quarters; {N_PATHS:,} paths with the engine's own residual shocks."
)

c1, c2 = st.columns(2)
with c1:
    st.markdown("**Shocks**")
    oil = st.slider("Oil price, peak change (%)", -50, 100, 0, 5, key="sim_oil")
    oil_q = st.slider("Quarter of the oil peak", 1, Q, 2, key="sim_oilq")
    oil_fade = st.toggle("Oil shock fades by the end of the horizon", True, key="sim_oilfade")
    du = st.slider("Unemployment, change by the end (pp)", -1.0, 3.0, 0.0, 0.1, key="sim_u")
with c2:
    st.markdown("&nbsp;")
    imp = st.slider(
        "Extra non-energy inflation, first year (pp, annualised)", -1.0, 1.5, 0.0, 0.1, key="sim_inf"
    )
    tp = st.slider("10-year term premium, change by quarter 4 (bp)", -100, 150, 0, 5, key="sim_tp")
    seed = st.number_input("Random seed", 0, 9999, 7, key="sim_seed", help="Same seed, same paths")

custom = {
    "oil_shock_pct": ramp(float(oil), oil_q, oil_fade),
    "unemp_change_pp": ramp(du, Q, False),
    "infl_shock_pp": [imp] * min(4, Q) + [0.0] * max(0, Q - 4),
    "tp_change_bp": ramp(float(tp), min(4, Q), False),
}


@st.cache_data(ttl=CACHE_TTL, show_spinner="Simulating…")
def _simulate(key: str, seed: int) -> dict:
    sim = scn.simulate(params, init, custom, N_PATHS, Q, seed=seed)
    det = scn.simulate(params, init, custom, 1, Q, shocks=False)
    return {"mc": sim, "det": det}


res = _simulate(str(custom), int(seed))
mc = res["mc"]
w = np.full(N_PATHS, 1.0 / N_PATHS)
base = scenario_results(sb, sb["base_weights"])

qs = [0.05, 0.16, 0.5, 0.84, 0.95]
q = {
    v: pd.DataFrame(scn.weighted_quantile(mc[v], w, qs).T, index=fut, columns=qs)
    for v in ("i", "pi", "u", "y10")
}
mv = scn.moves_probabilities(mc["i"], w, init["i"])
rec = scn.recession_probability(mc["u"], w, init["u"])

# ------------------------------------------------------------------ headline
st.subheader("Your scenario against the base mix")
k = st.columns(5)
k[0].metric(
    "Policy rate in 4 quarters (median)",
    f"{q['i'].iloc[3][0.5]:.2f}%",
    f"{q['i'].iloc[3][0.5] - base['q_i'].iloc[3][0.5]:+.2f} vs base",
    delta_color="off",
)
k[1].metric(
    "Core PCE in 4 quarters",
    f"{q['pi'].iloc[3][0.5]:.2f}%",
    f"{q['pi'].iloc[3][0.5] - base['q_pi'].iloc[3][0.5]:+.2f} vs base",
    delta_color="off",
)
k[2].metric(
    "Unemployment in 8 quarters",
    f"{q['u'].iloc[-1][0.5]:.2f}%",
    f"{q['u'].iloc[-1][0.5] - base['q_u'].iloc[-1][0.5]:+.2f} vs base",
    delta_color="off",
)
k[3].metric(
    "P(at least one hike, 4 quarters)",
    f"{100 * mv.loc[1, 'P(at least k hikes)']:.0f}%",
    f"{100 * (mv.loc[1, 'P(at least k hikes)'] - base['moves'].loc[1, 'P(at least k hikes)']):+.0f} pts",
    delta_color="off",
)
k[4].metric(
    "P(recession signal, 8 quarters)",
    f"{100 * rec:.0f}%",
    f"{100 * (rec - base['recession_prob']):+.0f} pts",
    delta_color="off",
)
st.caption(
    "Base: the probability-weighted mix of the four configured scenarios (Scenarios page), which include "
    "disinflation and hard-landing shocks; with every slider at zero your scenario carries no shock beyond the "
    "engine's own, so it differs from the base. Recession signal: a Sahm-type rise of 0.5 pp in the two-quarter "
    "average unemployment rate on the simulated paths; it reacts to the engine's unemployment noise and reads "
    "higher than the dedicated recession models (Growth and recession, Recession signals)."
)

# ------------------------------------------------------------------ fans
var = st.segmented_control(
    "Variable",
    ["Policy rate", "Core PCE inflation", "Unemployment", "10-year yield"],
    default="Policy rate",
    key="sim_var",
)
code = {"Policy rate": "i", "Core PCE inflation": "pi", "Unemployment": "u", "10-year yield": "y10"}[
    var or "Policy rate"
]
base_q = {"i": base["q_i"], "pi": base["q_pi"], "u": base["q_u"], "y10": base["q_y10"]}[code]
qq = q[code]
fig = go.Figure()
navy = "31,58,95"
fig.add_trace(
    go.Scatter(
        x=list(fut) + list(fut[::-1]),
        y=list(qq[0.95]) + list(qq[0.05][::-1]),
        fill="toself",
        fillcolor=f"rgba({navy},0.12)",
        line={"width": 0},
        name="your scenario, 90%",
    )
)
fig.add_trace(
    go.Scatter(
        x=list(fut) + list(fut[::-1]),
        y=list(qq[0.84]) + list(qq[0.16][::-1]),
        fill="toself",
        fillcolor=f"rgba({navy},0.25)",
        line={"width": 0},
        name="your scenario, 68%",
    )
)
fig.add_trace(
    go.Scatter(x=fut, y=qq[0.5], name="your scenario, median", line={"color": f"rgb({navy})", "width": 2.5})
)
fig.add_trace(
    go.Scatter(
        x=fut,
        y=base_q[0.5],
        name="base mix, median",
        line={"color": pl.THEMES[th]["muted"], "width": 2, "dash": "dash"},
    )
)
pl.base_layout(
    fig,
    f"{var}: median {qq[0.5].iloc[-1]:.2f}% after 8 quarters (base {base_q[0.5].iloc[-1]:.2f}%)",
    "Macro Tightening Monitor quarterly engine; your shocks",
    f"{fut[0]:%Y-%m-%d}",
    th,
    height=380,
)
fig.update_yaxes(title_text="%")
st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

with st.expander("Shock paths and quarterly table"):
    paths = pd.DataFrame(custom, index=fut)
    paths.columns = ["Oil (% vs today)", "Unemployment (pp)", "Extra inflation (pp)", "Term premium (bp)"]
    st.dataframe(paths, use_container_width=True)
    tab = pd.DataFrame(
        {
            f"{n} (median)": q[c][0.5]
            for n, c in (("Policy rate", "i"), ("Core PCE", "pi"), ("Unemployment", "u"), ("10-year", "y10"))
        }
    )
    st.dataframe(tab.style.format("{:.2f}"), use_container_width=True)
    st.dataframe(mv.style.format("{:.0%}"), use_container_width=True)
st.caption(
    "The engine: a Phillips curve with oil pass-through, an inertial policy rule estimated on Fed data with a "
    "quarter-point grid, and a 10-year yield equal to the expected average short rate plus the term premium. "
    "It is a small semi-structural model, not FRB/US; see the Scenarios model card."
)
footer()
