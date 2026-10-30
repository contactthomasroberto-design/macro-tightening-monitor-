# Note — forecast book

Primary sources: Moskowitz, Ooi and Pedersen (2012), *Time Series Momentum*, JFE; Asness, Moskowitz
and Pedersen (2013), *Value and Momentum Everywhere*, JF; Koijen, Moskowitz, Pedersen and Vrugt
(2018), *Carry*, JFE.

**Reading status:** abstracts and summaries; the published implementations differ (portfolios,
volatility scaling); here the signals feed a probability of direction per variable.

## What is replicated
The three signal families and their standard look-backs.

## What is simplified, and why
No volatility scaling or portfolio construction: the book scores forecasts, it does not trade.
Carry uses free proxies (term spreads, rate differentials); no commodity roll yield.

## What could break
Regime shifts in signal efficacy (momentum crashes); data outages.
