# Note — policy module

Primary sources:
- Taylor (1993), *Discretion versus policy rules in practice*, Carnegie-Rochester Conference Series 39.
- Yellen (2012), *Perspectives on Monetary Policy* (speech; "balanced approach" rule).
- Orphanides (2003), *Historical monetary policy analysis and the Taylor rule*, JME (first-difference rules).
- Clarida, Galí and Gertler (2000), *Monetary policy rules and macroeconomic stability*, QJE.
- Laubach and Williams (2003); Holston, Laubach and Williams (2017, 2023 update), NY Fed r* page.
- Federal Reserve, *Monetary Policy Report*, policy-rules box (rule set and conventions).

**Reading status:** not downloadable from the build environment; this note follows the standard
textbook statements of these rules. Check the Monetary Policy Report box and the NY Fed r* page
(post-COVID HLW modifications) before publication.

## What is replicated
- The rule family used in the Fed's Monetary Policy Report: Taylor (1993), balanced approach,
  first-difference, inertial, plus an unemployment-gap variant via Okun's law.
- r* as an external, published input (HLW/LW) with its release date, never a single number: a
  user range drives a heatmap over (r*, inflation coefficient) and the page states whether the
  conclusion holds across it.
- A CGG-style partial-adjustment reaction function with split samples, rolling estimates and a
  one-sided Taylor-principle test.

## What is simplified, and why
- Real-time output gaps are not used; CBO potential is latest-vintage (revised history).
- The euro-area gap is an Okun proxy from unemployment; Japan has no gap series in free data.
- The priced path is the 2-year yield unless a dated OIS value is entered in assumptions.yaml.
- Contemporaneous (not forecast-based) inflation in the reaction function; endogeneity is not
  addressed with IV/GMM (CGG use GMM with expected inflation). Stated as a limitation.

## What could break
- Lower-bound periods bias estimates (excluded by default, N shown).
- r* revisions can flip "behind the curve" verdicts — hence the robustness check.
- Inflation measure choice (core PCE vs CPI) shifts prescriptions by tenths of a point.
