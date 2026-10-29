import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components import chart, footer, header, sidebar_controls, theme
from macro import plotting as pl
from macro.data import source_label
from macro.pipeline import MARKET_BETAS
from markets_ui import NAVY, bundle

header(
    "FX and commodities",
    "How much of the recent moves in currencies, gold and inflation compensation rates and oil explain.",
)
ctl = sidebar_controls()
th = theme()
b = bundle()
betas = {k: r for k, r in b["betas"].items() if r.value is not None}
if not betas:
    st.warning("Not enough data for the sensitivities.")
    footer()
    st.stop()

ids = sorted({i for _, y, _, (xa, xb), _ in MARKET_BETAS for i in (y, xa, xb) if i})
src = source_label(*ids)

# ------------------------------------------------------------------ table
st.subheader("Sensitivities and the last quarter")
rows = []
for k, r in betas.items():
    e = r.extra
    uy, ux = e["unit_y"], e["unit_x"]
    rows.append(
        {
            "relation": k,
            "beta": f"{r.value:+.3f} {uy} per {ux}",
            "95% interval": f"[{r.lower:+.3f}, {r.upper:+.3f}]",
            "R² (2y, weekly)": e["r2"],
            "13-week move": f"{e['actual']:+.2f} {uy}",
            "driver's move": f"{e['x_move']:+.1f} {ux}",
            "explained": f"{e['explained']:+.2f} {uy}",
            "unexplained": f"{e['residual']:+.2f} {uy}",
        }
    )
tab = pd.DataFrame(rows).set_index("relation")
st.dataframe(tab.style.format({"R² (2y, weekly)": "{:.2f}"}), use_container_width=True)
st.caption(
    "OLS of weekly (Friday-to-Friday) changes over the last 104 weeks, Newey-West standard errors (4 lags). "
    "Weekly rather than daily changes because Tokyo, Frankfurt and New York close at different hours. "
    "'Explained' = beta × the driver's move over the same 13 weeks. Changes, not levels: regressions of one "
    "trending level on another are spurious. A low R² means the asset is not trading on that driver at the "
    "moment, which is itself the finding. " + src
)

# ------------------------------------------------------------------ decomposition chart
k_sorted = list(betas)
fig = go.Figure()
fig.add_trace(
    go.Bar(
        y=k_sorted,
        x=[betas[k].extra["explained"] for k in k_sorted],
        name="explained by the driver",
        orientation="h",
        marker_color=f"rgb{NAVY}",
    )
)
fig.add_trace(
    go.Bar(
        y=k_sorted,
        x=[betas[k].extra["residual"] for k in k_sorted],
        name="unexplained",
        orientation="h",
        marker_color=pl.THEMES[th]["muted"],
    )
)
fig.update_layout(barmode="relative")
worst = max(betas, key=lambda k: abs(betas[k].extra["residual"]))
pl.base_layout(
    fig,
    f"Largest gap between move and driver: {worst.split(' vs ')[0]} ({betas[worst].extra['residual']:+.2f} "
    f"{betas[worst].extra['unit_y']} unexplained over 13 weeks)",
    src,
    max(r.as_of for r in betas.values()),
    th,
    height=420,
)
fig.update_xaxes(title_text="13-week move, in the unit of each asset (% for prices, bp for yields)")
st.plotly_chart(fig, use_container_width=True, config={"displaylogo": False})

# ------------------------------------------------------------------ rolling fit
st.subheader("When do these assets trade on their driver?")
r2 = pd.concat(
    {
        k.split(" vs ")[0] + " / " + k.split(" vs ")[1].split(" (")[0]: r.extra["rolling_r2"]
        for k, r in betas.items()
    },
    axis=1,
)
fig = pl.line_chart(
    r2,
    "Share of weekly moves explained by the driver, rolling 2 years",
    src,
    max(r.as_of for r in betas.values()),
    yaxis="R²",
    theme=th,
)
chart(fig, r2, key="fx_r2")
beta_df = pd.concat({k: r.extra["rolling_beta"] for k, r in betas.items()}, axis=1)
with st.expander("Rolling betas"):
    for k in beta_df:
        fig = pl.line_chart(
            beta_df[[k]],
            k,
            src,
            betas[k].as_of,
            yaxis=f"{betas[k].extra['unit_y']} per {betas[k].extra['unit_x']}",
            theme=th,
            hline=0,
            height=300,
        )
        chart(fig, beta_df[[k]], key=f"beta_{k[:20]}")
footer()
