# Model card — regimes and view layer

| Field | Value |
|---|---|
| Module | `src/macro/regimes.py`, `src/macro/views.py` (bundle: `regime_bundle`, `build_views`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-27 |
| Status | experimental |

## Purpose
Classify the macro regime, assemble the scorecard and priced-vs-model table, check market
confirmation of the model view, and produce the structured view for the written notes.

## Inputs
GDPC1, GDPPOT, PCEPILFE, CPILFESL, and the outputs of every other module.

## Equations
Regime: (4Q growth ≥ 4Q potential growth) × (core PCE > target + 0.5). Markov switching:
x_t = μ_{S_t} + ε_t, ε ~ N(0, σ²_{S_t}), two states, smoothed probabilities.
Status thresholds per scorecard metric are listed in `pipeline.build_views`.

## Estimation sample
Quarterly (regime), monthly from 1990 (Markov).

## Assumptions
Margins and thresholds fixed a priori; language guard on views.

## Validation
Unit tests on status mapping, confirmation signs, the language guard.

## Known failure modes
Threshold effects; regimes based on revised data.

## Change history
See `docs/MODEL_CHANGELOG.md`.
