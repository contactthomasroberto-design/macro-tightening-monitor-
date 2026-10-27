# Note — growth nowcast and Growth-at-Risk

Primary sources:
- Almuzara, Baker, O'Keeffe and Sbordone (2023), *The New York Fed Staff Nowcast 2.0*, technical paper.
- Bańbura and Modugno (2014) / Bok et al. (2018) for the mixed-frequency DFM and news decomposition;
  statsmodels `DynamicFactorMQ` documentation (EM estimation, `news`).
- Atlanta Fed GDPNow methodology (archive, track record, no subjective adjustment, code freeze).
- Adrian, Boyarchenko and Giannone (2019), *Vulnerable Growth*, AER (NY Fed SR 794); IMF WP 18/180.

**Reading status:** not downloadable from the build environment. Statements below follow the brief's
summary and the published abstracts; check the primary texts before publication.

## What is replicated
- A mixed-frequency DFM with Global / Soft / Nominal / Labor factors and a weekly news decomposition
  by release category, with 50% and 68% bands (Nowcast 2.0 publishes these bands).
- Pseudo real-time evaluation at fixed points of the quarter with release lags, against AR and SPF.
- GDPNow habits: forecasts archived each run, track record, model changelog, code freeze per window.
- ABG quantile regressions on current growth and NFCI, skewed distribution fitted to 5/25/75/95%
  quantiles, expected shortfall, recursive backtest with PIT and log score.

## What is simplified, and why
- 13 monthly series instead of ~38; no time-varying growth trend (Nowcast 2.0 has one).
- Parameters re-estimated every 5 years in the evaluation (speed); latest-vintage outcomes.
- Jones-Faddy skew t instead of the Azzalini-Capitanio skew t; four-quantile least squares fit with
  bounded shape parameters.

## What could break
- COVID-era outliers dominate squared-error metrics (report MAE too).
- Survey series ID changes (Philly Fed, Empire flagged `verify`).
- GaR with few severe downturns: tail quantiles imprecise.
