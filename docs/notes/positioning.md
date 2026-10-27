# Note — positioning

Primary sources: CFTC Traders in Financial Futures (public reporting site, futures-only); OFR Hedge Fund
Monitor TFF dataset (duration-adjusted 10-year equivalents).

**Reading status:** not downloadable from the build environment. The Socrata dataset id and field
names used by the source adapter (`gpe5-46if`, `lev_money_positions_long_all`, ...) are flagged
`verify` and must be confirmed by the live smoke test.

## What is replicated
Net positions of leveraged funds and asset managers in Treasury, SOFR, equity-index and FX futures;
Tuesday reference date and publication lag shown; percentile ranks and crowding flags; 4-week changes.

## What is simplified, and why
Duration adjustment with approximate per-contract DV01 ratios (OFR's exact series preferred when
loaded); equity/FX notional at same-date prices.

## What could break
Contract renamings at the CFTC (the adapter matches a name substring and keeps the most frequent exact
name); basis-trade dominated Treasury positioning is not a directional view.
