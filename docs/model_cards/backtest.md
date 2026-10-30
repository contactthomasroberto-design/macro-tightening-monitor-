# Model card — backtests against the market

| Field | Value |
|---|---|
| Module | `src/macro/backtest.py` (bundle: `pipeline.backtest_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-30 |
| Status | experimental |

## Purpose
Answer the question a portfolio manager asks first: do the models add anything to market prices and
to the professional consensus?

## Inputs
DFF, DGS1, PCEPILFE, GDPC1, GDPPOT; the inflation module's pseudo-out-of-sample forecasts (COMB, SPF, RW).

## Equations
Fed: target = mean of DFF over t+1..t+12. Rule: i_t = α + ρ i_{t−1} + β π_t + γ y_t, OLS on data to t,
iterated 12 months with π and y fixed (π lagged 1 month, y 4 months). Market: DGS1 at t.
Scores: RMSE, MAE, bias; Diebold-Mariano (squared loss, HAC, HLN correction); encompassing
(realised − bench) = a + b (model − bench), Newey-West h − 1 lags; hit rate when |gap| > 0.5 pp.

## Estimation sample
Monthly origins 1990-01 to the last month with a known outcome; inflation origins from 2005.

## Validation
Results recorded against pre-registered hypotheses H20 and H21 (research log).

## Known failure modes
Latest-vintage data (revised) flatter the model; the T-bill/fed funds basis and the term premium bias
the market proxy upward (reported as bias); the rule holds inflation and the gap constant.

## Change history
See `docs/MODEL_CHANGELOG.md`.
