# Model changelog

Every change to a model specification, estimation sample, input set or evaluation design is
recorded here with its reason (BRIEF §2.6). Code that produces an archived forecast is frozen
within an evaluation window (one calendar month): changes merged during a window take effect
in the next window and are logged with that effective date.

| Effective window | Model | Version | Change | Reason | Commit |
|---|---|---|---|---|---|
| 2026-10 | inflation | 0.1.0 | Initial version | Project start | — |
| 2026-10 | policy | 0.1.0 | Initial version | Project start | — |
| 2026-10 | fincond | 0.1.0 | Initial version | Project start | — |
| 2026-10 | curves | 0.1.0 | Initial version | Project start | — |
| 2026-10 | growth | 0.1.0 | Initial version | Project start | — |
| 2026-10 | recession | 0.1.0 | Initial version | Project start | — |
| 2026-10 | transmission | 0.1.0 | Initial version | Project start | — |
| 2026-10 | positioning | 0.1.0 | Initial version | Project start | — |
| 2026-10 | scenarios | 0.1.0 | Initial version | Project start | — |
| 2026-10 | regimes | 0.1.0 | Initial version | Project start | — |
| 2026-11 | inflation | 0.1.1 | Euro area HICP from Eurostat (ECOICOP v2, 2025=100) instead of the discontinued ECB ICP series | Source discontinued after 2025-12 | — |
| 2026-11 | recession | 0.1.1 | Euro area recession indicator = technical recession from Eurostat real GDP (lag 135 days) | OECD-based EUROREC no longer updated | — |
| 2026-11 | growth | 0.1.1 | Survey block: Dallas Fed TMOS production index replaces Empire State current activity | Empire series removed from FRED (404) | — |
| 2026-11 | transmission | 0.1.1 | Euro Stoxx 50 and SOX optional (event study and betas run without them when Yahoo is unavailable); S&P 500 falls back to FRED SP500 (about 10 years) | Yahoo rate limits | — |
| 2026-10 | history | 0.1.0 | Initial version (Global Macro Database cycles, base rates, current position) | New module | — |
| 2026-11 | policy | 0.1.1 | Fed priced path from the Atlanta Fed Market Probability Tracker when fresh (else the dated assumption, else the 2Y yield); BoJ priced proxy from the MOF 2Y JGB yield; JP policy rate from the BoJ API | Fresher, published market pricing | — |
| 2026-11 | curves | 0.1.1 | Japan 10Y daily from the MOF instead of the monthly OECD series | Freshness | — |
| 2026-11 | markets | 0.1.0 | Initial version: cross-asset monitor, stress index, regimes, correlations, sensitivities, curve recession probit | Markets tab | — |
| 2026-11 | markets | 0.2.0 | Universe unchanged; dashboard gains stress testing and recession-signal pages fed by new modules | Markets tab extension | — |
| 2026-11 | leading | 0.1.0 | Initial version: five recession probits (10Y-3M, near-term forward spread proxy, EBP, combinations) with pseudo-out-of-sample evaluation | Recession signals from markets | — |
| 2026-11 | stress_test | 0.1.0 | Initial version: conditional-normal scenarios, coverage backtest, historical episodes and analogs, principal-component factors | Stress testing | — |
| 2026-11 | scenarios | 0.2.0 | Unemployment noise bootstrapped from expansion quarters only | With recession quarters in the noise, the no-shock path triggered the Sahm signal 43% of the time (16% after); research log H24 | — |
| 2026-11 | stress_test | 0.2.0 | Student-t option for conditional scenarios (degrees of freedom from the median excess kurtosis); coverage reported for both | Research log H23 | — |
| 2026-11 | backtest | 0.1.0 | Initial version: Fed rule against the 1-year yield, inflation combination against the SPF; DM and encompassing tests | Does the model beat the market? | — |
| 2026-11 | forecast_book | 0.1.0 | Initial version: 13-week directional probabilities from momentum, value and carry, pseudo-OOS scores, live archive | Measurable record | — |
| 2026-11 | markets | 0.3.0 | Removed the regime forward-moves table (in-sample, no |t| above 2, used by no decision) | Remove what serves no decision | — |
| 2026-11 | stress_test | 0.3.0 | Removed the PCA factor view from the bundle and the app (H19 rejected; no decision used it) | Remove what serves no decision | — |
| 2026-11 | backtest | 0.2.0 | Real-time Fed rule backtest on ALFRED vintages (runs once FRED_API_KEY is set, H26); inflation interval coverage, normal and empirical (H25) | Real-time discipline; honest bands | — |
