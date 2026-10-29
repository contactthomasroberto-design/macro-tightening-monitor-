# Note — recession signals from markets

Primary sources: Engstrom and Sharpe (2018/2019), *The Near-Term Forward Yield Spread as a Leading
Indicator*, Fed Board FEDS; Favara, Gilchrist, Lewis and Zakrajšek (2016), *Updating the Recession
Risk and the Excess Bond Premium*, FEDS Notes; Gilchrist and Zakrajšek (2012), AER; Estrella and
Mishkin (1998). See `docs/methods_review.md` for links.

**Reading status:** abstracts and Fed pages read through search summaries; full texts to be checked.

## What is replicated
The probit setup and the target (recession within 12 months) of the Fed Board's EBP model; the
spread models of Estrella-Mishkin and Engstrom-Sharpe.

## What is simplified, and why
The six-quarter forward rate is proxied by the 1-year rate 1 year ahead (no free forward curve).

## What could break
The Fed's CSV location; revisions to the EBP history; a recession call by the NBER changes every score.
