# Model card — inflation forecasts and diagnostics

| Field | Value |
|---|---|
| Module | `src/macro/inflation.py` (bundle: `macro.pipeline.inflation_bundle`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-27 |
| Status | experimental |

## Purpose
Answer "how far is inflation from target, how persistent is it, and where is it heading?" for the
US and the euro area (Japan: headline decomposition only). Shown on the Inflation page, the weekly
monitor and the monthly view; forecasts are archived every run.

## Inputs
CPI and components (FRED), PCE, Cleveland Fed median/trimmed-mean CPI, Atlanta Fed sticky CPI,
HICP and components (ECB), Brent (EIA via FRED), EURUSD/USDJPY, GSCPI (NY Fed), UNRATE and CBO NROU,
Michigan, SPF, breakevens, Cleveland Fed 10-year expected inflation. Release lags from
`config/series.yaml` are applied at every forecast origin.

## Equations
- Momentum: a_k = 100((P_t/P_{t-k})^{12/k} - 1), k = 1, 3, 6; yoy = 100(P_t/P_{t-12} - 1).
- Persistence: π_t = c + Σ_{j≤p} φ_j π_{t-j} + e_t on core m/m annualised, p by BIC (1..12);
  ρ = Σφ_j with HAC s.e.; half-life from the AR impulse response.
- Energy pass-through: (Δlog P^head − Δlog P^core)_t = a + Σ_{j=0..6} b_j Δlog Oil_{t−j} + e_t;
  B = Σb_j, HAC s.e.; full, pre-2020 and post-2020 samples.
- GSCPI local projections: 100(log y_{t+h} − log y_{t−1}) = a_h + b_h GSCPI_t + controls, h = 0..12.
- Expectations factor: first principal component of standardised measures, rescaled to SPF 10y;
  rolling ΔF_t = a + β Δπ_t (60 months) for anchoring.
- Forecasts (direct, h = 1..12, target = headline yoy):
  RW: π_{t+h} = π_t · AR: π_{t+h} = c + Σ φ_j π_{t−j} (p ≤ 6, BIC) ·
  PC: π_{t+h} = c + φπ_t + β ugap_t + γ Δ12 log oil_t + δ E^{10y}_t ·
  MF: monthly path from component weights, trend core/food and month-to-date oil ·
  EN: elastic net on lags and indicators (time-series CV) · COMB: equal-weight of AR, PC, MF, EN.
  Density: N(point, σ_h²), σ_h = RMSE of the model's own past out-of-sample errors.

## Estimation sample
Monthly from 1990 (US) / 1999 (EA); expanding window; out-of-sample origins from 2005-01.

## Assumptions
Inflation targets and the exceedance margin in `config/assumptions.yaml`. Oil flat beyond the
current month. Gaussian, symmetric bands (the skewed BoE-style fan lives in the scenario module).

## Validation
Scoreboard per horizon (1, 3, 6, 12): RMSE, MAE, relative RMSE vs random walk, DM test vs random
walk, log score, CRPS, PIT KS p-value; SPF benchmark at h = 12. Results are displayed on the page
with "does it beat the random walk" stated explicitly. Latest-vintage, not point-in-time.
Specifications tried: 6 models (see research log).

## Known failure modes
Energy-price regime shifts; pandemic-era outliers; level shifts in the expectations measures;
short EA history; JP component data absent; series ID changes at the source.

## Change history
See `docs/MODEL_CHANGELOG.md`.
