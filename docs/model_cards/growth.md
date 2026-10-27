# Model card — GDP nowcast (DFM) and Growth-at-Risk

| Field | Value |
|---|---|
| Module | `src/macro/growth.py` (bundle: `macro.pipeline.growth_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-27 |
| Status | experimental |

## Purpose
Nowcast current-quarter US real GDP growth weekly with a news decomposition; describe the conditional
distribution of future growth and its downside (Growth-at-Risk).

## Inputs
Monthly: PAYEMS, UNRATE, ICSA, UMCSENT, Philly Fed and Empire current activity, INDPRO, RSAFS, PCEC96,
HOUST, BOPTEXP, CPIAUCSL, PPIFIS. Quarterly: GDPC1. GaR: GDPC1, NFCI. Benchmarks: SPF current quarter.

## Equations
- x_{i,t} = λ_i' f_t + e_{i,t}; f_t = A_1 f_{t-1} + A_2 f_{t-2} + u_t; e_{i,t} AR(1); quarterly GDP
  growth linked to monthly factors by the Mariano-Murasawa aggregation (DynamicFactorMQ).
- Nowcast = E[GDP growth_q | data published by date d]; bands N(point, se²) at 50% and 68%.
- News: Δnowcast = Σ_j w_j (x_j − E_old[x_j]) + revisions effect.
- GaR: Q_τ(y_{t+h} | g_t, NFCI_t) = β_τ' [1, g_t, NFCI_t], τ ∈ {5,25,50,75,95}%; JF skew t fitted to
  the 5/25/75/95% quantiles; ES_5% = 20 ∫_0^0.05 Q(u) du.

## Estimation sample
From 1990 (series enter as they start; ≥36 observations required at the fit date).

## Assumptions
Factor structure fixed a priori; release lags from `config/series.yaml`.

## Validation
Real-time evaluation at three points of each quarter (RMSE, MAE, DM vs AR, vs SPF, log score, 68%
coverage); GaR recursive backtest (PIT, log score vs unconditional, 90% coverage); identity test that
news contributions add up to the nowcast change.

## Known failure modes
Pandemic outliers; parameter instability; small panel; skew-t shape at bounds.

## Change history
See `docs/MODEL_CHANGELOG.md`.
