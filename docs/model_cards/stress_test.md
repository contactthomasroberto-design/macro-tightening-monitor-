# Model card — cross-asset stress testing

| Field | Value |
|---|---|
| Module | `src/macro/stress_test.py` (bundle: `pipeline.stress_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-29 |
| Status | experimental |

## Purpose
Consistent what-if scenarios across assets and replay of historical stress episodes. Descriptive:
no forecast of prices, no positions. The common-factor (PCA) view was removed from the app and the
bundle on 2026-10-30 (no decision used it); `pca_factors` stays tested for research use.

## Inputs
The Markets universe (`config/markets.yaml`, 23 series); US core CPI for the high-inflation window.

## Equations
Weekly changes x ~ N(0, Σ). Given shocks s over h weeks: E[x | s] = Σ_xs Σ_ss⁻¹ s, Var[x | s] =
h·(Σ_xx − Σ_xs Σ_ss⁻¹ Σ_sx). Σ from pairwise moments with negative eigenvalues clipped. Episodes:
start-to-end moves; similarity = correlation of moves scaled by weekly s.d. × √weeks. Factors:
eigenvectors of the correlation matrix of standardised weekly changes over five years.

## Estimation sample
Weekly from 1990; covariance windows: last 104 weeks, since 2000, weeks with US core CPI above 3%.

## Assumptions
Normality, zero mean, independent weeks (for scaling by h); linear propagation of shocks.

## Validation
Out-of-sample coverage (H18): 72.8% inside ±1 s.d., 93.4% inside ±1.96 s.d., 879 weeks from 2010.
Factor stability (H19): rejected for single factors, plane of factors 1-2 stable (post hoc).

## Known failure modes
Tails fatter than normal; correlations shift in crises (use the high-inflation or since-2000 window
to see how much); short histories for the ICE BofA spreads; episodes before a series existed are blank.

## Change history
See `docs/MODEL_CHANGELOG.md`.
