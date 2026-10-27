# Research log

Hypotheses are written **before** testing; specifications tried and results are recorded,
including failures (BRIEF §2.7). Evaluation metrics and sample splits are fixed before
looking at results. Each dashboard page states how many specifications were tried.

## Pre-registered evaluation design (applies to all forecast models)
- Metrics: RMSE, MAE; for density forecasts log score and CRPS, PIT histogram; Diebold-Mariano
  test (squared-error loss, HAC variance, Harvey-Leybourne-Newbold small-sample correction).
- Benchmarks: random walk, AR(p) with p by BIC, SPF consensus where available.
- Pseudo out-of-sample: expanding window, first forecast origin 2005-01 (monthly models) /
  2005Q1 (quarterly), horizons stated per model.
- Vintages: ALFRED / Philadelphia Fed real-time data where available; otherwise results are
  labelled "latest-vintage, not point-in-time".

## Entries

| Date | Module | Hypothesis (written before test) | Specifications tried | Result | Kept? |
|---|---|---|---|---|---|
