# Model card — cross-asset markets

| Field | Value |
|---|---|
| Module | `src/macro/markets.py` (bundle: `pipeline.markets_bundle`; universe: `config/markets.yaml`) |
| Version | 0.1.0 |
| Owner | project author |
| Last review | 2026-10-29 |
| Status | experimental |

## Purpose
Describe what markets are doing and pricing, in the same rigour as the macro models: how large each
move is relative to the asset's own history, how stressed markets are, which cross-asset regime
prevails, how the main correlations behave, how much of recent FX, gold and breakeven moves rates
and oil explain, and what the yield curve implies for recession. No forecast of prices, no position.

## Inputs
Rates (DGS2, DGS10, DFII10, T10YIE, T10Y2Y, EA_YC_2Y, EA_YC_10Y, JP_2Y, JP_10Y), credit (BAMLC0A0CM,
BAMLH0A0HYM2, BAA10Y), volatility (VIX, MOVE), FX (DTWEXBGS, EURUSD, USDJPY), equities (SPX, SX5E, N225,
SOX), commodities (BRENT_FUT, GOLD_FUT), T10Y3M and USREC; benchmarks STLFSI4 and NFCI.

## Equations
- Moves: Δy in bp for yields and spreads, 100·Δln P for prices, Δ points for volatility indices.
- Move z-score: z = Δ_h x_T / sqrt(mean(Δ_h x_t²)) over the 756 business days ending at T−h (zero mean).
- Realised volatility: sd of daily changes over 21 days × √252.
- Stress index: S_t = mean_k z_{k,t}, z_{k,t} = (x_{k,t} − μ_{k,t}) / σ_{k,t} over a trailing 1,260-day
  window (minimum 504); components VIX, MOVE, Moody's Baa − 10Y.
- Regime: sign(63-day S&P 500 log return) × sign(63-day change in the 10-year yield).
- Forward moves by regime: mean of Δ_{21} x_{t→t+21}; s.e. = sd / sqrt(n / 21).
- Correlations: 63-day rolling correlation of daily changes; bond return taken as −Δy.
- Sensitivities: OLS of weekly Δy on weekly Δx over 104 weeks, Newey-West (4 lags); explained 13-week
  move = β · Δ_{13} x.
- Curve recession probit: P(USREC_{t+12} = 1) = Φ(a + b · spread_t), spread = monthly mean of T10Y3M.

## Estimation sample
Daily data from each series' start (ICE BofA spreads: last three years only, a FRED restriction);
probit on every month with a known outcome.

## Assumptions
Zero drift in the move z-score; equal weights in the stress index; regime boundaries at zero.

## Validation
- Stress index against the St. Louis Fed (STLFSI4) and Chicago Fed (NFCI) indices, in levels and in
  4-week changes (shown on the page).
- Probit: pseudo-R² and in-sample AUC; slope sign and size compared with the literature (negative).
- Unit tests recover planted parameters (`tests/test_markets.py`).

## Known failure modes
- Asynchronous closes: daily changes across Tokyo, Frankfurt and New York understate co-movement
  (hence weekly sensitivities).
- Few recessions: the probit's in-sample fit flatters it; one regime change (2022 inversion without a
  recession) is visible in its history.
- Yahoo rate limits leave some equity and commodity series stale; the monitor flags staleness.
- Low R² sensitivities are reported as found, not hidden: they mean the driver is not what moves the
  asset at the moment.

## Change history
See `docs/MODEL_CHANGELOG.md`.
