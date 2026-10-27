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
| 2026-10-27 | inflation | H1: a forecast combination beats the random walk at h = 12 for US headline yoy (RMSE, DM at 10%). Written before running the evaluation. | 6: RW, AR(BIC), Phillips curve, mixed-frequency (daily oil), elastic net, equal-weight combination | Demo data only so far (synthetic, not informative). Live evaluation pending network access. | all kept for comparison |
| 2026-10-27 | inflation | H2: cumulative energy pass-through is stable across pre/post-2020 samples. | 1 (lags 0-6 fixed a priori) | Demo only. | kept |
| 2026-10-27 | inflation | H3: long-run expectations become more sensitive to realised inflation after 2021 (de-anchoring). | 1 (60-month window fixed a priori) | Demo only. | kept |
