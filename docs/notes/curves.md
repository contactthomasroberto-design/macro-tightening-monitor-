# Note — curves, term premium and sovereign stress

Primary sources:
- Kim and Wright (2005), *An Arbitrage-Free Three-Factor Term Structure Model and the Recent Behavior
  of Long-Term Yields and Distant-Horizon Forward Rates*, FEDS 2005-33.
- Adrian, Crump and Moench (2013), *Pricing the Term Structure with Linear Regressions*, JFE (ACM).

**Reading status:** not downloadable from the build environment. We do not re-estimate these models:
we import the published series (THREEFYTP10 on FRED, ACM file from the NY Fed — both flagged `verify`).

## What is replicated
- The decomposition 10Y = expected average short rate + term premium, as each model defines it, and
  10Y = real yield + breakeven from TIPS-based series.
- Standard curve analytics (slopes, butterfly) and regime classification (bull/bear,
  steepener/flattener), with frequencies conditional on Fed hiking phases.

## What is simplified, and why
- No own term-structure model: published estimates are more credible and transparent for this use.
- Euro sovereign spreads use monthly long-term interest rates (ECB convergence series), not daily
  benchmark yields (not free with a long history).
- The global duration factor is a static PCA on monthly 10Y changes.

## What could break
- ACM file location/format changes (scripted download, manual fallback).
- Regime thresholds; TIPS liquidity premia contaminating breakevens (residual shown).
