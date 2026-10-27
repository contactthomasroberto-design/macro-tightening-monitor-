# Model card — policy rules and reaction function

| Field | Value |
|---|---|
| Module | `src/macro/policy.py` (bundles: `macro.pipeline.policy_bundle`, `cross_bank_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-27 |
| Status | experimental |

## Purpose
Benchmark each central bank's policy rate against standard rules under r* uncertainty, estimate how
the bank has actually reacted to inflation and slack, and compare priced vs prescribed moves.

## Inputs
Fed: DFF, core PCE, UNRATE, CBO NROU, GDPC1/GDPPOT, DGS2, HLW/LW r*. ECB: deposit rate, HICP ex
energy and food, EA unemployment, EA 2Y AAA yield, HLW euro-area r*. BoJ: call rate, CPI.

## Equations
- Taylor: i = r* + π* + a_π(π − π*) + a_y y (1993: a_π = 1.5, a_y = 0.5); balanced approach a_y = 1.
- Unemployment-gap: y ≈ −okun (u − u*). First difference: i_t = i_{t−1} + 0.5(π − π*) + 0.5 Δ4 y.
- Inertial: i_t = ρ i_{t−1} + (1 − ρ) i^Taylor_t.
- Reaction function: i_t = ρ i_{t−1} + (1 − ρ)(a + bπ_t + c y_t) + ε_t, linear OLS with HAC s.e.,
  long-run coefficients by delta method; Taylor principle H0: b ≤ 1.
- Reverse view: π such that the Taylor rule prescribes the priced rate.
- Synchronisation: share of banks with a positive 12-month change; mean pairwise rolling correlation.
- FX: rolling β of weekly Δlog FX on Δ(2Y differential).

## Estimation sample
Quarterly averages; full sample, pre-2008, post-2008; rolling 48 quarters. Lower-bound quarters
(i_t and i_{t−1} < 0.25%) excluded.

## Assumptions
Inflation targets, rule parameters, r* range, priced paths: `config/assumptions.yaml` (editable in the sidebar).

## Validation
Planted-parameter recovery test; split-sample stability; robustness of the policy-gap sign across the
(r*, a_π) grid stated on the page. N shown for each estimate.

## Known failure modes
Lower bound, unobserved r* and output gap, few hiking cycles, structural change in reaction (e.g.
flexible average inflation targeting 2020), the 2-year yield proxy embedding a term premium.

## Change history
See `docs/MODEL_CHANGELOG.md`.
