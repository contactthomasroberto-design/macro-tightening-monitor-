# BRIEF v2 — Macro Tightening Monitor (institutional grade)

This file replaces BRIEF v1. It is the instruction set for Claude Code. Read all of it before writing code. Start in plan mode, propose the architecture, wait for validation, then execute milestone by milestone (section 12).

## 0. Mission and positioning

Build an open, reproducible macro research stack on the synchronized tightening cycle of the Fed, the ECB and the Bank of Japan, modelled on how institutional research teams actually work and what they publish.

Central question: are the central banks right to tighten, how much tightening is still needed, and how does it transmit to growth, rates, credit, FX and equities?

The project must deliver three things, like a macro research desk:
1. A live dashboard (the monitor).
2. A recurring written product (weekly monitor, monthly view, occasional deep dive).
3. A transparent model archive (code, model cards, forecast archive, track record, changelog).

The author is a finance student who will publish this on LinkedIn and defend it in interviews. Every model must be explainable by him line by line. Prefer a transparent model done properly over a complex one done superficially.

Positioning rules:
- Educational research, not investment advice. Say so in README, dashboard footer and every exported document. Same wording the Fed uses for its own experimental series: research product, may be revised or discontinued, not an official view.
- No claim of alpha, edge, or track record on markets. No P&L backtests presented as strategy returns. We publish forecast accuracy of macro models, and sensitivities, never price targets.
- No market figure is hardcoded in code, README or dashboard copy. Every number comes from data with source and as-of date, or from a script that regenerates it.
- Do not copy proprietary text or code. Re-implement published methods from papers and public data, cite the source, and state what is simplified.

## 1. What institutions do, and what we copy from each

Before implementing a module, read the cited primary source and write a one-page note in `docs/notes/<module>.md`: what is replicated, what is simplified, why, and what could break. Some details below come from public summaries of these sources, so the primary text wins on any conflict.

| Institution / source | What they do | What we take from it |
|---|---|---|
| NY Fed Staff Nowcast 2.0 (technical paper, 2023) | Bayesian dynamic factor model with a handful of latent factors (global, soft, nominal, labor) and a time-varying growth trend, about 38 monthly and quarterly series. Weekly update. Each release's "news" (actual minus model prediction, weighted) is grouped by category and the category impacts sum to the weekly change. Publishes a point estimate with 50% and 68% probability bands. Evaluated by real-time reconstruction (from 2006) with squared errors at several horizons before the release. | Growth nowcast with a **news-decomposition view** ("what moved the nowcast this week"), bands, and real-time evaluation. statsmodels `DynamicFactorMQ` supports mixed frequencies and a `news` method: use it. |
| Atlanta Fed GDPNow | Aggregates 13 subcomponent forecasts via bridge equations, dynamic factor model for missing data, no subjective adjustments, code frozen during a forecasting window. Updates after each major release. Publishes subcomponent contributions, the evolution of the forecast against a survey benchmark, an archive spreadsheet with a **track record tab**, accuracy stats (mean absolute error and RMSE), and a document listing model modifications. | **Forecast archive + public track record** (we store every forecast vintage), a **model changelog**, a code-freeze rule per evaluation window, and a "contributions" chart. |
| Cleveland Fed Inflation Nowcasting (Knotek and Zaman, WP 24-06) | Parsimonious mixed-frequency model on real-time data, benchmarked against consensus surveys for **both point and density nowcasts**; more accurate than surveys for headline, competitive for core in the tested sample. | Inflation nowcast evaluated on point **and density** accuracy against a consensus benchmark (SPF), not just RMSE. |
| NY Fed r\* (Laubach-Williams, Holston-Laubach-Williams) | Estimates the natural rate and trend growth from GDP, inflation and the policy rate; versions for US, Canada, euro area; post-COVID modifications with time-varying volatility and supply-shock treatment. Publishes real-time vintage estimates, parameter estimates, replication code and charts, with explicit "not an official forecast" caveat. | r\* is **an input with a range, not a point**. Import the published HLW/LW series as external inputs (with release date), run sensitivity around them, and never present a single r\*. |
| Fed Board Kim-Wright and NY Fed ACM term premia | Arbitrage-free term-structure models that split long yields into expected short rates and a term premium (Kim-Wright is a three-factor model fit to Treasury yields; an inflation-augmented variant splits real and inflation-risk parts). | Use the published term premium series (verify FRED IDs, for example THREEFYTP10 and ACMTP10), and a decomposition page: 10Y = expected short rate + term premium, or real yield + breakeven. |
| Fed Board Index of Common Inflation Expectations (CIE) | Dynamic factor model summarizing the comovement of survey and market-based inflation expectations; experimental, revised each update. | Our **expectations-anchoring factor**: a common factor across household surveys, SPF and breakevens, with a rolling sensitivity to realized inflation. |
| NY Fed Global Supply Chain Pressure Index (Staff Report 1017) | Monitoring indicator for supply chain pressure; shown via local projections to be tied to producer-price inflation in the US and euro area. | Supply-side indicator in the inflation module, with local-projection pass-through to producer prices and core goods. |
| NY Fed "Vulnerable Growth" (Adrian, Boyarchenko, Giannone, Staff Report 794) | Quantile regressions of average future GDP growth (1 and 4 quarters) on current growth and the NFCI; fit a skewed-t distribution to the 5th, 25th, 75th, 95th quantiles; downside risk moves with financial conditions, upside is stable; recursive backtest with predictive scores and PITs. IMF later extended to the term structure of Growth-at-Risk. | **Growth-at-Risk module**: conditional growth distribution, expected shortfall, backtested calibration. Complements the recession probit. |
| Fed Board FCI-G | Financial-conditions index built from seven variables (policy rate, 10Y yield, 30Y mortgage rate, BBB yield, equities, house prices, broad dollar), each weighted by its estimated effect on next-year GDP growth from a structural model, using 3-month changes over a 1 or 3 year window. Positive = headwind. Contrasted by the Fed with statistical indices (Chicago NFCI, Bloomberg FCI) and macro-model indices (Goldman Sachs FCI) that ignore lags. | **Financial-conditions module**: an FCI-style impulse on growth, decomposed by variable. Use the published FCI-G data if downloadable; otherwise build "FCI-lite" with growth sensitivities estimated by us and label it clearly as not the Fed's index. |
| PIMCO, "Monetary policy through the lens of financial conditions" (2026) | Practitioner use of FCI-G: compare current conditions with the level consistent with closing the output gap, then translate the gap into **equivalents** (a rise in the 10Y yield, an equity decline, a dollar appreciation, or a combination), explicitly "not forecasts", with risk caveats. Three charts: decomposition, current vs target, projected path on forward-curve scenarios. | The format of our **"how much tightening is left"** page: gap to neutral financial conditions, equivalence table with uncertainty, projected path on scenarios. |
| Bank of England fan chart | Central projection is the **mode**; two-piece normal distribution with a skew parameter; variance calibrated on roughly the previous ten years of forecast errors then adjusted by judgment; skew from probability-weighted alternative assumptions (mean minus mode); bands of 10% each up to 90%; explicit conditioning (for example, unchanged policy rate). | Our **fan chart engine**: two-piece normal fans on policy rate, inflation and growth, with a printed conditioning statement and a "how to read it" box (the fan is not the full range). |
| CFTC Traders in Financial Futures (via OFR Hedge Fund Monitor) | Weekly (Tuesday) positions of Dealers, Asset Managers, Leveraged Funds (typically hedge funds and money managers) and Others in Treasury, short-rate, equity-index and currency futures; OFR publishes notional and duration-adjusted 10-year-equivalent measures. | **Positioning module**: leveraged-fund positioning in rates, equity and FX futures, duration-adjusted, with percentile ranks to flag crowded positions. |
| Philadelphia Fed Real-Time Data Set and Survey of Professional Forecasters | Vintage-accurate macro data and a consensus forecast archive used as the standard benchmark. | The **benchmark and evaluation data** for inflation and growth forecasts. |
| Macro hedge-fund workflow (River and Mercantile description in Risk.net; sponsored content, treat claims as unverified) | Layered process: a macro view; models size positions; discretionary oversight checks that model output reconciles with the view; a **market-motion check** (do prices confirm the thesis); valuation as a long-term vulnerability signal, credit and price motion as shorter-term; regime determines trend persistence. | Our **view layer**: macro view, evidence, "priced vs model" gap, and a market-confirmation check. No position sizing, no P&L. |
| BCA Research (marketing page; treat claims as unverified) | Executive summaries, trade ideas, regime-based analysis, probability-weighted scenarios, annual outlook written as a retrospective from the future. | Deliverable formats: executive summary, probability-weighted scenarios, regime view. We write **implications and sensitivities, not trade recommendations**. |
| OpenBB (open-source research platform), pandas-datareader, fredapi | Open data connectors and dashboards. | Optional inspiration for connectors. Prefer direct, documented sources in this repo for transparency and testability. |

## 2. How institutions work, as rules for this repo

1. **Real-time evaluation.** Evaluate forecasts on data as it was published (vintages), not revised history. Use ALFRED/FRED vintages (env `FRED_API_KEY`, optional) and the Philadelphia Fed real-time data and SPF files. Without vintages, label results "latest-vintage, not point-in-time".
2. **Publication lags.** Each series carries its release lag in `config/series.yaml`. Features at date t use only data published by t.
3. **News decomposition.** Whenever a nowcast changes, show which release moved it and by how much.
4. **Benchmark everything.** Random walk, AR, and consensus (SPF) benchmarks. Report RMSE and MAE, density scores (log score or CRPS) and PIT calibration for density forecasts, and Diebold-Mariano tests. If a model does not beat the benchmark, say so on its page.
5. **Archive and track record.** Every scheduled run stores the forecast with its vintage date in `archive/forecasts.csv`. The dashboard has a "Track record" page built from that archive, comparing each forecast with the later outcome. This is the institutional habit (GDPNow publishes an archive and track record) and the best credibility signal on LinkedIn.
6. **Model governance.** One model card per model (`docs/model_cards/`): purpose, inputs, equations, estimation sample, assumptions, validation results, known failure modes, version, last review date. A `docs/MODEL_CHANGELOG.md` records every change to a model, with the reason. Code for a forecast is frozen within an evaluation window (for example a calendar month); changes ship in the next window and are logged. Inspired by model-risk-management practice (for example the Fed's SR 11-7 guidance).
7. **Research log and multiple testing.** Keep `docs/research_log.md`: hypotheses written before testing, specifications tried, and results including failures. State in each page how many specifications were tried. Define evaluation metrics and sample splits before looking at results.
8. **Uncertainty everywhere.** Bands on every estimate and forecast: HAC errors, bootstrap, block bootstrap; fans for forecasts. Never a bare point estimate.
9. **Small samples stated.** Few recessions and hiking cycles; show N beside every event-study and recession statistic.
10. **Experimental-product disclaimers.** Every derived index (CIE-style factor, FCI-lite, term-premium decompositions) carries "research series, may be revised, not an official statistic".
11. **Reproducibility.** Fixed seeds, pinned dependencies, deterministic pipeline, run metadata (git hash, data vintage, timestamp) logged with every output.
12. **Data licensing.** Check redistribution terms and history limits for third-party series (for example credit indices on FRED, Yahoo-derived data). Do not commit raw third-party data; commit only small derived archives; cite sources on every chart.

## 3. Stack and repository layout

Python 3.11+, pandas, numpy, statsmodels (`DynamicFactorMQ`, `QuantReg`, `MarkovRegression`, probit/logit, OLS with HAC), scikit-learn, scipy, plotly, streamlit, SQLite, requests, PyYAML, pydantic, pytest, hypothesis (optional), ruff, mypy (lenient), kaleido, fpdf2 or WeasyPrint for PDFs.

```
macro-tightening-monitor/
  README.md  BRIEF.md  pyproject.toml  requirements.txt (pinned)  Makefile  Dockerfile
  .github/workflows/ ci.yml (lint + tests, demo data)  refresh.yml (scheduled live refresh + reports)
  .streamlit/config.toml
  config/ series.yaml  assumptions.yaml  scenarios.yaml  calendar.yaml
  src/macro/
    data/ sources (fred, alfred, ecb, yahoo, cftc, nyfed_files, fed_board_files), store (SQLite), vintages, health, demo
    inflation.py  policy.py  fincond.py  curves.py  growth.py  recession.py
    transmission.py  positioning.py  scenarios.py  fans.py  regimes.py  views.py
    archive.py (forecast archive and track record)  plotting.py  reports.py  utils.py
  app/ streamlit_app.py  pages/  components.py
  scripts/ update_data.py  run_all.py  weekly_monitor.py  monthly_view.py  export_figures.py  evaluate_archive.py
  archive/ forecasts.csv  (small, committed)
  docs/ methodology.md (LaTeX)  data_catalogue.md  model_cards/  notes/  research_log.md  MODEL_CHANGELOG.md  figures/  reports/
  tests/ per module + data layer + fixtures + app smoke tests
```

## 4. Data layer

One interface `get_series(id, vintage=None)` over pluggable sources, cached in SQLite (series_id, date, value, vintage_date, source, fetched_at), TTL by frequency, retries with backoff, graceful degradation (use last cache and show its age).

`MACRO_MODE=demo` switches to a synthetic generator (coherent simulator: energy shock, Phillips-type inflation, rule-based policy, yields from expected rates plus term premium, regime-dependent returns). Demo mode puts a permanent "SYNTHETIC DATA" banner on the UI and on every exported figure, and the export scripts refuse to run in it. It exists for tests, CI and offline use.

Catalogue (starting point). **Verify every ID at runtime** with a live smoke test (marker `live`, skipped in CI) checking existence, units, last observation date and staleness. Document and replace any stale or discontinued series.

- US (FRED; API with vintages if key set, else csv endpoint): DFF, DFEDTARU, CPIAUCSL, CPILFESL, PCEPI, PCEPILFE, Cleveland Fed median and trimmed-mean CPI, Atlanta Fed sticky CPI, CPI services and core goods, T10YIE, T5YIFR, MICH, DFII10, UNRATE, NROU, PAYEMS, ICSA, GDPC1, GDPPOT, DGS3MO, DGS2, DGS5, DGS10, DGS30, T10Y2Y, T10Y3M, THREEFYTP10, ACMTP10, BAMLH0A0HYM2, BAMLC0A0CM, NFCI, STLFSI4, VIXCLS, DTWEXBGS, USREC, MORTGAGE30US, BBB yield (verify).
- Euro area (ECB data portal csv, FRED or Eurostat fallback): deposit facility rate, HICP headline, core, energy, services, non-energy industrial goods, AAA yield curve spot rates, sovereign 10Y for DE, FR, IT, ES, unemployment, EUROREC, ECB SPF.
- Japan: policy rate, CPI, JGB 10Y (verify freshness; use BoJ or e-Stat if FRED/OECD series are stale).
- Markets (yfinance, personal-use terms, label accordingly): ^GSPC, ^STOXX50E, ^N225, ^SOX, ^VIX, ^MOVE, EURUSD=X, USDJPY=X, DX-Y.NYB, BZ=F, GC=F.
- Published research series (manual or scripted download, files from the issuing institution, with release date stored): HLW/LW r\*, Fed Board CIE, FCI-G, NY Fed GSCPI, Philadelphia Fed SPF and Real-Time Data Set.
- Positioning: CFTC Traders in Financial Futures (public reporting site) and the OFR Hedge Fund Monitor dataset. Tuesday positions, published with a lag of a few days (verify).
- `config/assumptions.yaml`: inputs that cannot be sourced for free (OIS-implied terminal rates, consensus policy paths): value, source, as-of date; dashboard flags any entry older than 30 days.
- `config/calendar.yaml`: next CPI, employment, GDP, FOMC, ECB and BoJ dates from official calendars (source and retrieval date stored). Used by the calendar page and by nowcast update logic.

## 5. Models — specification

### 5.1 Inflation (`inflation.py`)
- Decomposition: headline, core, energy, food, services, goods; 3m and 6m annualised; trimmed-mean, median and sticky measures; broadening indicator (share of components above target).
- Persistence: AR(p) by BIC, half-life, rolling to expose de-anchoring.
- Energy pass-through: distributed-lag of headline-minus-core on local-currency oil (lags 0-6), cumulative effect with HAC errors; stability across pre-2020 and post-2020 samples.
- Supply side: GSCPI local projections on producer prices and core goods (US and euro area).
- Expectations factor (CIE-style): dynamic factor across household surveys, SPF and breakevens; rolling sensitivity of long-run expectations to realized inflation; de-anchoring flag.
- Nowcast and forecast: horizons 1 to 12 months. Candidates: random walk, AR, Phillips curve (unemployment gap, energy, expectations), parsimonious mixed-frequency model with daily energy prices inside the month, elastic net, equal-weight combination. Evaluate pseudo out-of-sample on vintages: RMSE, MAE, log score and PIT against SPF consensus and the random walk, Diebold-Mariano. Fan chart for the headline path. Output: probability that inflation exceeds target by a stated margin in 12 months.
- Regions: US and euro area; Japan if data quality allows.

### 5.2 Policy (`policy.py`)
- Rule family: Taylor 1993, unemployment-gap variant, balanced approach, first-difference, inertial with smoothing. All parameters in `assumptions.yaml`, editable in the dashboard.
- r\*: external input from published HLW/LW (with release date) plus a user range. Heatmap of the prescribed rate over (r\*, inflation coefficient). The headline conclusion must hold across the range, or the page says it does not.
- Estimated reaction function: `i_t = rho*i_{t-1} + (1-rho)*(a + b*pi_t + c*gap_t) + e_t`, HAC errors, split samples, rolling coefficients; check the Taylor principle (b > 1).
- Policy gap and "behind the curve" indicator; real policy rate vs r\*; prescribed vs priced number of moves (priced from `assumptions.yaml` plus 2Y-yield proxy); reverse view (which inflation and unemployment path justifies current pricing).
- Cross-bank synchronization measure, rate differentials vs EURUSD and USDJPY with bands.
- Optional extension: simple lexicon-based hawkish/dovish tone index on FOMC and ECB statements, shown as context only.

### 5.3 Financial conditions (`fincond.py`) — "how much tightening is left"
- Fed FCI-G data if downloadable; otherwise FCI-lite: seven variables (policy rate, 10Y, mortgage rate, BBB yield, equities, house prices, dollar) with growth sensitivities estimated by us (local projections or regressions of next-year growth on 3-month changes), 1y and 3y lookbacks, decomposition by variable, sign convention positive = headwind. State clearly which version is shown.
- Gap to the financial-conditions level consistent with closing the output gap (method from the practitioner note; assumptions explicit and editable).
- Equivalence table with uncertainty: the gap expressed as a change in the 10Y yield, in equities, in the dollar, or a combination. Labeled "not forecasts".
- Projected FCI path under scenario paths for the policy rate and yields.
- Comparison with NFCI and a simple statistical-factor index, to show how conclusions depend on the index choice.

### 5.4 Curves, term premium, sovereign stress (`curves.py`)
- US curve: 3m10y, 2s10s, 5s30s, butterflies; 10Y = real yield + breakeven; published term premia (Kim-Wright, ACM) and the expected-short-rate component.
- Curve regime classification (bull or bear steepener or flattener) with history and frequencies.
- Euro: Bund 2Y and 10Y, OAT-Bund, BTP-Bund, Bonos-Bund; expanding-window z-scores and percentiles; stress flag on level and speed.
- Global duration factor: PCA on changes in 10Y yields (US, DE, JP, FR, IT); explained share of PC1, rolling.
- Japan: yield level and changes; any policy-band reference comes from `assumptions.yaml` with source and date.

### 5.5 Growth and recession risk (`growth.py`, `recession.py`)
- Growth nowcast: mixed-frequency dynamic factor model (statsmodels `DynamicFactorMQ`) on a small, documented panel (labor, surveys, production, consumption, trade, prices), with the **news decomposition** by release category and 50% and 68% bands. Benchmark against SPF and a simple AR. Evaluate on real-time vintages where available.
- Growth-at-Risk (Adrian, Boyarchenko, Giannone): quantile regressions of average growth over the next 1 and 4 quarters on current growth and NFCI; fit a skewed distribution to the 5th, 25th, 75th and 95th quantiles; report expected shortfall; recursive backtest with predictive scores and PIT histograms. Document the approximation if using a different skewed-t implementation.
- Recession probit: 12-month-ahead probability on the 3m10y spread, extended with credit spread, 6-month change in unemployment, NFCI; regularised logit as robustness; Sahm-rule indicator; expanding-window ROC AUC, Brier score, calibration plot; block-bootstrap band on the current probability; state the number of recession episodes.
- Euro-area version if data allow.

### 5.6 Transmission (`transmission.py`)
- Stock-bond correlation by inflation regime with bootstrap bands.
- Event study around detected policy changes (windows [-5, +5]) for 2Y, 10Y, S&P 500, Euro Stoxx 50, USD, SOX; bootstrap CIs; N shown.
- Real-yield sensitivity: returns on changes in real yields and breakevens, rolling betas, by regime, HAC errors; how duration-like are semiconductors and AI leaders versus the broad index.
- Local projections of responses over 0-20 days to a policy-surprise proxy (change in 2Y yield on policy dates), labeled as a proxy.
- FX: differential-driven model for EURUSD and USDJPY.

### 5.7 Positioning (`positioning.py`)
- Leveraged-fund and asset-manager net positions in Treasury, short-rate, equity-index and FX futures, duration-adjusted to 10-year equivalents where the source provides it; percentile ranks over a rolling window; crowding flags; change over 4 weeks.
- Joined with the view layer: does positioning already reflect the macro thesis? Always labeled with the Tuesday reference date and the publication lag.

### 5.8 Scenarios and fans (`scenarios.py`, `fans.py`)
- Four scenarios in `scenarios.yaml` (disinflation, sticky inflation or stagflation, energy shock, hard landing) with editable probabilities summing to 1.
- Quarterly engine over 8 quarters: inflation from estimated persistence and pass-through, unemployment from the scenario, policy from the estimated reaction function with a maximum step per meeting.
- Monte Carlo (10,000 paths, residual bootstrap): probability of at least k more moves, recession probability, scenario-conditional and probability-weighted terminal rates versus priced.
- Fan chart engine (BoE-style): mode as central path, two-piece normal with skew from probability-weighted scenarios, variance from past forecast errors, bands of 10% up to 90%, printed conditioning statement and a "how to read" note.
- Market mapping: yields via estimated betas to the policy path; equities and USD via estimated real-yield betas, with bands; reverse stress test for current pricing.

### 5.9 Regime and view layer (`regimes.py`, `views.py`)
- Regime classification: growth and inflation state (two-by-two) from nowcasts and trends, plus a Markov-switching model on inflation or the stock-bond correlation (statsmodels `MarkovRegression`) as a cross-check. Show current regime probabilities and the regime history.
- Priced-vs-model scorecard per central bank and asset class: what the market prices (assumptions plus yield proxies) against what the estimated models imply, with uncertainty.
- Market-confirmation check: do 2Y yields, breakevens, USD, credit spreads and equities move consistently with the stated macro view? Flag divergences.
- View template for the written notes: view, evidence, what is priced, what would change the view, risks, catalysts from the calendar, implications and sensitivities (not recommendations).

## 6. Deliverables (what the project ships, with cadence)

1. **Dashboard** (live): pages in section 7.
2. **Weekly Monitor** (2 pages, PDF, `scripts/weekly_monitor.py`): scorecard, what changed this week (news decomposition of nowcasts, rate moves), calendar for next week, positioning snapshot, one chart that matters.
3. **Monthly Macro View** (4 to 6 pages, PDF): regime, fan charts, scenarios with probabilities, priced vs model, financial-conditions gap, risks, limitations box, model-change log for the month.
4. **Deep dive** (6 to 10 pages, one per quarter, written as a research note): for example "Are the central banks behind the curve? A reaction-function approach".
5. **Model archive**: `archive/forecasts.csv`, track record page, model cards, changelog, research log.
6. **LinkedIn package**: see section 11.

## 7. Dashboard (`app/`)

Streamlit multi-page, English UI.
- Header: LIVE or DEMO badge, as-of date per source, run metadata, "not investment advice".
- Overview: scorecard per central bank (inflation vs target, policy gap, financial-conditions gap, curve regime, recession and growth-at-risk, sovereign stress, positioning), generated commentary from current numbers, "what changed since last week".
- Pages: Calendar and news, Inflation, Policy, Financial conditions, Curves and term premium, Growth and recession risk, Transmission, Positioning, Scenarios and fans, Regime and views, Track record, Data health, Model cards.
- Sidebar: date range, r\* range, rule parameters, scenario probabilities, region. Cache heavy computations.
- Every chart: title that states the finding, source and as-of line, recession shading, policy-date annotations, hover, CSV download, table view.
- Design: fixed entity colors across the whole app (Fed blue `#2a78d6`, ECB orange `#eb6834`, BoJ aqua `#1baf7a`; further series in fixed order violet `#6250d6`, magenta `#e87ba4`, yellow `#eda100`, green `#008300`, red `#e34948`); about 2px lines; no dual axes (small multiples or indexing); legend always shown for two or more series; recessive grid; light and dark themes; reserved status colors (good `#0ca30c`, warning `#fab219`, serious `#ec835a`, critical `#d03b3b`) always with icon and label; fan charts in one hue with lightness steps.
- First load under 5 seconds from cache.

## 8. Engineering quality

- Type hints; every model function documents the formula it implements.
- Tests: recover planted parameters from simulated data for each estimator; mocked HTTP for data sources; regression tests on demo outputs; `streamlit.testing.v1.AppTest` smoke test per page; property tests for fan chart and quantile code (monotone quantiles, probabilities sum to 1).
- `make demo` (offline, full pipeline), `make live`, `make test`, `make lint`, `make weekly`, `make monthly`, `make figures`.
- CI: ruff and pytest on demo data at each push. `refresh.yml`: scheduled job (weekly) runs live refresh, appends the forecast archive, builds reports as workflow artifacts, never exposes secrets (FRED key via GitHub secret).
- Logging, no silent exception handling, visible banner when a source is down.
- `.gitignore` for caches and raw downloads. Conventional Commits, one commit per sub-step.

## 9. README (research-note style)

1. Executive summary (generated from current data)
2. Question and thesis
3. What this project replicates and from whom (table from section 1, with links)
4. Data, vintages and publication lags
5. Methods (one paragraph per module, equations in `docs/methodology.md`)
6. Results with exported figures and the track-record snapshot
7. Scenarios, fans, and priced-vs-model
8. Limitations: few recession and hiking episodes, r\* uncertainty, data revisions, structural breaks, policy-surprise proxy, free-data constraints, no OIS curve, subjective scenario inputs
9. How to run (demo, live, optional keys), layout, tests
10. Governance: model cards, changelog, research log
11. Roadmap (OIS-implied paths, PMI nowcasting, SNB and BoE modules, NLP of central-bank statements)
12. Disclaimer and data-source terms

## 10. Definition of done

- `make demo` runs offline end to end, CI green.
- `make live` populates every page with real data; the live smoke test passes for all series; each stale series is documented and replaced.
- Every model page shows the estimate, uncertainty, benchmark comparison or robustness evidence, and limitations.
- The forecast archive records each run; the track-record page works once at least two evaluation points exist.
- Each model has a card, each change is in the changelog, the research log lists tested specifications.
- No hardcoded market numbers; every figure has source and as-of date.
- The author can explain every equation, assumption and chart in an interview.

## 11. LinkedIn plan

- Exports (`scripts/export_figures.py`): PNG at 1200x627 and carousel PDF; title states the finding; footer with source, as-of date and repo link. Refuses to export in demo mode.
- One post per milestone, each finding-first: chart, one-sentence result, method in two lines, limitation in one line, repo link. Suggested series: (1) are the central banks behind the curve (policy module), (2) how much tightening is left (financial conditions), (3) growth-at-risk and recession odds, (4) term premium and sovereign spreads, (5) scenario fans and priced-vs-model, (6) the track record after a few months.
- Never present a number without its date and source; never use language of recommendation ("buy", "sell", "overweight"). Use "implies", "is consistent with", "sensitivity".
- Text of each post is written only after real results exist, from the generated numbers.

## 12. Milestones (commit after each, run tests, report verification status)

- M0: scaffolding, config files, CI, theme, demo banner, governance templates (model card, changelog, research log)
- M1: data layer (sources, SQLite, vintages, health checks, demo generator), live smoke test, calendar
- M2: inflation module and page, forecast archive, expectations factor
- M3: policy module and page (rules, reaction function, r\* inputs and sensitivity)
- M4: financial conditions module and page (FCI-G or FCI-lite, equivalence table)
- M5: curves, term premium, sovereign stress. **First publishable checkpoint**: LinkedIn posts 1 and 2 can go out after M3 and M4
- M6: growth nowcast with news decomposition, Growth-at-Risk, recession probit
- M7: transmission and positioning
- M8: scenarios, Monte Carlo, fan charts, regime and view layer, scorecard
- M9: weekly monitor, monthly view, scheduled refresh workflow, track-record page
- M10: README, methodology, model cards, final review against section 10

At the end of each milestone, state what was verified against live data, what ran only on demo data, and what remains unverified.

## 13. Primary sources to read first

- NY Fed Staff Nowcast 2.0 technical paper: https://newyorkfed.org/medialibrary/media/research/blog/2023/NYFed-Staff-Nowcast_technical-paper
- Atlanta Fed GDPNow: https://www.atlantafed.org/research-and-data/data/gdpnow
- Cleveland Fed WP 24-06, Nowcasting Inflation (Knotek and Zaman): https://www.clevelandfed.org/publications/working-paper/2024/wp-2406-nowcasting-inflation
- NY Fed r\* (LW and HLW): https://www.newyorkfed.org/research/policy/rstar
- Kim and Wright, three-factor arbitrage-free model (Fed Board): https://www.federalreserve.gov/econres/feds/an-arbitrage-free-three-factor-term-structure-model-and-the-recent-behavior-of-long-term-yields-and-distant-horizon-forward.htm
- Fed Board, Index of Common Inflation Expectations: https://www.federalreserve.gov/econres/notes/feds-notes/research-data-series-index-of-common-inflation-expectations-20210305.htm
- NY Fed Staff Report 1017, Global Supply Chain Pressure Index: https://www.fedinprint.org/item/fednsr/94243
- NY Fed Staff Report 794, Vulnerable Growth: https://www.newyorkfed.org/research/staff_reports/sr794.pdf
- IMF WP 18/180, The Term Structure of Growth-at-Risk: https://www.imf.org/en/publications/wp/issues/2018/08/02/the-term-structure-of-growth-at-risk-46150
- Fed Board, A New Index to Measure US Financial Conditions (FCI-G): https://www.federalreserve.gov/econres/notes/feds-notes/a-new-index-to-measure-us-financial-conditions-20230630.html
- PIMCO, Monetary policy through the lens of financial conditions: https://www.pimco.com/ch/en/insights/monetary-policy-through-the-lens-of-financial-conditions
- Bank of England, understanding the fan chart (Quarterly Bulletin, 1998): https://www.bankofengland.co.uk/-/media/boe/files/quarterly-bulletin/1998/the-inflation-report-projections-understanding-the-fan-chart
- OFR Hedge Fund Monitor, CFTC TFF dataset: https://financialresearch.gov/hedge-fund-monitor/datasets/tff
- Philadelphia Fed Real-Time Center (Real-Time Data Set, SPF): https://www.philadelphiafed.org/research-and-data/real-time-center/survey-of-professional-forecasters/historical-data/mean-forecasts
- Risk.net, global macro views combine with quantitative models (sponsored content): https://www.risk.net/asset-management/hedge-funds/7530341/global-macro-views-combine-with-quantitative-models-to-produce-consistent-returns
