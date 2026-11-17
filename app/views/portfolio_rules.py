import pandas as pd
import streamlit as st

from components import footer, header, sidebar_controls
from portfolio_ui import DISCLAIMER, bundle

header(
    "Rules", "Every rule of the portfolio, fixed before the backtest. Changing one is a new model version."
)
ctl = sidebar_controls()
b = bundle()
cfg = b["config"]
m = cfg["model"]

st.markdown(
    f"""
- **Benchmark**: 60% MSCI ACWI, 40% US aggregate bonds, in US dollars.
- **Universe**: {len(cfg["universe"])} lines: equity regions, Treasuries by maturity, inflation-linked bonds,
  investment-grade credit, gold, commodities, cash, and six semiconductor names (SK Hynix, Samsung Electronics,
  Micron, TSMC, NVIDIA, ASML).
- **Risk model**: Ledoit-Wolf shrinkage on {m["cov_window_weeks"]} weeks of weekly USD returns.
- **Expected returns**: Black-Litterman, δ = {m["risk_aversion"]}, τ = {m["tau"]}, a full view worth
  {m["view_scale"]} Sharpe units; confidence trend {m["confidence"]["trend"]:.0%}, macro {m["confidence"]["macro"]:.0%},
  micro {m["confidence"]["micro"]:.0%}, news {m["confidence"]["news"]:.0%}.
- **Constraints**: long only; ex-ante volatility ≤ benchmark's; tracking error ≤ {m["tracking_error_max"]:.0%};
  total equity within ±{cfg["sleeves"]["equity_total_band"]:.0%} of 60%; semiconductors
  {cfg["sleeves"]["semis"]["min"]:.0%}-{cfg["sleeves"]["semis"]["max"]:.0%}, 5% per name; cash ≤
  {cfg["sleeves"]["cash_max"]:.0%} unless the drawdown overlay is on.
- **Drawdown overlay**: """
    + "; ".join(
        f"beyond {lv['drawdown']:.0%} drawdown the risk cap falls to {lv['scale']:.0%}"
        for lv in m["drawdown_overlay"]["levels"]
    )
    + f"""; released below half the threshold.
- **Trading**: monthly (first refresh of the month) or when the overlay changes; trades under
  {m["no_trade_band"]:.1%} skipped; costs per line (Korean shares 25 bp, transaction tax included).
- **Safeguards**: a price older than {cfg["live"]["stale_days"]} business days freezes the rebalance; kill switch
  `trading_enabled` (now **{"on" if cfg["live"]["trading_enabled"] else "OFF"}**); hourly check in market hours with a GitHub
  issue when the drawdown passes {cfg["live"]["alerts"]["drawdown"]:.0%} or the day's loss {cfg["live"]["alerts"]["daily_loss"]:.0%}.
- **Record**: every paper rebalance is appended to `archive/portfolio_book.csv` and never edited; the paper NAV is
  recomputed from it.
"""
)
st.subheader("Universe")
u = pd.DataFrame(cfg["universe"]).T[["name", "sleeve", "max", "cost_bp"]]
u["min"] = pd.DataFrame(cfg["universe"]).T.get("min")
st.dataframe(u, use_container_width=True)
st.caption(f"Model version {b['version']}. " + DISCLAIMER)
footer()
