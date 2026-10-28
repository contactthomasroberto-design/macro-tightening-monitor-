# Data catalogue

Generated from `config/series.yaml` by `scripts/update_data.py --catalogue`. Do not edit by hand.

Release lag = days between the end of the reference period and first publication (approximate).
`verify` = ID, units or freshness to be confirmed by the live smoke test (`make test-live`).

| id | region | freq | source | source id | units | lag (d) | verify | description | terms |
|---|---|---|---|---|---|---|---|---|---|
| `DFF` | US | D | fred | `DFF` | percent | 1 |  | Effective federal funds rate | FRED; public domain unless noted by the original source |
| `DFEDTARU` | US | D | fred | `DFEDTARU` | percent | 0 |  | Fed funds target range upper limit | FRED; public domain unless noted by the original source |
| `DGS3MO` | US | D | fred | `DGS3MO` | percent | 1 |  | 3-month Treasury constant maturity | FRED; public domain unless noted by the original source |
| `DGS2` | US | D | fred | `DGS2` | percent | 1 |  | 2-year Treasury constant maturity | FRED; public domain unless noted by the original source |
| `DGS5` | US | D | fred | `DGS5` | percent | 1 |  | 5-year Treasury constant maturity | FRED; public domain unless noted by the original source |
| `DGS10` | US | D | fred | `DGS10` | percent | 1 |  | 10-year Treasury constant maturity | FRED; public domain unless noted by the original source |
| `DGS30` | US | D | fred | `DGS30` | percent | 1 |  | 30-year Treasury constant maturity | FRED; public domain unless noted by the original source |
| `T10Y2Y` | US | D | fred | `T10Y2Y` | percentage points | 1 |  | 10Y minus 2Y Treasury spread | FRED; public domain unless noted by the original source |
| `T10Y3M` | US | D | fred | `T10Y3M` | percentage points | 1 |  | 10Y minus 3M Treasury spread | FRED; public domain unless noted by the original source |
| `DFII10` | US | D | fred | `DFII10` | percent | 1 |  | 10-year TIPS real yield | FRED; public domain unless noted by the original source |
| `T10YIE` | US | D | fred | `T10YIE` | percent | 1 |  | 10-year breakeven inflation | FRED; public domain unless noted by the original source |
| `T5YIFR` | US | D | fred | `T5YIFR` | percent | 1 |  | 5y5y forward inflation expectation | FRED; public domain unless noted by the original source |
| `THREEFYTP10` | US | D | fred | `THREEFYTP10` | percent | 7 | yes | Kim-Wright 10Y term premium (Fed Board) | FRED; public domain unless noted by the original source |
| `ACMTP10` | US | D | nyfed_files | `ACMTermPremium.xls:ACMTP10` | percent | 35 |  | ACM 10Y term premium (NY Fed, monthly file update) | NY Fed research series; cite source |
| `MORTGAGE30US` | US | W | fred | `MORTGAGE30US` | percent | 1 |  | 30-year fixed mortgage rate (Freddie Mac) | FRED; public domain unless noted by the original source |
| `BAMLC0A4CBBBEY` | US | D | fred | `BAMLC0A4CBBBEY` | percent | 1 | yes | ICE BofA BBB corporate effective yield | ICE BofA via FRED: copyrighted, FRED may truncate history; do not redistribute raw data |
| `DBAA` | US | D | fred | `DBAA` | percent | 1 |  | Moody's seasoned Baa corporate bond yield (long-history substitute for the ICE BBB yield) | Moody's via FRED; cite source |
| `BAA10Y` | US | D | fred | `BAA10Y` | percentage points | 1 |  | Moody's Baa yield minus 10-year Treasury | Moody's via FRED; cite source |
| `BAMLH0A0HYM2` | US | D | fred | `BAMLH0A0HYM2` | percentage points | 1 | yes | ICE BofA US high yield OAS | ICE BofA via FRED: copyrighted, FRED may truncate history; do not redistribute raw data |
| `BAMLC0A0CM` | US | D | fred | `BAMLC0A0CM` | percentage points | 1 | yes | ICE BofA US corporate IG OAS | ICE BofA via FRED: copyrighted, FRED may truncate history; do not redistribute raw data |
| `NFCI` | US | W | fred | `NFCI` | index | 5 |  | Chicago Fed National Financial Conditions Index | FRED; public domain unless noted by the original source |
| `STLFSI4` | US | W | fred | `STLFSI4` | index | 5 |  | St. Louis Fed Financial Stress Index | FRED; public domain unless noted by the original source |
| `VIXCLS` | US | D | fred | `VIXCLS` | index | 1 |  | CBOE VIX | CBOE via FRED; cite source |
| `DTWEXBGS` | US | D | fred | `DTWEXBGS` | index | 7 |  | Nominal broad US dollar index | FRED; public domain unless noted by the original source |
| `CSUSHPISA` | US | M | fred | `CSUSHPISA` | index | 60 |  | S&P CoreLogic Case-Shiller US national home price index | S&P via FRED; copyrighted, do not redistribute |
| `CPIAUCSL` | US | M | fred | `CPIAUCSL` | index | 15 |  | CPI all items SA | FRED; public domain unless noted by the original source |
| `CPILFESL` | US | M | fred | `CPILFESL` | index | 15 |  | CPI less food and energy SA | FRED; public domain unless noted by the original source |
| `CPIENGSL` | US | M | fred | `CPIENGSL` | index | 15 |  | CPI energy SA | FRED; public domain unless noted by the original source |
| `CPIUFDSL` | US | M | fred | `CPIUFDSL` | index | 15 |  | CPI food SA | FRED; public domain unless noted by the original source |
| `CUSR0000SAS` | US | M | fred | `CUSR0000SAS` | index | 15 |  | CPI services SA | FRED; public domain unless noted by the original source |
| `CUSR0000SACL1E` | US | M | fred | `CUSR0000SACL1E` | index | 15 |  | CPI commodities less food and energy (core goods) SA | FRED; public domain unless noted by the original source |
| `PCEPI` | US | M | fred | `PCEPI` | index | 30 |  | PCE price index | FRED; public domain unless noted by the original source |
| `PCEPILFE` | US | M | fred | `PCEPILFE` | index | 30 |  | Core PCE price index | FRED; public domain unless noted by the original source |
| `MEDCPIM158SFRBCLE` | US | M | fred | `MEDCPIM158SFRBCLE` | percent annualized m/m | 15 | yes | Cleveland Fed median CPI | FRED; public domain unless noted by the original source |
| `TRMMEANCPIM158SFRBCLE` | US | M | fred | `TRMMEANCPIM158SFRBCLE` | percent annualized m/m | 15 | yes | Cleveland Fed 16% trimmed-mean CPI | FRED; public domain unless noted by the original source |
| `CORESTICKM159SFRBATL` | US | M | fred | `CORESTICKM159SFRBATL` | percent y/y | 15 | yes | Atlanta Fed sticky-price core CPI | FRED; public domain unless noted by the original source |
| `PPIFIS` | US | M | fred | `PPIFIS` | index | 15 |  | PPI final demand | FRED; public domain unless noted by the original source |
| `MICH` | US | M | fred | `MICH` | percent | 0 |  | University of Michigan 1-year inflation expectations | U. Michigan via FRED; cite source |
| `EXPINF10YR` | US | M | fred | `EXPINF10YR` | percent | 15 |  | Cleveland Fed model 10-year expected inflation | FRED; public domain unless noted by the original source |
| `DCOILBRENTEU` | GLOBAL | D | fred | `DCOILBRENTEU` | USD per barrel | 7 |  | Brent crude spot (EIA) | FRED; public domain unless noted by the original source |
| `UNRATE` | US | M | fred | `UNRATE` | percent | 7 |  | Unemployment rate | FRED; public domain unless noted by the original source |
| `NROU` | US | Q | fred | `NROU` | percent | 0 |  | CBO noncyclical rate of unemployment (projection series) | FRED; public domain unless noted by the original source |
| `PAYEMS` | US | M | fred | `PAYEMS` | thousands | 7 |  | Nonfarm payrolls | FRED; public domain unless noted by the original source |
| `ICSA` | US | W | fred | `ICSA` | claims | 5 |  | Initial jobless claims | FRED; public domain unless noted by the original source |
| `GDPC1` | US | Q | fred | `GDPC1` | billions chained USD SAAR | 30 |  | Real GDP | FRED; public domain unless noted by the original source |
| `GDPPOT` | US | Q | fred | `GDPPOT` | billions chained USD | 0 |  | CBO real potential GDP (projection series) | FRED; public domain unless noted by the original source |
| `INDPRO` | US | M | fred | `INDPRO` | index | 16 |  | Industrial production | FRED; public domain unless noted by the original source |
| `RSAFS` | US | M | fred | `RSAFS` | millions USD | 15 |  | Advance retail sales | FRED; public domain unless noted by the original source |
| `PCEC96` | US | M | fred | `PCEC96` | billions chained USD | 30 |  | Real personal consumption expenditures | FRED; public domain unless noted by the original source |
| `HOUST` | US | M | fred | `HOUST` | thousands SAAR | 17 |  | Housing starts | FRED; public domain unless noted by the original source |
| `BOPTEXP` | US | M | fred | `BOPTEXP` | millions USD | 35 |  | Exports of goods and services | FRED; public domain unless noted by the original source |
| `UMCSENT` | US | M | fred | `UMCSENT` | index | 0 |  | University of Michigan consumer sentiment | U. Michigan via FRED; cite source |
| `GACDFSA066MSFRBPHI` | US | M | fred | `GACDFSA066MSFRBPHI` | diffusion index | 0 | yes | Philadelphia Fed manufacturing current activity | FRED; public domain unless noted by the original source |
| `BACTSAMFRBDAL` | US | M | fred | `BACTSAMFRBDAL` | diffusion index | 0 |  | Dallas Fed Texas manufacturing outlook, current general business activity (replaces the Empire State survey, no longer on FRED) | FRED; public domain unless noted by the original source |
| `USREC` | US | M | fred | `USREC` | 0/1 | 0 |  | NBER recession indicator (dated with long lags by NBER) | FRED; public domain unless noted by the original source |
| `EA_DFR` | EA | D | ecb | `FM.D.U2.EUR.4F.KR.DFR.LEV` | percent | 0 |  | ECB deposit facility rate | ECB Data Portal: reuse allowed with source attribution |
| `EA_HICP` | EA | M | eurostat | `prc_hicp_minr:EA:I25:TOTAL` | index 2025=100 (ECOICOP v2) | 17 |  | HICP overall index | Eurostat; reuse allowed with source attribution |
| `EA_HICP_CORE` | EA | M | eurostat | `prc_hicp_minr:EA:I25:TOT_X_NRG_FOOD` | index 2025=100 (ECOICOP v2) | 17 |  | HICP excl. energy | Eurostat; reuse allowed with source attribution |
| `EA_HICP_ENERGY` | EA | M | eurostat | `prc_hicp_minr:EA:I25:NRG` | index 2025=100 (ECOICOP v2) | 17 |  | HICP energy | Eurostat; reuse allowed with source attribution |
| `EA_HICP_FOOD` | EA | M | eurostat | `prc_hicp_minr:EA:I25:FOOD` | index 2025=100 (ECOICOP v2) | 17 |  | HICP food incl. alcohol and tobacco | Eurostat; reuse allowed with source attribution |
| `EA_HICP_SERV` | EA | M | eurostat | `prc_hicp_minr:EA:I25:SERV` | index 2025=100 (ECOICOP v2) | 17 |  | HICP services | Eurostat; reuse allowed with source attribution |
| `EA_HICP_NEIG` | EA | M | eurostat | `prc_hicp_minr:EA:I25:IGD_NNRG` | index 2025=100 (ECOICOP v2) | 17 |  | HICP non-energy industrial goods | Eurostat; reuse allowed with source attribution |
| `EA_YC_2Y` | EA | D | ecb | `YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y` | percent | 1 |  | AAA euro area govt spot rate 2Y | ECB Data Portal: reuse allowed with source attribution |
| `EA_YC_10Y` | EA | D | ecb | `YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y` | percent | 1 |  | AAA euro area govt spot rate 10Y | ECB Data Portal: reuse allowed with source attribution |
| `DE_10Y` | EA | M | ecb | `IRS.M.DE.L.L40.CI.0000.EUR.N.Z` | percent | 10 | yes | Germany 10Y long-term interest rate (convergence criterion) | ECB Data Portal: reuse allowed with source attribution |
| `FR_10Y` | EA | M | ecb | `IRS.M.FR.L.L40.CI.0000.EUR.N.Z` | percent | 10 | yes | France 10Y long-term interest rate | ECB Data Portal: reuse allowed with source attribution |
| `IT_10Y` | EA | M | ecb | `IRS.M.IT.L.L40.CI.0000.EUR.N.Z` | percent | 10 | yes | Italy 10Y long-term interest rate | ECB Data Portal: reuse allowed with source attribution |
| `ES_10Y` | EA | M | ecb | `IRS.M.ES.L.L40.CI.0000.EUR.N.Z` | percent | 10 | yes | Spain 10Y long-term interest rate | ECB Data Portal: reuse allowed with source attribution |
| `EA_UNRATE` | EA | M | ecb | `LFSI.M.I9.S.UNEHRT.TOTAL0.15_74.T` | percent | 32 | yes | Euro area unemployment rate (country group code may change with enlargement) | ECB Data Portal: reuse allowed with source attribution |
| `EUROREC` | EA | M | eurostat | `techrec:namq_10_gdp:EA:CLV10_MEUR:SCA:B1GQ` | 0/1 | 135 |  | Euro area technical recession indicator (two or more consecutive quarters of falling real GDP, Eurostat); replaces the discontinued OECD-based EUROREC. Lag 135 days = first month of a quarter to its GDP release (quarter end + ~45 days), conservative for all three months | Eurostat; derived indicator |
| `JP_POLICY` | JP | M | fred | `IRSTCI01JPM156N` | percent | 30 | yes | Japan call money rate (OECD MEI; may be stale | FRED; public domain unless noted by the original source |
| `JP_CPI` | JP | M | bis | `WS_LONG_CPI:M.JP.628` | index 2010=100 | 60 |  | Japan CPI all items (BIS long CPI series; replaces the discontinued OECD MEI series on FRED; BIS republishes national CPI with a ~2-month delay) | BIS statistics; cite source |
| `JP_10Y` | JP | M | fred | `IRLTLT01JPM156N` | percent | 30 | yes | Japan 10Y government bond yield (OECD MEI) | FRED; public domain unless noted by the original source |
| `SPX` | US | D | yahoo | `^GSPC` | index | 1 |  | S&P 500 | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `SX5E` | EA | D | yahoo | `^STOXX50E` | index | 1 |  | Euro Stoxx 50 | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `N225` | JP | D | yahoo | `^N225` | index | 1 |  | Nikkei 225 | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `SOX` | US | D | yahoo | `^SOX` | index | 1 |  | PHLX Semiconductor index | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `NVDA` | US | D | yahoo | `NVDA` | USD | 1 |  | NVIDIA share price (AI-leader basket component) | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `MSFT` | US | D | yahoo | `MSFT` | USD | 1 |  | Microsoft share price (AI-leader basket component) | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `GOOGL` | US | D | yahoo | `GOOGL` | USD | 1 |  | Alphabet class A share price (AI-leader basket component) | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `AMZN` | US | D | yahoo | `AMZN` | USD | 1 |  | Amazon share price (AI-leader basket component) | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `META` | US | D | yahoo | `META` | USD | 1 |  | Meta Platforms share price (AI-leader basket component) | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `VIX` | US | D | yahoo | `^VIX` | index | 1 |  | CBOE VIX (Yahoo) | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `MOVE` | US | D | yahoo | `^MOVE` | index | 1 | yes | ICE BofA MOVE index (Yahoo) | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `EURUSD` | GLOBAL | D | yahoo | `EURUSD=X` | USD per EUR | 1 |  | EURUSD spot | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `USDJPY` | GLOBAL | D | yahoo | `USDJPY=X` | JPY per USD | 1 |  | USDJPY spot | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `DXY` | US | D | yahoo | `DX-Y.NYB` | index | 1 |  | ICE US dollar index | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `BRENT_FUT` | GLOBAL | D | yahoo | `BZ=F` | USD per barrel | 1 |  | Brent front-month future | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `GOLD_FUT` | GLOBAL | D | yahoo | `GC=F` | USD per oz | 1 |  | Gold front-month future | Yahoo Finance via public endpoint: personal, non-commercial use only; do not redistribute |
| `HLW_RSTAR_US` | US | Q | nyfed_files | `HLW:US` | percent | 90 |  | Holston-Laubach-Williams r* US (one-sided) | NY Fed research series; not an official forecast |
| `HLW_RSTAR_EA` | EA | Q | nyfed_files | `HLW:Euro Area` | percent | 90 |  | Holston-Laubach-Williams r* euro area | NY Fed research series; not an official forecast |
| `LW_RSTAR_US` | US | Q | nyfed_files | `LW:US` | percent | 90 |  | Laubach-Williams r* US (one-sided) | NY Fed research series; not an official forecast |
| `GSCPI` | GLOBAL | M | nyfed_files | `GSCPI:GSCPI` | standard deviations | 4 | yes | NY Fed Global Supply Chain Pressure Index | NY Fed research series; cite source |
| `CIE` | US | Q | fed_board_files | `CIE:CIE` | percent | 20 | yes | Fed Board Index of Common Inflation Expectations | Fed Board research series; experimental, revised each update |
| `FCIG_1Y` | US | M | fed_board_files | `FCIG_1Y:FCI-G Index (one-year lookback)` | percentage points of GDP growth | 30 |  | Fed Board FCI-G one-year lookback | Fed Board research series; experimental |
| `SPF_CPI_1Y` | US | Q | philly | `SPF_INFL:INFCPI1YR` | percent | 45 |  | Philadelphia Fed SPF median CPI inflation forecast | Philadelphia Fed; cite source |
| `SPF_RGDP_1Y` | US | Q | philly | `SPF_GROWTH:RGDP:4q` | percent | 45 |  | Philadelphia Fed SPF mean real GDP growth forecast | Philadelphia Fed; cite source |
| `SPF_RGDP_CQ` | US | Q | philly | `SPF_GROWTH:RGDP:cq` | percent annualised q/q | 0 |  | Philadelphia Fed SPF mean real GDP growth forecast for the survey quarter (RGDP2; survey released mid-quarter — availability treated as quarter end) | Philadelphia Fed; cite source |
| `SPF_CPI10` | US | Q | philly | `SPF_INFL:INFCPI10YR` | percent | 45 |  | Philadelphia Fed SPF median 10-year CPI inflation expectation | Philadelphia Fed; cite source |
| `TFF_UST10_LEV` | US | W | cftc | `TFF:043602:lev_money` | contracts net | 3 |  | Leveraged-fund net position | CFTC public data |
| `TFF_UST10_AM` | US | W | cftc | `TFF:043602:asset_mgr` | contracts net | 3 |  | Asset-manager net position | CFTC public data |
| `TFF_SOFR3M_LEV` | US | W | cftc | `TFF:134741:lev_money` | contracts net | 3 |  | Leveraged-fund net position | CFTC public data |
| `TFF_ES_LEV` | US | W | cftc | `TFF:13874A:lev_money` | contracts net | 3 |  | Leveraged-fund net position | CFTC public data |
| `TFF_ES_AM` | US | W | cftc | `TFF:13874A:asset_mgr` | contracts net | 3 |  | Asset-manager net position | CFTC public data |
| `TFF_EUR_LEV` | GLOBAL | W | cftc | `TFF:099741:lev_money` | contracts net | 3 |  | Leveraged-fund net position | CFTC public data |
| `TFF_JPY_LEV` | GLOBAL | W | cftc | `TFF:097741:lev_money` | contracts net | 3 |  | Leveraged-fund net position | CFTC public data |
