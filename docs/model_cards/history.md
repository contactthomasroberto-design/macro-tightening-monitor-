# Model card — historical tightening cycles

| Field | Value |
|---|---|
| Module | `src/macro/history.py`, `src/macro/data/gmd.py` (bundle: `history_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-28 |
| Status | experimental |

## Purpose
Base rates from history: how often tightening cycles have been followed by a recession or a banking
crisis, by size of the cycle, inflation at the peak and era; where the Fed, the euro area (Germany as
proxy) and the BoJ stand against comparable past cycles.

## Inputs
Global Macro Database (annual, country × year): `cbrate` (else `strate`), `infl`, `rGDP`,
`BankingCrisis`. Licence: free for academic use; other uses need written permission from the authors.
Downloaded at run time, cached in `data/cache/gmd/` (refreshed every 30 days), never committed.

## Equations
Cycle: trough year t to peak year p of the policy rate i, with i_p − i_t ≥ 1pp, the peak being the
highest rate before a fall of 0.5pp. Recession after = min over years p..p+2 of Δlog real GDP < 0.
Crisis after = a banking crisis in t..p+2. Shares with 95% Wilson intervals; logit of recession on the
rise, inflation at the peak and the real rate at the peak, standard errors clustered by country.
Current position: trough = lowest rate in the last six realised years, peak = highest rate after it.

## Estimation sample
Realised years only (≤ last full calendar year; the latest release includes projections). About
1,200 cycles in about 170 countries, 1700s to the last full year.

## Assumptions
Thresholds (1pp rise, 0.5pp fall, two-year window) fixed a priori. Germany stands in for the euro area.

## Validation
Unit tests on planted panels (dating, outcomes, open outcome windows, projection cut-off, ignored years,
Wilson interval, self-exclusion of the cycle being assessed).

## Known failure modes
Annual data misses short cycles and short recessions; heterogeneous policy regimes (gold standard,
wars, pegs) pooled; 2020 counted as a recession year unless excluded (robustness row shown); data
quality of early years varies by country.

## Change history
See `docs/MODEL_CHANGELOG.md`.
