# Model card — <model name>

| Field | Value |
|---|---|
| Module | `src/macro/<module>.py::<function>` |
| Version | 0.1.0 |
| Owner | <author> |
| Last review | YYYY-MM-DD |
| Status | experimental / in use / retired |

## Purpose
What question the model answers and where its output is shown (dashboard page, report).

## Inputs
Series ids (see `config/series.yaml`), frequency, transformations, publication lags handled.

## Equations
The exact specification implemented (mirrors the docstring and `docs/methodology.md`).

## Estimation sample
Start, end, frequency, N; split samples used for stability checks.

## Assumptions
Every assumption, including editable inputs in `config/assumptions.yaml`.

## Validation
Benchmarks (random walk, AR, SPF), metrics (RMSE, MAE, log score / CRPS, PIT, DM test),
evaluation design (real-time vintages or latest-vintage, stated), number of specifications tried.
If the model does not beat its benchmark, say so here.

## Known failure modes
Structural breaks, small samples, data revisions, regime dependence, anything that could break it.

## Change history
See `docs/MODEL_CHANGELOG.md`.
