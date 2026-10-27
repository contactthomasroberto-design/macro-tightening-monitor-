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
| 2026-10-27 | policy | H4: the estimated long-run inflation response b exceeds 1 in the full sample and in both sub-samples (Taylor principle). | 3 samples (full, pre-2008, post-2008 excl. lower bound), 1 specification | Demo only. | kept |
| 2026-10-27 | policy | H5: the "behind the curve" verdict (Taylor rule above the actual rate) is robust to r* in [0, 1.5] and a_pi in [1, 2.5]. | 1 grid fixed a priori | Demo only; the page reports "not robust" when the sign flips. | kept |
| 2026-10-27 | fincond | H6: rate variables carry negative and equities/house prices positive growth sensitivities (FCI-G signs). | 2 lookbacks (1y, 3y); ridge penalty from a fixed 8-value grid by CV | Demo: house-price and Baa signs differ from the prior in at least one lookback — reported as such, equivalences flagged when unstable. | kept |
| 2026-10-27 | data | Replace ICE BBB yield by Moody's Baa in the FCI (history length). | — | Decision before estimation. | kept |
| 2026-10-27 | curves | H7: bear flatteners are over-represented during Fed hiking phases (rate up over 6 months) relative to other periods. | 1 (21-day window, 5bp threshold fixed a priori) | Demo only. | kept |
| 2026-10-27 | growth | H8: the DFM nowcast beats an AR(1) just before the advance release (RMSE, DM at 10%). | 1 factor structure (Global/Soft/Nominal/Labor, AR(2) factors) fixed a priori | Demo only. | kept |
| 2026-10-27 | growth | H9: NFCI lowers the 5% conditional quantile of future growth more than the median (ABG asymmetry). | 2 horizons (1Q, 4Q) | Demo only. | kept |
| 2026-10-27 | recession | H10: adding credit spread, unemployment change and NFCI to the term-spread probit improves out-of-sample AUC and Brier. | 3 (spread probit, extended probit, L2 logit) | Demo only. | kept |
| 2026-10-27 | transmission | H11: the stock-bond correlation is positive when core inflation exceeds 3% and negative/zero below 2%. | 1 (3 buckets fixed a priori) | Demo only (planted by the simulator, so not evidence). | kept |
| 2026-10-27 | transmission | H12: semiconductors and AI leaders have larger (more negative) real-yield betas than the S&P 500. | 1 per asset + 3 regimes | Demo only. | kept |
| 2026-10-27 | positioning | No hypothesis tested: descriptive monitor. | — | — | kept |
