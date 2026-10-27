# Model card — positioning

| Field | Value |
|---|---|
| Module | `src/macro/positioning.py` (bundle: `macro.pipeline.positioning_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-27 |
| Status | experimental |

## Purpose
Show whether speculative positioning is stretched in rates, equities and FX, as context for the view layer.

## Inputs
CFTC TFF net positions (leveraged funds, asset managers) for 10Y notes, 3M SOFR, E-mini S&P 500, euro, yen; SPX, EURUSD, USDJPY.

## Equations
10Y equivalents = contracts × DV01 ratio; USD notional = contracts × multiplier × price; percentile =
share of the last 156 weekly observations below the latest; crowded if ≥ 90 or ≤ 10.

## Estimation sample
Weekly from the start of each TFF series.

## Assumptions
DV01 ratios approximate (stated); 3-year window.

## Validation
Unit tests on conversions and flags.

## Known failure modes
Contract changes, basis-trade positions, publication delays around holidays.

## Change history
See `docs/MODEL_CHANGELOG.md`.
