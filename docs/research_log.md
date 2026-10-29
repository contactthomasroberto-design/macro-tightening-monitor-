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
| 2026-10-27 | scenarios | Design choice (no hypothesis): fan variance from Monte Carlo dispersion until the archive holds enough own forecast errors. | 1 | — | kept; revisit when archive N ≥ 40 |
| 2026-10-27 | scenarios | Unemployment noise: AR(1)-residual bootstrap winsorised at 2.5/97.5% (first version used raw quarterly changes incl. 2020, which dominated the recession probability). | 2 | First version rejected before publication. | second kept |
| 2026-10-27 | regimes | H13: the Markov-switching high-inflation regime coincides with the 2x2 'overheating/stagflation' quarters more than 70% of the time. | 1 | Demo only. | kept |
| 2026-10-28 | data | First live smoke test (`make test-live`): 42 of 106 series failed. Decisions taken before any model was re-estimated on live data. | — | Replacements: ECB HICP (discontinued after 2025-12) → Eurostat `prc_hicp_minr` ECOICOP v2, index 2025=100; OECD-based EUROREC (stale) → technical recession from Eurostat real GDP (two or more consecutive q/q declines); OECD Japan CPI on FRED (stale) → BIS long CPI; Empire State (404 on FRED) → Dallas Fed TMOS (`BACTSAMFRBDAL`); CFTC TFF queried by contract code (stable through the 2022 renames); SPF CPI from `Inflation.xlsx` (median); FCI-G from the Fed Board csv; HLW/LW parsed by header. Yahoo rate limits (HTTP 429): FRED fallbacks for S&P 500, Nikkei, VIX, FX, broad dollar and Brent; the other Yahoo series flagged optional. CIE has no scripted download (manual file, optional). After the fixes: 105 pass, CIE skipped. | kept |
| 2026-10-28 | history | H14: tightening cycles that end with high inflation at the peak (> 5%) are more often followed by recession than cycles ending with inflation of 2-5%. Written before running the summary. | 1 definition (1pp rise, 0.5pp fall, 2-year window), 1 logit (rise, inflation at peak, real rate at peak) | First run on GMD 2026_09 (1,210 cycles, 171 countries): > 5% 43% vs 2-5% 31% (non-overlapping 95% intervals), but < 2% is highest at 57% (mostly gold-standard and interwar cycles); the logit on the continuous variables finds no significant effect (N = 1,134). Partially supported; the relation is not monotonic. | kept |
| 2026-10-28 | data | Freshness audit after the first live run. | — | Added: Atlanta Fed Market Probability Tracker (daily priced fed funds path, replaces the hand-entered OIS assumption when fresh), MOF JGB daily yields (JP 10Y, new JP 2Y), BoJ API call rate (monthly and daily, replaces the OECD MEI copy on FRED), SOFR, €STR, GDPNow and the Weekly Economic Index as external benchmarks. Not found free: OIS-implied paths for the ECB and the BoJ; Japan CPI fresher than BIS without an e-Stat API key. | kept |
| 2026-10-29 | markets | H15: a three-component stress index (VIX, MOVE, Baa-10Y; rolling 5-year z-scores, equal weights) correlates above 0.5 with the St. Louis Fed index in 4-week changes. Written before computing it. | 2 component sets | First set included the ICE BofA IG and HY spreads; dropped before validation because FRED serves only their last three years, which made the index change composition in 2025. Kept set: 0.75 in levels, 0.71 in 4-week changes (1993-2026, 1,713 weeks); NFCI 0.64 and 0.46. Supported. | kept |
| 2026-10-29 | markets | FX and gold sensitivities to rate differentials. | 2 (daily, weekly changes) | Daily changes gave R² near zero for EUR/USD and USD/JPY over the last year; weekly changes were chosen on a priori grounds (asynchronous Tokyo, Frankfurt and New York closes) after seeing this, which is recorded here. Weekly R² over two years remains low (0.01-0.05 for FX), reported as found. | weekly kept |
| 2026-10-29 | markets | H16: the 10Y-3M probit slope is negative and significant on the project's data. | 1 | b = -0.44 (s.e. 0.08), pseudo-R² 0.14, in-sample AUC 0.81 (1982-2025). Supported. | kept |
