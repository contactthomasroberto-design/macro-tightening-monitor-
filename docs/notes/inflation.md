# Note — inflation module

Primary sources:
- Knotek and Zaman (2024), *Nowcasting Inflation*, Federal Reserve Bank of Cleveland WP 24-06.
- Fed Board, *Research Data Series: Index of Common Inflation Expectations* (FEDS Notes, 2021).
- Benigno, di Giovanni, Groen and Noble (2022), *The GSCPI: A New Barometer of Global Supply
  Chain Pressures*, NY Fed Staff Report 1017.
- Jordà (2005), *Estimation and Inference of Impulse Responses by Local Projections*, AER.

**Reading status:** these documents could not be downloaded from the build environment (network
policy). This note relies on the published abstracts and on standard knowledge of the methods; it
must be checked against the primary texts before any live publication. The primary text wins on
any conflict.

## What is replicated
- **Nowcast logic (Knotek-Zaman):** the key idea that high-frequency energy prices observed inside
  the month carry most of the information about the next headline print, while core and food are
  forecast by recent trends. We aggregate component forecasts with weights estimated on history.
- **Evaluation against consensus for point and density:** RMSE, MAE, log score, CRPS, PIT, DM tests,
  with the SPF as the consensus benchmark (h = 12 only, mapped approximately).
- **Common expectations factor (CIE):** one factor summarising survey and market measures, in
  inflation units.
- **Supply-chain pass-through (SR 1017):** local projections of prices on the GSCPI.

## What is simplified, and why
- Knotek-Zaman use daily oil *and* weekly gasoline prices and their own component models; we use
  Brent only (free, daily, long history) and hold oil flat beyond the current month (no free
  futures curve). The model is called "mixed-frequency (daily oil)" and is labelled simplified.
- The CIE is a dynamic factor model re-estimated each update; we use a static principal component on
  a balanced panel, rescaled to SPF 10-year expectations. Labelled "research series, not official".
- Evaluation uses latest-vintage data with release lags respected. Real-time vintages (ALFRED) are
  wired in the data layer but not yet used in the forecast loop: results are labelled
  "latest-vintage, not point-in-time".
- The SPF benchmark forecasts average CPI inflation over the next four quarters; we compare it with
  the 12-month-ahead yoy rate. The timing mismatch is a few months and is stated on the page.

## What could break
- Structural breaks in pass-through (2021-22) — checked with pre/post-2020 splits.
- Small post-2020 sample (N shown).
- PIT and DM p-values with overlapping multi-step errors are indicative only.
- Series discontinuations (Cleveland median/trimmed, Atlanta sticky CPI IDs are flagged `verify`).
