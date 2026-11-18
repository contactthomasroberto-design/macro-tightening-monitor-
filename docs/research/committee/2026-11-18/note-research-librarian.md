# Research librarian : vues candidates (comité du 17/11/2026)

Fichiers lus sans modification : `.claude/agents/research-librarian.md`, `config/house_views.yaml`, `config/portfolio.yaml`. Les tickers XLV, NVDA, MCHI, INDA, EWY, EWT, FXF, FXY, BNO, IEF et VGK figurent tous dans l'univers. Il n'y a pas d'ETF tech large (pas de XLK).

Bilan : 2 acceptées, 2 fusions, 1 correction, 6 rejetées.

| # | Candidate | Verdict | Raison |
|---|---|---|---|
| 1 | GS, objectif KOSPI 7 500 (17/11) | REJETÉE | Date et objectif vérifiés (Investing.com, 17/11), mais la note ne contient pas de pondération explicite : « greatest potential upside » est du ton. Elle est aussi redondante avec l'entrée GS Asie du 15/11 (Corée surpondérée, EWY +1). Le chiffre peut être ajouté au résumé de cette entrée. |
| 2 | MS Asie/EM (16/11) | FUSION | C'est le même rapport, « 2027 Global Strategy Outlook » (Investing.com). Corée surpondérée ; Chine, HK, Inde et Taïwan à equal-weight ; Japon relevé à surpondérer, TOPIX 4 800 (déc. 2027). |
| 3 | GS FX, USD/JPY 150 (15/11) | REJETÉE | La date d'origine est fin septembre 2026 (révision de K. Reichgott Fishman, 150 contre 165 ; stockhub.kr, briefs.co). Le papier Bloomingbit du 15/11 est une reprise, et la vue a plus de 30 jours. |
| 4 | Citi (09/11) | ACCEPTÉE (partielle) | The Standard, 09/11 : actions US ramenées de surpondérer à neutre, tech mondiale à neutre, santé mondiale relevée à surpondérer. Pour l'Europe hors R.-U., la note dit seulement « more positive », sans notation : VGK est exclu. XLV est à +0,5 et non +1, car c'est un appel sur la santé mondiale porté par un ETF US (proxy). Couverture secondaire. |
| 5 | HSBC Nvidia (14/11) | ACCEPTÉE | 247wallst, 14/11 : de Buy à Hold, objectif d'environ 370 $ à 170 $ (Frank Lee). Le jour exact de la note HSBC n'est pas donné ; j'ai retenu la date de la couverture. Couverture secondaire. |
| 6 | MS Nvidia 267 $ (16/11) | REJETÉE | Aucune source lisible trouvée. Dernier objectif vérifiable : 285 $ (Overweight), le 18/05/2026. |
| 7 | UBS Brent 110 $ (28/10) | REJETÉE | Date vérifiée (Reuters via BOE Report, 28/10 ; roic.ai date la note du 27/10), donc dans la fenêtre. Mais il n'y a pas de recommandation, seulement un chemin de prix qui baisse sur la durée de validité de la vue (110 $ fin 2026, 95 $ en mars 2027, 90 $ en juin, 85 $ en septembre). Un BNO +0,5 serait déduit. |
| 8 | T. Rowe Price, A. Husain | REJETÉE | La page est datée « November 2026 » sans jour, donc la date n'est pas vérifiable. Aucun positionnement explicite : « still somewhat bearish » et « bear flatten » relèvent du ton. |
| 9 | J.P. Morgan, Europe (16/11) | REJETÉE | Aucune source lisible. Le seul chiffre trouvé (BPA 2027 +12 %, Stoxx 600 680) date de juin 2026. |
| 10 | ING CHF (04/11), entrée existante | CORRECTION : retrait | Source FXStreet en 403, lue via extrait de recherche et Tradingpedia (04/11). Les seules prévisions chiffrées portent sur EUR/CHF (« downside risks to EUR/CHF forecasts »). « Clean positive for the Swiss franc » est générique, sans référence au USD, et l'univers n'a pas d'instrument EUR/CHF. FXF (CHF/USD) ne reçoit donc aucune vue explicite. Je propose de retirer l'entrée ; à défaut, ramener FXF à 0 avec cette raison en commentaire. |
| 11 | GS Asie (15/11), MCHI | FUSION : MCHI +0,5 | Business Today, 15/11 : « Upgraded to overweight: China H-shares and India », A-shares ramenées à market weight. MCHI mêle de l'offshore (H-shares surpondérées) et une petite poche d'A-shares (market weight), d'où +0,5 et non +1. |

## YAML

```yaml
  # 4. nouvelle entrée
  - institution: Citi Research (global equity strategy)
    title: "US equities cut to neutral on AI concerns; global health care to overweight"
    date: 2026-11-09
    url: https://www.thestandard.com.hk/finance/article/347976/Citigroup-downgrades-US-equities-to-neutral-on-AI-concerns
    summary: US equities cut to neutral from overweight; global and European tech to neutral; global health care and European food & beverage raised to overweight; more positive on Europe ex-UK without a stated rating (not encoded). XLV is a proxy for the global sector call (secondary coverage).
    stances: {SPY: 0, XLV: 0.5}

  # 5. nouvelle entrée
  - institution: HSBC Global Research (US semiconductors)
    title: "Nvidia downgraded to Hold, target cut to $170"
    date: 2026-11-14
    url: https://247wallst.com/investing/2026/11/14/hsbc-just-downgraded-nvidia-and-cut-its-target-to-170/
    summary: Analyst Frank Lee downgrades Nvidia to Hold from Buy and cuts the target to $170 from about $370 (date of coverage; the note's own date is not stated; secondary coverage).
    stances: {NVDA: 0}

  # 2. FUSION : remplace l'entrée Morgan Stanley "2027 Global Strategy Outlook" du 16/11 (url inchangée)
  - institution: Morgan Stanley Research
    title: "2027 Global Strategy Outlook"
    date: 2026-11-16
    url: https://www.cnbc.com/2026/11/16/goldman-sachs-morgan-stanley-2027-outlook-markets.html
    summary: >-
      Maximum overweight global equities, adding in every region (S&P 500 8,700, MSCI Europe 3,030,
      TOPIX 4,800 Dec-2027; Japan raised to overweight from equal weight); Asia/EM strategists overweight
      Japan and Korea, equal weight China, Hong Kong, India and Taiwan (Investing.com, 16 Nov); core bonds
      neutral, corporate credit equal weight; prefers Bunds and gilts; modest dollar rally (DXY 105), yen
      weaker (162); gold top commodity pick ($5,250).
    stances: {SPY: 1, VGK: 1, EWJ: 1, EEM: 0, EWY: 1, EWT: 0, MCHI: 0, INDA: 0, AGG: 0, IEF: 0, LQD: 0, BWX: 0.5, UUP: 0.5, FXY: -1, GLD: 1}

  # 11. FUSION : entrée Goldman Sachs Asia du 15/11, stances seulement
    stances: {EWY: 1, EWJ: 1, EWT: 0, INDA: 1, MCHI: 0.5}

  # 10. CORRECTION : supprimer l'entrée ING "Swiss franc supported by hawkish SNB risk" (2026-11-04)
```

## Notes

- **MS 2 :** l'entrée MS fusionnée pose MCHI 0 alors que GS 15/11 pose MCHI +0,5 et HSBC 20/10 MCHI +1. C'est cohérent : les vues divergent vraiment.
- **Brent :** BNO reste avec GS −0,5 et EIA −0,5. UBS, non encodé, est un contre-signal haussier à court terme.
- **Confiance :** élevée pour 2, 3, 5 et 11 ; moyenne pour 4 (proxy XLV) et 10 (page primaire non ouverte).
- **Ce qui me ferait changer d'avis :** une source lisible pour MS Nvidia 267 $ ou JPM Europe ; le texte ING complet s'il mentionne USD/CHF.
- **Question pour l'équipe quant :** un objectif de prix sur matière première (UBS Brent) doit-il être converti en signe par rapport au spot à la date de publication, selon une règle écrite ? Le fichier le fait déjà pour les objectifs d'indice (UBS S&P, UBS Stoxx).
