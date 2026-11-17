# Note — systematic portfolio

Primary sources: Black and Litterman (1992), *Global Portfolio Optimization*, FAJ; He and Litterman
(1999), *The Intuition Behind Black-Litterman Model Portfolios*; Idzorek (2005), *A Step-by-Step Guide
to the Black-Litterman Model*; Ledoit and Wolf (2004), *A Well-Conditioned Estimator for
Large-Dimensional Covariance Matrices*, JMA; Moskowitz, Ooi and Pedersen (2012), *Time Series
Momentum*, JFE; Gilchrist and Zakrajšek (2012), *Credit Spreads and Business Cycle Fluctuations*, AER;
Bailey and López de Prado (2014), *The Deflated Sharpe Ratio*, JPM; Grossman and Zhou (1993),
*Optimal Investment Strategies for Controlling Drawdowns*, MF.

**Reading status:** papers known from their published versions; formulas checked against the
standard textbook statements.

## What is replicated
Reverse optimisation and the Black-Litterman posterior; Ledoit-Wolf shrinkage (identity target, on
correlations); time-series momentum; the deflated Sharpe ratio.

## What is simplified, and why
- View confidences are fixed per family, not estimated: estimating them on the backtest would overfit.
- The drawdown control is a two-step rule, not the Grossman-Zhou continuous floor: simpler to audit.
- No currency hedging: the benchmark is unhedged USD; KRW exposure is part of the Korean positions.
- No shorting, leverage or derivatives: a balanced long-only portfolio.

## What could break
A regime where trend and macro signals are wrong together (2022-like inflation shock, 2020-like
V-shaped crash); data outages on Yahoo; a change in SEC XBRL tags.
