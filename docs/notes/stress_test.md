# Note — cross-asset stress testing

Primary sources: conditional-normal stress testing (Novosyolov and Satchkov, Journal of Risk Model
Validation); Glasserman, Kang and Kang, OFR working paper 0007 (empirical-likelihood scenarios);
MSCI macro factor model documentation. See `docs/methods_review.md`.

**Reading status:** summaries only from the build environment.

## What is replicated
Conditional scenarios under a multivariate normal; factor analysis by principal components.

## What is simplified, and why
No fat-tailed (Student-t) or empirical-likelihood version yet: the coverage test shows the normal is
close at ±1 s.d. and slightly narrow at ±1.96 s.d.

## What could break
Correlation regime shifts; series with short histories dominate pairwise estimates in short windows.
