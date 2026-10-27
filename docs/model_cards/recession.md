# Model card — recession probabilities

| Field | Value |
|---|---|
| Module | `src/macro/recession.py` (in `macro.pipeline.growth_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-27 |
| Status | experimental |

## Purpose
Probability of a US recession 12 months ahead, with uncertainty and out-of-sample evidence; euro-area variant.

## Inputs
T10Y3M, BAA10Y, UNRATE, NFCI, USREC; euro area: AAA 2Y/10Y, EA unemployment, EUROREC.

## Equations
P(REC_{t+12}=1) = Φ(a + b·spread_t) and Φ(a + b'x_t) with x = (spread, credit spread, Δ6 u, NFCI);
L2 logit with penalty by time-series CV; Sahm_t = ū3_t − min_{12m}(ū3) ≥ 0.5.

## Estimation sample
Monthly, full history of the regressors; out-of-sample origins from 1998.

## Assumptions
NBER dates treated as known in estimation (they are not in real time).

## Validation
AUC, Brier vs climatology, calibration bins (expanding window); moving-block bootstrap (12 months,
300 draws) band on the current probability; episodes counted and shown.

## Known failure modes
Few events; structural changes in the term premium weaken the spread signal.

## Change history
See `docs/MODEL_CHANGELOG.md`.
