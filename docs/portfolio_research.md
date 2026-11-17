# Running a systematic portfolio like a hedge fund: models, evidence, and what this project uses

Written 2026-11-17 for the Portfolio menu. For each family: what it is and what the evidence says.
"Here" says whether and where the project uses it. References are listed at the end.
A rule of thumb from the literature runs through the whole note. Most published signals lose half
their strength once published (McLean and Pontiff, 2016). Most backtests are overfitted (Bailey et
al., 2017). So every addition must earn its place out of sample, after costs.

## 1. Portfolio construction (how to turn views into weights)

| Model | Idea | Evidence and caveats | Here |
|---|---|---|---|
| Mean-variance (Markowitz, 1952) | Maximise return minus risk | Error-maximising with estimated means; extreme corners | Final step only, with bounds |
| **Black-Litterman** (1992; He-Litterman, 1999; Idzorek, 2005) | Start from the benchmark's implied returns, tilt by views weighted by confidence | Not an optimiser but a better input to one; stable, explainable weights | **Core** (`portfolio.black_litterman`) |
| Minimum variance | Lowest-risk long-only mix | Strong out-of-sample risk; concentrates in bonds and cash | Comparison |
| Equal risk contribution / risk parity (Maillard, Roncalli, Teïletche, 2010; Asness, Frazzini, Pedersen, 2012) | Each asset contributes the same risk | Robust, no return forecasts; needs leverage to reach equity-like returns | Comparison |
| **Hierarchical risk parity** (López de Prado, 2016) | Cluster correlations, split risk down the tree | Lower out-of-sample variance than CLA in the author's simulations; contested by replications (ERC sometimes lower) | Comparison |
| Robust optimisation, resampling (Michaud) | Optimise against estimation error | Similar effect to shrinkage plus bounds | Not used: Ledoit-Wolf, bounds and Black-Litterman already do this |
| CVaR optimisation (Rockafellar-Uryasev, 2000) | Minimise the tail loss directly | Good for fat tails; unstable on short samples | Reported (expected shortfall), not optimised |
| Kelly / growth-optimal | Maximise log wealth | Far too aggressive with estimated edges; fractional Kelly at best | Not used |

## 2. Risk model

| Model | Evidence | Here |
|---|---|---|
| **Ledoit-Wolf shrinkage** (2004) | Better-conditioned covariance, fewer extreme weights | **Core**, on correlations |
| EWMA / GARCH volatility (RiskMetrics; Engle, 2002 DCC) | Faster reaction to volatility spikes | Candidate: shorter half-life for the volatility cap |
| Factor risk models (Barra-type) | Explain risk by common factors | Not used: 19 lines do not need one |
| Student-t / fat tails | 95% bands too narrow under normality | Stress page (H23) |

## 3. Return signals (views)

| Signal | Evidence | Here |
|---|---|---|
| **Time-series momentum** (Moskowitz, Ooi, Pedersen, 2012; Hurst, Ooi, Pedersen, "A century of trend following", 2017) | Positive across asset classes for a century; strongest in crises ("crisis alpha") | **Trend views** |
| Cross-sectional momentum (Jegadeesh-Titman, 1993) | Strong but crash-prone (Daniel-Moskowitz, 2016) | Inside the semiconductor sleeve |
| Value and carry (Asness, Moskowitz, Pedersen, 2013; Koijen et al., 2018) | Diversifying; slow | Forecast book (Governance); candidate views |
| Low volatility (Frazzini-Pedersen, 2014, betting against beta) | Robust in equities | Inside the semiconductor sleeve |
| Macro regimes: growth and inflation quadrants; excess bond premium (Gilchrist-Zakrajšek, 2012) | EBP is the best recession signal here (H17); regime timing is hard | **Macro views** |
| Business-cycle fundamentals: memory cycle | Micron reports before the Korean makers; DRAM prices lead earnings | **Micro view** (H29) |
| **News sentiment**: Tetlock (2007), Garcia (2013), Ke-Kelly-Xiu (2019), Lopez-Lira and Tang (2023) | Negative media tone predicts lower returns; news is priced within about two days (KKX); LLM headline scores predict next-day returns, more for small stocks and bad news; GDELT tone predicts index returns in several studies | **Scored and archived**; in the allocation only if H32 passes |
| Country valuation: CAPE and earnings yield across countries (Asness, Ilmanen, Maloney, "Market timing: sin a little", 2017; Klement, 2012, CAPE across countries) | Cheap markets earn more over 5-10 years; weak at 1-3 months | **Candidate `valuation`** (H48), price-deviation proxy: no free point-in-time CAPE by country |
| Positioning: speculators' net futures positions at extremes (Bessembinder and Chan, 1992; Wang, 2003; Dewally, Ederington, Fernando, 2013) | Mixed: hedgers' extremes are weakly contrarian, speculators' positions often follow trend; strongest at extremes, in currencies | **Candidate `positioning`** (H49), CFTC TFF leveraged funds, tails only |
| Earnings momentum and surprise (Bernard and Thomas, 1989, post-earnings drift; Chan, Jegadeesh, Lakonishok, 1996) | Drift after surprises is one of the most robust anomalies, weaker since 2000 in large caps | **Candidate `earnings`** (H50), revenue only (SEC filings, MU and NVDA) |
| Event risk: returns and volatility around FOMC and macro releases (Lucca and Moench, 2015, pre-FOMC drift; Savor and Wilson, 2013, announcement-day premium) | Announcement days carry a *premium*: cutting risk before them may cost return | **Candidate event de-risking** (H51), tested against that prior |

Candidate families enter `views_at` and the quant lab's signal audit but keep confidence 0 in
`config/portfolio.yaml`; each is run in its own variant at confidence 0.10, and adopted only on the
verdict rules written in the research log (H48-H51) before the first run. Note the prior against H51:
the literature finds a positive premium on announcement days, so de-risking may well lose return.

## 4. News analytics, as practitioners do it

- Weight each story by **relevance² × novelty²**, as RavenPack does. A passing mention or a repeat counts
  for little. Commercial analytics drop near-neutral stories and z-score each entity's own history.
- **Freshness**: news is absorbed within days. A monthly allocation keeps only the slow part (attention
  shifts, sector tone). The fast part needs daily or intraday trading, which a paper portfolio of ETFs
  does not do.
- **Sentiment models**: FinBERT beats finance dictionaries (Loughran-McDonald) by a wide margin.
  Large language models do better still (Lopez-Lira and Tang), but they cost money per headline and
  this project stays free. FinBERT is the best free option.
- **Here**: FinBERT scores headlines every two hours. Reuters and Bloomberg come through Google News;
  BBC, MarketWatch, CNBC, the Fed and the ECB come from their own feeds. Each holding's score uses
  relevance² × novelty² × credibility × freshness. Scores are archived when first seen (point in time),
  and an issue alert fires on an extreme score.
- **Validation**: company tone from GDELT since 2017 is tested before any weight is given (H32).

## 5. Risk control and drawdown management

| Technique | Evidence | Here |
|---|---|---|
| **Volatility targeting** (Harvey et al., 2018) | Raises Sharpe and cuts drawdowns for risk assets; little effect on bonds | **Volatility cap at the benchmark's** |
| **Drawdown control** (Grossman-Zhou, 1993; CPPI) | Bounds the loss, but can lock in losses and miss rebounds | **Two-step overlay** (8%, 15%) |
| Trend overlay | Same "crisis alpha" as trend views | Through trend views |
| Stop-losses per position (Kaminski-Lo, 2014) | Help only when returns are persistent | Not used |
| Stress tests and historical replay | Standard in risk committees | Risk page |

## 6. Avoiding self-deception

| Tool | Here |
|---|---|
| Pre-registered hypotheses | H27-H32 written before any run |
| Walk-forward, point-in-time data, publication lags | Yes; SEC data dated at the filing date; no-look-ahead test |
| **Deflated Sharpe ratio** (Bailey and López de Prado, 2014) | Yes, counting every variant and construction |
| Probability of backtest overfitting, CSCV (Bailey et al., 2017) | Candidate: needs many configurations to be meaningful |
| Ablations | Yes: overlay, trend, macro and micro removed in turn |
| Transaction costs and taxes | Yes, per line; Korean transaction tax |
| Survivorship bias | **Not removed**: the semiconductor names were chosen in 2026 |
| Paper trading before real money | Paper book from 2026-11-20, never edited |

## 7. What a hedge-fund desk has that this project does not

- Intraday data and execution, borrow for shorts, futures for cheap leverage and hedging.
- Paid data: consensus estimates and revisions, DRAM contract prices, order books, positioning by fund.
- A risk committee: here, a human must read the issues the monitor opens.

## References (selection)
- Black and Litterman (1992), FAJ; He and Litterman (1999), Goldman Sachs; Idzorek (2005).
- Ledoit and Wolf (2004), JMA. Maillard, Roncalli and Teïletche (2010), JPM. López de Prado (2016), JPM.
- Moskowitz, Ooi and Pedersen (2012), JFE; Hurst, Ooi and Pedersen (2017), JPM; Asness, Moskowitz and
  Pedersen (2013), JF; Frazzini and Pedersen (2014), JFE; Daniel and Moskowitz (2016), JFE.
- Gilchrist and Zakrajšek (2012), AER.
- Tetlock (2007), JF; Garcia (2013), JF.
- Ke, Kelly and Xiu (2019), [NBER w26186](https://www.nber.org/papers/w26186).
- Lopez-Lira and Tang (2023-2025), [arXiv 2304.07619](https://arxiv.org/abs/2304.07619).
- Araci (2019), FinBERT; [LLM sentiment trading comparison, arXiv 2412.19245](https://arxiv.org/abs/2412.19245v1).
- [RavenPack-style relevance and novelty weighting](https://docs.bigdata.com/blog/market-data/entity-sentiment-signals).
- [GDELT news sentiment and Chinese stock returns, PBFJ 2022](https://www.sciencedirect.com/science/article/abs/pii/S0927538X22001056).
- Harvey et al. (2018), [The Impact of Volatility Targeting, JPM](https://www.quantpedia.com/Blog/Details/the-impact-of-volatility-targeting-on-equities-bonds-commodities-and-currencies).
- Grossman and Zhou (1993), MF.
- Bailey and López de Prado (2014), JPM; [Bailey, Borwein, López de Prado and Zhu (2017), The
  Probability of Backtest Overfitting, JCF](https://papers.ssrn.com/abstract=2326253);
  [López de Prado, Building Diversified Portfolios that Outperform Out-of-Sample](https://papers.ssrn.com/abstract=2708678).
- McLean and Pontiff (2016), JF.
