# Note — regimes and the view layer

Primary sources:
- Hamilton (1989), *A New Approach to the Economic Analysis of Nonstationary Time Series and the
  Business Cycle*, Econometrica (Markov switching); statsmodels `MarkovRegression` documentation.
- Risk.net sponsored article on macro-fund process (unverified claims): macro view, discretionary
  check, market-motion confirmation, valuation vs shorter-term signals.

**Reading status:** not downloadable from the build environment.

## What is replicated
- A growth × inflation two-by-two regime and a Markov-switching cross-check on inflation.
- The "market-motion check": do 2Y yields, breakevens, the dollar, credit spreads and equities move
  consistently with the model view? Divergences are flagged.
- A priced-vs-model scorecard and a structured view (view, evidence, priced, what changes it, risks,
  catalysts, implications) — with a language guard rejecting recommendation words.

## What is simplified, and why
No position sizing, no P&L, no trade ideas (brief positioning rules). Regime thresholds fixed a priori.

## What could break
Regime boundaries are knife-edge near the thresholds; Markov estimates depend on start values (seeded).
