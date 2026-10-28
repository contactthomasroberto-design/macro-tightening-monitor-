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
