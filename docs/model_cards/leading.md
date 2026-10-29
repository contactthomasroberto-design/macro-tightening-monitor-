# Model card — recession signals from markets

| Field | Value |
|---|---|
| Module | `src/macro/leading.py` (bundle: `pipeline.leading_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-29 |
| Status | experimental |

## Purpose
Compare market-based recession models out of sample and show their current probabilities next to
the project's macro recession model and the Fed Board's published excess-bond-premium model.

## Inputs
DGS10, DGS3MO, DGS2, DGS1 (FRED), EBP (Fed Board staff), USREC (NBER via FRED); EBP_PROB as benchmark.

## Equations
P(recession in t+1..t+12) = Φ(a + b'x_t), x_t one of: 10Y−3M spread; near-term forward spread
proxy 2·y2 − y1 − y3M; EBP; NTFS + EBP; 10Y−3M + EBP (monthly averages). Full-sample fits with HAC
(12 lags) standard errors; pseudo-out-of-sample forecasts from expanding windows, training only on
months s with s + 12 ≤ t.

## Estimation sample
1982 onward for the spreads (3-month bill on FRED), 1973 for the EBP; forecast origins from 1990.

## Assumptions
Probit link; constant coefficients; the six-quarter forward rate is proxied.

## Validation
AUC, Brier, log score and Brier skill against the expanding base rate, with 24-month block-bootstrap
intervals; EBP-only model against the Fed Board's published probability (8.5% vs 9.1% for the 12
months from September 2026). Pre-registered hypothesis H17 and its result in the research log.

## Known failure modes
Few recessions (four since 1990); NBER dates are known only with a delay; the EBP history is revised
every month; the 2022-24 curve inversion without recession penalises spread models.

## Change history
See `docs/MODEL_CHANGELOG.md`.
