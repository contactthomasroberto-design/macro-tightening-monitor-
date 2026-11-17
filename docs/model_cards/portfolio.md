# Model card — systematic portfolio

| Field | Value |
|---|---|
| Module | `src/macro/portfolio.py`, `src/macro/portfolio_live.py` (bundle: `pipeline.portfolio_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-11-17 |
| Status | experimental (paper only) |

## Purpose
A rules-based balanced portfolio against a 60/40 ACWI/AGG benchmark, with a drawdown no larger than
the benchmark's and a conviction sleeve in semiconductors (SK Hynix, Samsung Electronics, Micron,
TSMC, NVIDIA, ASML). Tracked on paper; it places no orders and is not investment advice.

## Inputs
Adjusted daily closes (Yahoo) of 19 ETFs and shares and the KRW rate; DGS3MO (cash before BIL);
EBP (Fed Board), CPILFESL (BLS), the monitor's stress index; SEC EDGAR quarterly revenue and gross
profit of Micron and NVIDIA dated at the filing date; GDELT daily news tone on three themes.
Every parameter: `config/portfolio.yaml`.

## Equations
Weekly USD returns; covariance = Ledoit-Wolf-shrunk correlation (towards the identity) × volatilities,
156 weeks. π = δ Σ w_eq (δ = 2.5). Views q_i = π_i + 0.25 σ_i s_i with s in [-1, 1] by family
(trend, macro, micro, news), Ω_ii = τ σ_i² (1 − c)/c, τ = 0.05. Black-Litterman posterior μ, then
max μ'w − δ/2 w'Σw subject to long-only bounds, sum 1, semiconductors 5-15% (5% per name; SK Hynix
and Samsung ≥ 1.5%), total equity 60% ± 15 pp, cash ≤ 10% outside the overlay, σ(w) ≤ σ(w_eq) × scale,
tracking error ≤ 5% (SLSQP; the tracking-error cap, then the volatility cap, are relaxed if infeasible).
Drawdown overlay: scale 0.75 beyond an 8% drawdown, 0.50 beyond 15%, released below half the threshold.

## Estimation sample
Walk-forward from January 2005, weekly data, monthly rebalance; every estimate uses data up to the
rebalance date only (tested: changing the future does not change past weights).

## Validation
Pre-registered H27-H31: drawdown and Sharpe against the benchmark; ablations (overlay, trend, macro,
micro); memory-cycle and news-tone information coefficients on non-overlapping samples; deflated
Sharpe ratio over all configurations run. Paper book archived from 2026-11-20 and never edited.

## Known failure modes
- Mean-variance corner solutions: mitigated by Black-Litterman, the cash cap and bounds, not removed.
- Fixed macro signs: an inflation shock where bonds and equities fall together hurts both sleeves.
- The overlay acts after losses: it limits a long drawdown, not a crash inside one week.
- Korean shares: closes 14 hours before New York; Yahoo outages freeze trading in them (stale gate).
- Free fundamentals cover US filers only; Korean makers rely on prices and Micron's cycle.
- Backtest survivorship: the semiconductor names were chosen in 2026, knowing they survived.

## Change history
See `docs/MODEL_CHANGELOG.md`.
