# Note — cross-asset markets

Primary sources:
- Estrella and Mishkin (1998), *Predicting U.S. Recessions: Financial Variables as Leading
  Indicators*, Review of Economics and Statistics; Federal Reserve Bank of New York, *The Yield Curve
  as a Leading Indicator* (methodology page).
- Kliesen and Smith, *Measuring Financial Market Stress* (St. Louis Fed, STLFSI); Office of Financial
  Research, *Financial Stress Index* methodology.
- J.P. Morgan/Reuters (1996), *RiskMetrics Technical Document* (volatility scaling of moves).
- Newey and West (1987), HAC covariance.

**Reading status:** not downloadable from the build environment; methods implemented from their
standard published form, to be checked against the primary texts.

## What is replicated
- Estrella-Mishkin probit of recession 12 months ahead on the 10Y-3M spread (the NY Fed's model),
  estimated on the project's data rather than copied coefficients.
- A composite stress index in the spirit of the STLFSI and OFR FSI (standardised risk measures,
  equal weights), validated against them.

## What is simplified, and why
- Three stress components instead of the 18 (STLFSI) or 33 (OFR) of the published indices: only
  series with long free histories. The validation shows how much this costs.
- Sensitivities on weekly changes with a fixed two-year window; no regime-dependent betas.
- Regimes from a fixed 2×2 rule rather than an estimated model: transparent, no fitting.

## What could break
- FRED's three-year limit on ICE BofA series; Yahoo rate limits.
- The probit's relation weakened after 2022 (inversion without recession); it is shown, not adjusted.

## Open questions
- A free source of long OAS histories would allow a credit component closer to the OFR index.
