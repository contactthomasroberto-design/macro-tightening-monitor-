import streamlit as st

from components import footer, header, sidebar_controls
from macro.data import source_label
from markets_ui import bundle

header(
    "Carry and roll-down",
    "What the curve and rate differentials pay over three months if nothing moves, and per unit of risk.",
)
ctl = sidebar_controls()
b = bundle()

st.subheader("US Treasuries: 3-month carry and roll-down")
cr = b.get("carry_rates")
if cr is not None and not cr.empty:
    st.dataframe(
        cr.style.format(
            {
                "yield (%)": "{:.2f}",
                "carry (bp)": "{:+.1f}",
                "roll-down (bp)": "{:+.1f}",
                "breakeven (bp)": "{:+.1f}",
                "3-month vol (bp)": "{:.0f}",
                "breakeven / vol": "{:.2f}",
            }
        ),
        use_container_width=True,
    )
    best = cr["breakeven / vol"].idxmax()
    st.markdown(
        f"The best cushion per unit of risk is on the **{best:g}-year**: its yield can rise "
        f"{cr.loc[best, 'breakeven (bp)']:.0f} bp over three months before a holder loses, "
        f"{cr.loc[best, 'breakeven / vol']:.2f} times the realised 3-month volatility."
    )
    st.caption(
        "Carry: yield over the 3-month bill for a quarter, divided by duration (in bp of yield). Roll-down: the fall "
        "in yield from ageing three months along today's curve (linear interpolation). Breakeven = carry + roll-down. "
        "Vol: realised 63-day volatility of daily yield changes, scaled to three months. Assumes an unchanged curve; "
        "it is what the curve pays, not a forecast. "
        + source_label("DGS3MO", "DGS1", "DGS2", "DGS5", "DGS10", "DGS30")
    )

st.subheader("Currencies: 3-month interest carry")
cf = b.get("carry_fx")
if cf is not None and not cf.empty:
    st.dataframe(
        cf.drop(columns="sign").style.format(
            {
                "rate held (%)": "{:.2f}",
                "rate funded (%)": "{:.2f}",
                "3-month carry (%)": "{:+.2f}",
                "3-month vol (%)": "{:.2f}",
                "carry / vol": "{:+.2f}",
            }
        ),
        use_container_width=True,
    )
    st.caption(
        "Carry: the overnight rate of the currency held minus that of the funding currency, for a quarter (€STR, SOFR, "
        "Japan call rate). Vol: realised 63-day volatility of the exchange rate. Covered interest parity makes the "
        "forward price embed this carry; it is earned only if the spot rate does not move against the holder. "
        + source_label("SOFR", "EA_ESTR", "JP_CALL_D")
    )
footer()
