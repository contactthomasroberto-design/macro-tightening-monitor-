# Note — historical tightening cycles (Global Macro Database)

Primary source:
- Müller, K., Xu, C., Lehbib, M. and Chen, Z. (2025), *The Global Macro Database: A New International
  Macroeconomic Dataset*, NBER Working Paper 33714; data and documentation at www.globalmacrodata.com.

**Reading status:** data documentation and licence page read on 2026-10-28; working paper not re-read.

## What is replicated
Nothing from a specific paper: a transparent base-rate exercise in the spirit of the "soft landing"
literature, made possible by the GMD's long, harmonised cross-country coverage.

## What is simplified, and why
Annual frequency (the GMD is annual); a rule-based cycle definition instead of judgement-based
dating; no conditioning on the source of the shock. The page reports base rates, not forecasts.

## What could break
The share depends on the thresholds (1pp, 0.5pp, two years) and on the pooled sample; projection years
in a new release would leak into the outcomes if `last_actual_year` were bypassed; the licence limits
use to academic work unless the authors grant permission.
