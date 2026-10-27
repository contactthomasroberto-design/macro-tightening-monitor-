# Note — financial conditions module

Primary sources:
- Ajello, Cavallo, Favara, Peterman, Schindler and Sinha (2023), *A New Index to Measure U.S.
  Financial Conditions*, FEDS Notes (FCI-G).
- PIMCO (2026), *Monetary policy through the lens of financial conditions* (practitioner note).
- Chicago Fed, *National Financial Conditions Index* methodology.

**Reading status:** not downloadable from the build environment; the FCI-G description follows the
brief's summary (seven variables, FRB/US multipliers, 3-month changes over 1- or 3-year windows,
positive = headwind) and must be checked against the FEDS Note. The PIMCO note is treated as a
format template (decomposition, current vs target, path on scenarios, equivalences "not forecasts").

## What is replicated
- The FCI-G variable set and sign convention, 1-year and 3-year lookbacks, decomposition by variable.
- The practitioner format: gap between current conditions and those consistent with closing the
  output gap; equivalence table in single-variable terms with uncertainty; projected path.
- A comparison with statistical indices (NFCI and our own principal-component factor).

## What is simplified, and why
- Weights: FCI-G uses FRB/US impulse responses; we estimate growth sensitivities by ridge regression
  of next-year GDP growth on lookback changes (one coefficient per variable and lookback). The model
  is not public in usable form, and a statistical estimate is explainable line by line.
- Lag structure: one aggregated change per lookback instead of model-implied lag distributions of
  3-month changes.
- Corporate yield: Moody's Baa (long free history) instead of ICE BBB.
- Neutral FCI: FCI* = output gap × 4/H — closes the gap in H quarters with linear growth drag.

## What could break
- Collinearity among rate variables (sign instability flagged via bootstrap).
- Short sample in live data (broad dollar from 2006).
- Wrong-signed sensitivities make equivalences meaningless: flagged "not reliable" when the sign
  flips in more than 10% of bootstrap draws.
