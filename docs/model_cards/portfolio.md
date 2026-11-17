# Model card — systematic portfolio

| Field | Value |
|---|---|
| Module | `src/macro/portfolio.py`, `src/macro/portfolio_live.py` (bundle: `pipeline.portfolio_bundle`) |
| Version | 0.3.0 |
| Owner | project author |
| Last review | 2026-11-17 |
| Status | experimental (paper only) |

## Purpose
A systematic multi-asset alternative fund on paper: long and short across about fifty global
instruments, gross exposure up to 160%, with a drawdown no larger than the 60/40 ACWI/AGG benchmark's
and a conviction sleeve in semiconductors (SK Hynix, Samsung Electronics, Micron, TSMC, NVIDIA, ASML).
It places no orders and is not investment advice.

## Inputs
Adjusted daily closes (Yahoo) of 51 instruments plus the KRW rate. Macro data: EBP, core CPI, industrial
production, CPI, and the monitor's stress index. Carry: Treasury yields, TIPS real yield, credit spreads,
SOFR, €STR, the Japan call rate. SEC quarterly revenue of Micron and NVIDIA, dated at filing. GDELT
company news tone. Dated house views (config/house_views.yaml). VIX for the tail hedge.

## Equations
Weekly USD returns, Ledoit-Wolf covariance (156 weeks). Black-Litterman: π = δ Σ w_eq, with views
q_i = π_i + 0.25 σ_i s_i from eight families, each with its own confidence: trend, macro, regime,
value, carry, micro, house, news (gated by H32).
The optimiser (cvxpy, Clarabel) maximises μ'w − δ/2 w'Σw − borrow'(−w)⁺ − 4·cost'|w − w_prev| subject to:
- Σw = 1 and the line bounds;
- Σ|w| ≤ 1.6;
- semiconductors net between 5% and 15%; net equity between 20% and 90%;
- alternatives ≤ 15%; currencies gross ≤ 20%; cash ≤ 10% outside the overlay;
- σ ≤ σ_benchmark × overlay scale; tracking error ≤ 8%.

Overlays:
- a drawdown overlay (8% and 15%);
- monthly one-month 5% OTM S&P 500 puts at the VIX × 1.15, hedge ratio 25-100% of net equity by trend
  and stress.

## Estimation sample
Walk-forward from January 2005, weekly rebalancing. Instruments enter once they have 52 weeks of history.

## Validation
Pre-registered H27-H35. Ablations: long only, no hedge, no overlay, no views, v0.2 style.
Comparisons with equal weight, minimum variance, ERC and HRP. Deflated Sharpe over every configuration
run. The paper book starts 2026-11-20 and is never edited.

Operational checks (`src/macro/fund_checks.py`):
- **Funds one can buy.** Metrics against DBMF (managed futures), RPAR (risk parity), QAI and HDG
  (hedge-fund replication) over the common history of all of them, net of their fees. Funds with less
  than a year of history are left out. Shown on Portfolio → Backtest.
- **Liquidity.** Days to liquidate each position of a USD 100m notional fund (`live.notional_usd`) at
  10% of average daily traded value. A position is flagged above one day or above 1% of a day's
  volume. The ADV figures are static, rounded, dated estimates (`liquidity.adv_usd`), not live data.
  Shown on Portfolio → Risk.
- **Price anomalies.** The two-hourly monitor flags:
  - a daily move beyond 6 trailing-year standard deviations that the sector proxy did not share
    (beyond 3 sd);
  - a same-day close that differs by more than 2% between Yahoo and Stooq (US listings only).

  Anomalies go to `archive/price_anomalies.csv`, open one GitHub issue each, and appear in the
  evening report. They never change a position automatically.
- **Model health** (Portfolio → Model health):
  - the weight change at each rebalance;
  - ex-ante volatility (sample covariance of the trailing three years, every fourth rebalance)
    against the volatility realised over the next 26 weeks;
  - the limits binding today;
  - optimiser fallbacks over the backtest;
  - the paper book against the backtest, once it has two weeks.

## Known failure modes
- Shorts: borrow availability and recalls are not modelled beyond a cost; squeezes on crowded shorts.
- Synthetic puts: Black-Scholes at the VIX plus a fixed skew premium; real put prices and bid-ask differ.
- Mean-variance corner solutions are dampened by Black-Litterman, bounds and costs, not removed.
- House views cannot be backtested; they enter with a 10% confidence only.
- Survivorship: the semiconductor names were chosen in 2026, knowing they survived.
- ETF proxies for futures-based exposures (oil, managed futures) carry roll costs that futures would not.
- Liquidity uses static ADV estimates. Volumes fall in crises, exactly when exits matter, so the check
  is an order of magnitude, not a guarantee.
- The second price source covers US listings only. The Korean names rely on the jump check alone, and a
  Stooq outage silently leaves only that check.

## Change history
See `docs/MODEL_CHANGELOG.md`.
