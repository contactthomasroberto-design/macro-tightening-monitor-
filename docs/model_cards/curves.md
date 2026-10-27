# Model card — curves, term premium, sovereign stress

| Field | Value |
|---|---|
| Module | `src/macro/curves.py` (bundle: `macro.pipeline.curves_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-27 |
| Status | experimental |

## Purpose
Describe the US curve and what drives the 10Y yield, classify curve regimes, monitor euro sovereign
stress and the common global duration factor; JGB monitoring.

## Inputs
DGS3MO, DGS2, DGS5, DGS10, DGS30, DFII10, T10YIE, THREEFYTP10, ACMTP10, DE/FR/IT/ES 10Y, EA AAA 2Y/10Y,
JP 10Y, DFEDTARU (hiking condition).

## Equations
- 3m10y = 10y − 3m; 2s10s = 10y − 2y; 5s30s = 30y − 5y; fly = 2·5y − 2y − 10y (bp).
- Regime on rolling 21 business days: Δslope = Δ(10y − 2y), Δlevel = Δ((2y + 10y)/2); sign rules
  as documented in `classify_regime`; range-bound when both |moves| < 5bp.
- Stress: expanding z = (s_t − mean_{≤t})/sd_{≤t}, expanding percentile, speed z = Δ3m s / sd(Δ3m)_{≤t};
  flag if z > 2 or percentile > 95 or speed z > 2.
- Duration factor: PC1 share of standardised monthly 10Y changes, full sample and 60-month rolling.

## Estimation sample
Daily US from the start of each series; monthly euro and Japan series; common sample for the PCA.

## Assumptions
Thresholds fixed a priori; JGB reference level only if entered in assumptions.yaml with source/date.

## Validation
Unit tests on formulas, regime rules, stress flags and PCA recovery on simulated data.

## Known failure modes
Monthly sovereign data miss intra-month stress; term-premium model revisions.

## Change history
See `docs/MODEL_CHANGELOG.md`.
