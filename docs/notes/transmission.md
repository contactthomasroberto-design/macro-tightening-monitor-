# Note — transmission

Primary sources and references:
- Jordà (2005) local projections; event-study practice around FOMC decisions (e.g. Kuttner 2001;
  Gürkaynak, Sack and Swanson 2005 for surprise measurement).
- Literature on the sign of the stock-bond correlation and inflation (e.g. Campbell, Sunderam and
  Viceira; practitioner notes on the ~3% inflation threshold).

**Reading status:** not downloadable from the build environment; methods are standard and stated in
full on the page and in the model card.

## What is replicated
Event study [−5, +5] around detected policy changes with bootstrap CIs and N; stock-bond correlation
by inflation regime; real-yield and breakeven betas (rolling, by regime); local projections on a
policy-surprise proxy; a differential-driven FX model.

## What is simplified, and why
- No intraday or fed-funds-futures surprise series (not free): the 1-day 2Y change on decision days is
  a proxy mixing surprise and information effects; decision days without a change are missing.
- Events come from target-rate changes, not the FOMC calendar (unscheduled moves included).
- The AI-leaders basket is an equal-weight index of five large caps over their listed history; it is
  descriptive (survivorship: chosen ex post).

## What could break
Overlapping event windows, regime-dependent betas, spurious FX levels regressions (changes shown).
