# Note — scenarios, Monte Carlo and fan charts

Primary sources:
- Britton, Fisher and Whitley (1998), *The Inflation Report projections: understanding the fan chart*,
  Bank of England Quarterly Bulletin.
- Wallis (1999), *Asymmetric density forecasts of inflation and the Bank of England's fan chart*.
- BCA Research (marketing page; unverified) and PIMCO (2026) for the presentation format of
  probability-weighted scenarios and "not forecasts" language.

**Reading status:** not downloadable from the build environment; the TPN algebra follows the standard
statement (mode, σ, skew γ; s1 = σ/√(1+γ), s2 = σ/√(1−γ); mean − mode = √(2/π)(s2 − s1)).

## What is replicated
- Fans whose central line is the mode, two-piece normal densities, skew from probability-weighted
  alternative scenarios (mean − mode), 10% bands up to 90%, a printed conditioning statement and a
  "how to read" box.
- Probability-weighted scenarios with editable probabilities; scenario-conditional and weighted
  terminal rates against what is priced; a reverse stress test.

## What is simplified, and why
- Variance from the dispersion of bootstrap Monte Carlo paths (historical one-step residuals) rather
  than ten years of the institution's own forecast errors (we do not have a long archive yet; the
  forecast archive will provide them over time — then switch, and log it in the changelog).
- No judgemental variance adjustment.
- Equal-tailed bands rather than the BoE's mode-including bands.
- US only; a quarterly reduced-form engine (Phillips curve + estimated reaction function), not a DSGE.

## What could break
Scenario inputs are subjective; the engine's Phillips curve is flat and unstable over time; the
reaction function is estimated with few hiking cycles; Okun-implied growth is crude.
