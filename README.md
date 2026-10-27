# Macro Tightening Monitor

**An open, reproducible macro research stack on the synchronised tightening cycle of the Fed, the ECB
and the Bank of Japan** — a live dashboard, a weekly and monthly written product, and a transparent
model archive (code, model cards, forecast archive, track record, changelog).

> **Disclaimer.** Educational research product. May be revised or discontinued. Not an official view
> of any central bank and not investment advice. No claim of alpha or market track record: this
> project publishes the forecast accuracy of macro models and sensitivities, never price targets.

## 1. Executive summary

<!-- SUMMARY:START -->
_No live results yet. The executive summary is generated from real data by `make live` and the weekly `refresh` workflow (`scripts/update_readme.py`); it is never filled with synthetic numbers._
<!-- SUMMARY:END -->

## 2. Question and thesis

Are the central banks right to tighten, how much tightening is still needed, and how does it transmit
to growth, rates, credit, FX and equities? The project answers with explicit, testable models: rule
prescriptions under r\* uncertainty, an estimated reaction function, a financial-conditions gap, growth
and recession risk with real-time evaluation, transmission estimates, and probability-weighted
scenarios. Every page shows the estimate, its uncertainty, a benchmark or robustness check, and its
limitations.

## 3. What this project replicates, and from whom

| Source | What we take from it | Module |
|---|---|---|
| [NY Fed Staff Nowcast 2.0](https://newyorkfed.org/medialibrary/media/research/blog/2023/NYFed-Staff-Nowcast_technical-paper) | Mixed-frequency DFM, news decomposition by release, 50%/68% bands, real-time evaluation | `growth.py` |
| [Atlanta Fed GDPNow](https://www.atlantafed.org/research-and-data/data/gdpnow) | Forecast archive, public track record, model changelog, code freeze per window | `archive.py` |
| [Cleveland Fed WP 24-06](https://www.clevelandfed.org/publications/working-paper/2024/wp-2406-nowcasting-inflation) | Parsimonious inflation nowcast with daily energy prices; point and density evaluation vs consensus | `inflation.py` |
| [NY Fed r\* (LW, HLW)](https://www.newyorkfed.org/research/policy/rstar) | r\* as an external input with a range, never a single point | `policy.py` |
| [Kim-Wright](https://www.federalreserve.gov/econres/feds/an-arbitrage-free-three-factor-term-structure-model-and-the-recent-behavior-of-long-term-yields-and-distant-horizon-forward.htm), ACM | Published term premia; 10Y = expected short rate + term premium | `curves.py` |
| [Fed Board CIE](https://www.federalreserve.gov/econres/notes/feds-notes/research-data-series-index-of-common-inflation-expectations-20210305.htm) | Common inflation-expectations factor; anchoring check | `inflation.py` |
| [NY Fed GSCPI (SR 1017)](https://www.fedinprint.org/item/fednsr/94243) | Supply-chain pressure and local projections on prices | `inflation.py` |
| [Vulnerable Growth (SR 794)](https://www.newyorkfed.org/research/staff_reports/sr794.pdf), [IMF WP 18/180](https://www.imf.org/en/publications/wp/issues/2018/08/02/the-term-structure-of-growth-at-risk-46150) | Growth-at-Risk: quantile regressions, skewed t, expected shortfall, PIT backtest | `growth.py` |
| [Fed Board FCI-G](https://www.federalreserve.gov/econres/notes/feds-notes/a-new-index-to-measure-us-financial-conditions-20230630.html) | Seven-variable financial-conditions impulse, decomposition (re-estimated as "FCI-lite", not the Fed's index) | `fincond.py` |
| [PIMCO (2026)](https://www.pimco.com/ch/en/insights/monetary-policy-through-the-lens-of-financial-conditions) | Gap to neutral conditions, equivalence table "not forecasts", projected path | `fincond.py` |
| [BoE fan chart (1998)](https://www.bankofengland.co.uk/-/media/boe/files/quarterly-bulletin/1998/the-inflation-report-projections-understanding-the-fan-chart) | Two-piece normal fans, mode as central projection, scenario-based skew | `fans.py` |
| [OFR / CFTC TFF](https://financialresearch.gov/hedge-fund-monitor/datasets/tff) | Positioning by trader type, duration-adjusted, crowding percentiles | `positioning.py` |
| [Philadelphia Fed SPF and RTDSM](https://www.philadelphiafed.org/research-and-data/real-time-center/survey-of-professional-forecasters/historical-data/mean-forecasts) | Consensus benchmarks and real-time data | `evaluation.py` |
| Macro-fund process ([Risk.net](https://www.risk.net/asset-management/hedge-funds/7530341/global-macro-views-combine-with-quantitative-models-to-produce-consistent-returns), sponsored, unverified) | View layer and market-confirmation check (no sizing, no P&L) | `views.py` |

What is replicated, simplified and why is documented per module in [`docs/notes/`](docs/notes/).

## 4. Data, vintages and publication lags

One interface, `get_series(id, vintage=None, as_of=None)`, over FRED/ALFRED, the ECB Data Portal,
Yahoo Finance (personal-use terms), CFTC and research files from the NY Fed, the Fed Board and the
Philadelphia Fed, cached in SQLite with TTLs, retries and graceful degradation. The full catalogue,
with release lags and redistribution terms, is in [`docs/data_catalogue.md`](docs/data_catalogue.md)
(generated from [`config/series.yaml`](config/series.yaml)). Series flagged `verify` must pass the
live smoke test (`make test-live`) before publication.

Real-time discipline: features at date *t* only use data published by *t* (release lags); ALFRED
vintages are used when `FRED_API_KEY` is set, otherwise results are labelled **"latest-vintage, not
point-in-time"**. Raw third-party data is never committed.

## 5. Methods

Equations are in [`docs/methodology.md`](docs/methodology.md); each model has a card in
[`docs/model_cards/`](docs/model_cards/).

- **Inflation.** Decomposition, momentum and broadening; persistence (AR by BIC, rolling sum of
  coefficients, half-life); energy pass-through (distributed lag, HAC, pre/post-2020); GSCPI local
  projections; a CIE-style expectations factor with a de-anchoring flag; direct forecasts (random walk,
  AR, Phillips curve, mixed-frequency with daily oil, elastic net, combination) evaluated pseudo
  out-of-sample on RMSE, MAE, log score, CRPS, PIT and Diebold-Mariano against the random walk and SPF.
- **Policy.** Taylor (1993), balanced-approach, unemployment-gap, first-difference and inertial rules;
  r\* heatmap with an explicit robustness verdict; a partial-adjustment reaction function with split
  samples and a Taylor-principle test; priced vs prescribed moves and a reverse view.
- **Financial conditions.** FCI-lite with bootstrap bands and a variable decomposition; the gap to
  conditions consistent with closing the output gap; single-variable equivalences (not forecasts);
  projected paths; comparison with NFCI and a statistical factor.
- **Curves.** Slopes, 10Y = real + breakeven and = expected rate + term premium (published models),
  regime classification, euro sovereign stress (expanding z-scores, speed), global duration factor.
- **Growth and recession.** DynamicFactorMQ nowcast with weekly news decomposition and real-time
  evaluation vs AR(1) and SPF; Growth-at-Risk with PIT backtests; recession probits with AUC, Brier,
  calibration and block-bootstrap bands; Sahm rule.
- **Transmission and positioning.** Stock-bond correlation by inflation regime; event studies around
  policy changes; real-yield betas of the S&P 500, semiconductors and AI leaders; local projections on
  a policy-surprise proxy; a differential-driven FX model; CFTC positioning with crowding flags.
- **Scenarios, fans and views.** A quarterly engine with 10,000 Monte Carlo paths per scenario,
  BoE-style two-piece-normal fans, market mapping, reverse stress test; regimes (2×2 and Markov
  switching); scorecard, priced vs model and a market-confirmation check.

## 6. Results

Figures in [`docs/figures/`](docs/figures/) are exported from live data by `scripts/export_figures.py`
(which refuses to run on synthetic data); the track record is on the dashboard's **Track record** page
and in `out/live/track_record_summary.csv`. Until the first live run, this section intentionally
contains no numbers.

## 7. Scenarios, fans and priced vs model

Scenario narratives and probabilities live in [`config/scenarios.yaml`](config/scenarios.yaml) and are
editable in the dashboard sidebar. The **Scenarios and fans** and **Regime and views** pages show
scenario-conditional and probability-weighted paths against what is priced, with uncertainty.

## 8. Limitations

Few recessions and hiking cycles (N is shown beside every statistic); r\* and the output gap are
unobservable; data revisions (latest-vintage unless ALFRED vintages are loaded); structural breaks; the
policy-surprise proxy mixes surprise and information effects; free-data constraints (no OIS curve:
2-year yields proxy the priced path; ICE history on FRED may be truncated; the broad dollar starts in
2006); subjective scenario inputs; statistical (not FRB/US) FCI weights; a smaller nowcast panel than
the NY Fed's.

## 9. How to run

```bash
make install            # pinned dependencies (Python 3.11+, tested on 3.13)
make demo               # offline, full pipeline on synthetic data (SYNTHETIC banner everywhere)
make app                # Streamlit dashboard
make test && make lint  # tests (live tests skipped) and ruff
make live               # real data (FRED_API_KEY optional: enables ALFRED vintages)
make test-live          # live smoke test of every catalogue series -> data/live_smoke.csv
make weekly monthly     # PDFs (refuse demo mode; `make demo-reports` for layout checks)
make figures            # LinkedIn exports (refuse demo mode)
```

Layout: `config/` (catalogue, assumptions, scenarios, calendar) · `src/macro/` (data layer, models,
pipeline, reports) · `app/` (dashboard) · `scripts/` · `archive/forecasts.csv` · `docs/` · `tests/`.
Unpublishable inputs (OIS-implied paths) go in `config/assumptions.yaml` with source and date; the
dashboard flags entries older than 30 days.

## 10. Governance

Model cards ([`docs/model_cards/`](docs/model_cards/)), a model changelog with a monthly code-freeze
rule enforced by the archive ([`docs/MODEL_CHANGELOG.md`](docs/MODEL_CHANGELOG.md)), and a research log
with hypotheses written before testing and every specification tried
([`docs/research_log.md`](docs/research_log.md)). Every output carries run metadata (git hash, data
vintage, timestamp). CI runs lint and tests on synthetic data at every push; a weekly workflow
refreshes live data, appends the archive and builds the reports.

## 11. Roadmap

OIS-implied policy paths; PMI-based nowcasting; SNB and BoE modules; NLP tone indices of central-bank
statements; ALFRED vintages inside the inflation forecast loop; switching fan variances to the
archive's own forecast errors once enough evaluation points exist.

## 12. Disclaimer and data-source terms

Research product, may be revised or discontinued, not an official view and not investment advice.
Derived indices (FCI-lite, the expectations factor, term-premium decompositions) are research series,
may be revised, and are not official statistics. Data remain the property of their providers: FRED
series follow their original sources' terms (ICE BofA and S&P series are copyrighted); Yahoo Finance
data are for personal, non-commercial use; ECB, CFTC, NY Fed, Fed Board and Philadelphia Fed data are
cited on every chart. No raw third-party data is committed to this repository.
