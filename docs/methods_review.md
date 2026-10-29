# Methods review (October 2026): what was added, from which sources, and what was left out

This review was written before the models below were estimated. Each method is one that a central
bank, an international institution or the academic literature has published and that practitioners
use; nothing here is new or proprietary. Sources are cited as found; where only a summary or a
secondary write-up could be read from the build environment, it says so.

## 1. Recession signals from markets

| Signal | Source | Why it is added |
|---|---|---|
| 10-year minus 3-month Treasury spread | Estrella and Mishkin (1998); the New York Fed's yield-curve model | Already in the project; kept as the benchmark |
| Near-term forward spread: forward 3-month rate six quarters ahead minus the current 3-month rate | Engstrom and Sharpe, [The Near-Term Forward Yield Spread as a Leading Indicator](https://www.federalreserve.gov/econres/feds/the-near-term-forward-yield-spread-as-a-leading-indicator-a-less-distorted-mirror.htm) (Fed Board, 2018, revised 2019); [Don't Fear the Yield Curve](https://www.federalreserve.gov/econres/notes/feds-notes/dont-fear-the-yield-curve-20180628.htm) (FEDS Notes, 2018) | They find it dominates long-term spreads in recession and GDP models: it reads expected near-term easing, not term premia |
| Excess bond premium (EBP) | Gilchrist and Zakrajšek (2012, AER); Favara, Gilchrist, Lewis and Zakrajšek, [Updating the Recession Risk and the Excess Bond Premium](https://www.federalreserve.gov/econres/notes/feds-notes/updating-the-recession-risk-and-the-excess-bond-premium-20161006.html) (FEDS Notes, 2016) | Credit spread net of expected default: investor risk appetite. The Fed publishes it monthly with its own recession probability, which serves here as an external benchmark |

Follow-up work matters for interpretation: Fed Board staff (Ajello, Benzoni and co-authors; Chicago
Fed [Economic Perspectives 2022-4](https://www.chicagofed.org/publications/economic-perspectives/2022/4)
and [Chicago Fed Letter 469](https://www.chicagofed.org/publications/chicago-fed-letter/2022/469))
explain why the near-term spread signalled little recession risk in 2022 while the 10Y-3M spread
inverted. The forward rate six quarters ahead is not published free; it is approximated here by the
one-year rate one year ahead implied by the 1- and 2-year Treasury yields (stated on the page).

**Evaluation (pre-registered in the research log, H17):** pseudo-out-of-sample, expanding window,
monthly forecast origins from 1990, outcomes used only once known; AUC, Brier score and log score
against the unconditional frequency.

## 2. Conditional stress scenarios

Imposing a shock on one asset in isolation produces internally inconsistent scenarios; conditioning
the rest of the market on the shock does not (see the conditional-distribution literature on stress
testing: Novosyolov and Satchkov, [Portfolio crash testing](https://www.risk.net/journal-of-risk-model-validation/2161275/portfolio-crash-testing-making-sense-of-extreme-event-exposures),
Journal of Risk Model Validation; Glasserman, Kang and Kang, [Stress Scenario Selection by Empirical
Likelihood](https://www.financialresearch.gov/working-papers/files/OFRwp0007_GlassermanKangKang_StressScenarioSelectionbyEmpiricalLikelihood.pdf),
OFR). Method used: multivariate normal on weekly changes, E[x | s] = Σ_xs Σ_ss⁻¹ s and its
conditional covariance, with the covariance estimated on a chosen window (last two years, since
2000, or high-inflation weeks only). Known limit: under fat tails (Student-t), conditioning does not
shrink variance as much as the normal implies (the arXiv paper on [conditional
stress](https://arxiv.org/pdf/2004.06420)); the out-of-sample coverage test (H18) measures how much
this matters.

Historical episodes are replayed on the same universe (1994 bond rout, 1998 LTCM, 2008 Lehman, 2013
taper tantrum, 2015 renminbi devaluation, 2018 Q4, 2020 Covid, 2022 inflation shock, 2023 regional
banks, 2024 yen carry unwind), and the current 3-month cross-asset move is compared with each.

## 3. Cross-asset factors

Principal components of weekly cross-asset changes (MSCI's macro factor models describe rates
factors that resemble the principal components of rate changes:
[MSCI Macro Factor Model](https://www.msci.com:443/documents/1296102/11854897/MSCI_MAC_Factor_Model_Tier2_Factsheet_July+2020.pdf/b2ef0a59-d546-bd50-0947-a2d052dc924d);
Macrosynergy on [principal components for macro signals](https://macrosynergy.com/?p=54201), a
vendor's own research). Reported with explained variance, loadings, current factor scores and a
stability check (H19). The growth/inflation framing of regimes follows the four-environment logic
popularised by Bridgewater (secondary sources only; Bridgewater's site could not be reached).

## 4. Policy rules

The Fed's [Policy Rules and How Policymakers Use Them](https://www.federalreserve.gov/monetarypolicy/policy-rules-and-how-policymakers-use-them.htm)
lists the Taylor (1993), balanced-approach, adjusted, shortfalls and first-difference rules; the
project already computes the main ones. A [2025 Hoover analysis](https://hoover.org/node/367192)
(Papell) finds balanced-approach rules outperform Taylor rules in FRB/US: shown as context, not used
to weight rules.

## 5. Growth-at-Risk and scenario analysis

Growth-at-Risk follows Adrian, Boyarchenko and Giannone (2019) and the IMF's practice
([Term Structure of Growth-at-Risk](https://www.imf.org/en/publications/wp/issues/2018/08/02/the-term-structure-of-growth-at-risk-46150),
quantile regressions with a skewed-t fit; already in the project). Scenario analysis in central
banks increasingly uses structural scenarios in VARs (Antolín-Díaz, Petrella and Rubio-Ramírez,
[Structural Scenario Analysis with SVARs](https://www.bankofengland.co.uk/-/media/boe/files/events/2018/november/forecasting-at-central-banks/structural-scenario-analysis-with-svars.pdf),
JME 2021). The project's engine is a small semi-structural quarterly model; the new simulator lets
a user set the shock paths and see the distribution of outcomes, with the engine's own uncertainty.
A full SVAR scenario engine is left for later (it needs identifying restrictions that deserve their
own review).

## 6. Considered and left out

- **Trend and carry signals** (Moskowitz, Ooi and Pedersen, [Time Series Momentum](https://papers.ssrn.com/abstract=2089463),
  JFE 2012; disputed by Kim, Tse and Wald): trading signals, outside the project's rule of
  implications, not positions.
- **Proprietary nowcasts and indicator sets** (J.P. Morgan's JPMaQS, Bridgewater, Citi surprise
  indices): not free.
- **Inflation swaps, OIS curves for the ECB and the BoJ**: not free.
