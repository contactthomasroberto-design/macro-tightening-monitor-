# Model card — transmission

| Field | Value |
|---|---|
| Module | `src/macro/transmission.py` (bundle: `macro.pipeline.transmission_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-27 |
| Status | experimental |

## Purpose
Quantify how tightening transmits to yields, equities (including rate-sensitive sectors), the dollar
and FX, with uncertainty and sample sizes.

## Inputs
DFEDTARU, DGS2, DGS10, DFII10, T10YIE, CPILFESL, S&P 500, Euro Stoxx 50, SOX, AI-leader stocks, broad
dollar, EURUSD, USDJPY, EA 2Y AAA, JGB 10Y.

## Equations
- corr(r^eq_m, −Δy10_m) within core-inflation buckets; moving-block bootstrap (6 months).
- Event path: x_{e+k} − x_{e−6}, k ∈ [−5, 5], mean over events, bootstrap over events.
- r_t = a + b_real Δreal_t + b_be Δbe_t + e_t (weekly, HAC), rolling 52 weeks and by regime.
- LP: y_{t+h} − y_{t−1} = a_h + b_h s_t + e, s = Δ2Y on decision days, HC1.
- FX: 100 log FX_t = a + b diff_t + u_t (HAC) and the same in first differences.

## Estimation sample
Full daily/weekly/monthly history of each series.

## Assumptions
Inflation buckets (2%, 3%) and windows fixed a priori.

## Validation
Planted-effect tests (event jump, real-yield beta, regime correlation); N shown everywhere.

## Known failure modes
Proxy surprises, overlapping windows, structural breaks, survivorship in the AI basket.

## Change history
See `docs/MODEL_CHANGELOG.md`.
