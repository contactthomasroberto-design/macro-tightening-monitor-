import pandas as pd
import streamlit as st

from components import footer, header, sidebar_controls
from portfolio_ui import DISCLAIMER, SLEEVE_LABEL, bundle

header("Rules", "Every rule of the fund, fixed before the backtest. Changing one is a new model version.")
ctl = sidebar_controls()
b = bundle()
cfg = b["config"]
m, sl, th = cfg["model"], cfg["sleeves"], cfg["model"].get("tail_hedge", {})
conf = m["confidence"] | {"news": b.get("news_confidence", 0.0)}

st.markdown(
    f"""
- **Mandate**: multi-asset alternative fund, long and short, with a drawdown no larger than the 60/40 benchmark's
  (60% MSCI ACWI, 40% US aggregate bonds, in US dollars). Model fund on paper: no order is placed.
- **Universe**: {len(cfg["universe"])} instruments: equity regions (US, Europe, Japan, China, India, Taiwan, Korea,
  Brazil, EM), US styles and sectors, six semiconductor names, Treasuries by maturity, inflation-linked and
  international government bonds, investment grade, high yield, EM debt in dollars and local currency, gold,
  silver, oil, copper, commodities, REITs, infrastructure, managed futures, a tail-risk fund and four currencies.
  The optimiser chooses which to use each week.
- **Risk model**: Ledoit-Wolf shrinkage on {m["cov_window_weeks"]} weeks of weekly USD returns.
- **Expected returns**: Black-Litterman on the benchmark's equilibrium (δ = {m["risk_aversion"]}, τ = {m["tau"]}), views
  worth up to {m["view_scale"]} Sharpe units, by family and confidence: """
    + ", ".join(f"{k} {v:.0%}" for k, v in conf.items())
    + f""".
- **Portfolio construction** (convex optimiser, weekly): gross exposure ≤ {sl["gross_max"]:.0%}; net equity
  {sl["equity_net"]["min"]:.0%}-{sl["equity_net"]["max"]:.0%}; semiconductors net {sl["semis"]["min"]:.0%}-{sl["semis"]["max"]:.0%}
  (SK Hynix and Samsung long only, at least 1.5% each: Korean short selling is restricted); alternatives ≤
  {sl["alt_max"]:.0%}; currencies gross ≤ {sl["fx_gross_max"]:.0%}; cash ≤ {sl["cash_max"]:.0%} unless the drawdown
  overlay is on; ex-ante volatility ≤ the benchmark's; tracking error ≤ {m["tracking_error_max"]:.0%}; trading costs
  (×{m["turnover_aversion"]:g}, a 3-month holding) and borrow costs of shorts in the objective; trades under
  {m["no_trade_band"]:.2%} skipped.
- **Drawdown overlay**: """
    + "; ".join(
        f"beyond {lv['drawdown']:.0%} drawdown the risk cap falls to {lv['scale']:.0%}"
        for lv in m["drawdown_overlay"]["levels"]
    )
    + f"""; released below half the threshold.
- **Tail hedge**: one-month S&P 500 puts {1 - th.get("moneyness", 0.95):.0%} out of the money, rolled monthly,
  priced at the VIX × {1 + th.get("skew_premium", 0):.2f}; hedge ratio {th.get("base_ratio", 0):.0%} of net equity,
  +{th.get("trend_ratio", 0):.0%} when US trend is negative, +{th.get("added_ratio", 0):.0%} more when volatility is
  also cheap (stress index below 0).
- **Safeguards**: a price older than {cfg["live"]["stale_days"]} business days freezes the rebalance; kill switch
  `trading_enabled` (now **{"on" if cfg["live"]["trading_enabled"] else "OFF"}**); checks every two hours with a GitHub
  issue when the drawdown passes {cfg["live"]["alerts"]["drawdown"]:.0%} or the day's loss {cfg["live"]["alerts"]["daily_loss"]:.0%}.
- **Record**: every paper rebalance is appended to `archive/portfolio_book.csv` and never edited; an evening report
  (GitHub issue, e-mailed) lists the changes and the research of the day.
"""
)
st.subheader("Universe")
u = pd.DataFrame(cfg["universe"]).T
u["sleeve"] = u["sleeve"].map(SLEEVE_LABEL)
st.dataframe(
    u[["name", "sleeve", "min", "max", "cost_bp", "borrow_bp"]].rename(
        columns={"cost_bp": "trading cost (bp)", "borrow_bp": "borrow (bp a year)"}
    ),
    use_container_width=True,
)
st.caption(f"Model version {b['version']}. " + DISCLAIMER)
footer()
