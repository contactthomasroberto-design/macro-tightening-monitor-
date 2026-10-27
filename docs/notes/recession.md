# Note — recession probabilities

Primary sources:
- Estrella and Mishkin (1998), *Predicting U.S. Recessions: Financial Variables as Leading Indicators*, REStat.
- Sahm (2019), *Direct Stimulus Payments to Individuals* (Sahm rule), Hamilton Project.
- NY Fed yield-curve recession probability page (3m10y probit) for the benchmark specification.

**Reading status:** not downloadable from the build environment; specifications follow the standard
published forms.

## What is replicated
- 12-month-ahead probit on the 3m10y spread; extension with credit spread, 6-month change in
  unemployment and NFCI; L2-regularised logit as robustness; Sahm rule.
- Expanding-window evaluation (AUC, Brier vs climatology, calibration), block-bootstrap band on the
  current probability, number of episodes always shown.

## What is simplified, and why
- Moody's Baa−10Y as credit spread (long free history) rather than ICE HY OAS.
- NBER dates used as known when fitting; in real time they arrive 6-12+ months late (stated).

## What could break
- Very few recessions; spread-based models misfired in 2022-24 in the actual US data (curve
  inverted, no NBER recession by the time of writing — check before publication).
