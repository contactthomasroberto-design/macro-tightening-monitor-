# Model card — FCI-lite and gap to neutral

| Field | Value |
|---|---|
| Module | `src/macro/fincond.py` (bundle: `macro.pipeline.fincond_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-27 |
| Status | experimental — research series, not an official statistic |

## Purpose
Measure the growth drag from financial conditions, decompose it by variable, and translate the gap
to conditions consistent with closing the output gap into single-variable equivalences.

## Inputs
DFF, DGS10, MORTGAGE30US, DBAA, S&P 500, Case-Shiller national HPI, broad dollar (DTWEXBGS); real
GDP and CBO potential; NFCI, BAA10Y, VIX, 10Y-3M for the comparison indices; FCI-G if supplied.

## Equations
- Δx_k over L quarters (pp for rates, 100·Δlog for prices), L = 4 or 12.
- g_{t,t+4} = c + Σ β_k Δx_{k,t} + φ g_{t−4,t} + e_t, ridge on standardised regressors, penalty by
  expanding-window CV; moving-block bootstrap (block 8 quarters, 500 draws).
- FCI_t = −Σ β_k Δx_{k,t}; contribution_k = −β_k Δx_{k,t}.
- FCI* = y_t·4/H; gap = FCI* − FCI_t. Equivalence Δx_k = −gap/β_k (median and 16-84% over draws).

## Estimation sample
Quarterly, full available history of all seven variables (live: from 2006 because of the dollar index).

## Assumptions
H = 8 quarters and ±30% multiplier uncertainty (`config/assumptions.yaml`).

## Validation
Planted-sensitivity recovery test (signs and scale); decomposition adds up; projection decays to zero
with unchanged levels; comparison with NFCI, statistical factor and (when available) FCI-G.

## Known failure modes
Sign instability among collinear rates; regime dependence of sensitivities; output-gap mismeasurement.

## Change history
See `docs/MODEL_CHANGELOG.md`.
