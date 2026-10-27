# Model card — scenario engine, Monte Carlo, fans

| Field | Value |
|---|---|
| Module | `src/macro/scenarios.py`, `src/macro/fans.py` (bundle: `scenario_bundle`, `scenario_results`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-27 |
| Status | experimental |

## Purpose
Conditional paths for the Fed funds rate, core PCE inflation and growth under four scenarios; the
probability of further moves and of a Sahm-type deterioration; BoE-style fans; priced vs model.

## Inputs
Core PCE, UNRATE, CBO NROU, Brent, Fed funds, 2Y and 10Y yields, CBO potential GDP, ACM term premium;
reaction-function estimates from the policy module; `config/scenarios.yaml`.

## Equations
See the module docstring: quarterly Phillips curve (OLS, HAC), unemployment = scenario path + AR(1)
noise with bootstrapped residuals, inertial reaction-function policy with a step cap and a floor,
10Y = 40-quarter average expected policy rate + term premium. Monte Carlo: 10,000 paths per scenario
(residual bootstrap), mixture by probability. TPN fans as in `fans.py`.

## Estimation sample
Quarterly from 1990 (data permitting).

## Assumptions
Scenario paths and probabilities (subjective), r* midpoint of the user range, Okun coefficient,
maximum step of two meetings × 75bp per quarter.

## Validation
Property tests: TPN integrates to one, quantiles monotone, ppf inverts cdf, requested skew reproduced,
mixture weights sum to one, move probabilities monotone in k, step cap and floor respected.

## Known failure modes
Garbage-in on scenario narratives; unstable Phillips-curve slope; recession probability sensitive to
the unemployment noise (reported).

## Change history
See `docs/MODEL_CHANGELOG.md`.
