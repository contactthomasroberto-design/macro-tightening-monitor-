# Model card — forecast book

| Field | Value |
|---|---|
| Module | `src/macro/forecast_book.py` (bundle: `pipeline.forecast_book_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-30 |
| Status | experimental |

## Purpose
A measurable record: probabilities that eight market variables are higher in 13 weeks, scored out of
sample and, from now on, live at maturity. Forecasts, not recommendations.

## Inputs
DGS2, DGS10, T10Y2Y, EURUSD, USDJPY, SPX, BAA10Y, BRENT_FUT; carry proxies from DGS3MO, DFF, EA_YC_2Y, JP_2Y.

## Equations
P(up) = logistic(b0 + b1 momentum + b2 value + b3 carry); momentum = 26-week change / s.d. of 26-week
changes (3 years); value = 5-year z-score of the (log) level; carry = 5-year z-score of the proxy.
Newton-Raphson logistic fit with a tiny ridge.

## Estimation sample
Weekly; pseudo-out-of-sample origins from 2005, training on origins whose outcome is known.

## Validation
Brier skill against the expanding base rate with a 26-week block bootstrap, AUC, reliability table;
pre-registered hypothesis H22.

## Known failure modes
Overlapping 13-week targets (handled by the block bootstrap); Yahoo outages shorten the S&P 500
history (FRED serves only ten years); signals are public, so skill is expected to be small.

## Change history
See `docs/MODEL_CHANGELOG.md`.
