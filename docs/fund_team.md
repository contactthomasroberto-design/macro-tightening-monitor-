# L'équipe du fonds : qui fait quoi

Le fonds est **systématique** : les règles de `config/portfolio.yaml` fixent les positions. L'équipe d'agents
ne fixe pas les poids. Elle produit la recherche qui alimente les règles et en garde une trace honnête.
Les rôles sont décrits dans `.claude/agents/`. Toute session Claude Code ouverte sur ce dépôt peut les appeler.

| Rôle | Agent | Périmètre |
|---|---|---|
| CIO / gérant | `chief-investment-officer` | Comité du soir, arbitrage, vues publiées à enregistrer, note quotidienne |
| Stratégiste macro | `macro-strategist` | Croissance, inflation, banques centrales, régime macro |
| Actions US | `us-equity-analyst` | S&P 500, styles, secteurs, résultats, valorisations |
| Europe | `europe-analyst` | Actions européennes, BCE et BoE, spreads souverains, euro |
| Japon et Asie développée | `japan-asia-analyst` | BoJ, yen, JGB, Corée, Taïwan |
| Émergents | `emerging-markets-analyst` | Chine, Inde, Brésil, dette émergente, flux |
| Semi-conducteurs | `semis-tech-analyst` | Cycle mémoire (DRAM, HBM), SK Hynix, Samsung, Micron, TSMC, NVIDIA, ASML |
| Énergie et matières premières | `energy-commodities-analyst` | Pétrole, or, argent, cuivre |
| Financières et immobilier | `financials-analyst` | Banques, REIT, crédit privé |
| Taux et crédit | `rates-credit-analyst` | Courbes, prime de terme, TIPS, IG, HY, dette émergente |
| Changes | `fx-strategist` | Dollar, yen, euro, franc suisse, carry |
| Recherche quantitative | `quant-researcher` | Tests de signaux, surapprentissage, hypothèses pré-enregistrées |
| Risque | `risk-manager` | Mandat, concentrations, stress, couverture, ventes à découvert |

Depuis le 17/11/2026, l'équipe compte **27 membres répartis en 7 équipes**, détaillés dans `config/team.yaml`
et visibles sur la page **Portfolio → Team** du site, avec leur travail en cours et leurs travaux passés
(`archive/team_log.csv`). Aux rôles ci-dessus s'ajoutent :
- économiste États-Unis et analyste banques centrales ;
- analystes pétrole et gaz, métaux, défense et industrie ;
- analystes haut rendement et dette émergente ;
- chercheur signaux, quant construction de portefeuille, analyste exécution et coûts, analyste stress tests ;
- ingénieur données, desk news et documentaliste recherche.

## Le cycle quotidien
1. **Toutes les deux heures** (GitHub Actions) :
   - FinBERT note les titres de presse ;
   - le suivi de recherche relève les publications de 20 banques, gérants et hedge funds et extrait
     les recommandations explicites ;
   - le risque est contrôlé, avec une alerte en cas de dépassement.
2. **Après la clôture de New York** (rafraîchissement du soir) :
   - mise à jour des données ;
   - backtest et poids du jour ;
   - rééquilibrage papier hebdomadaire ;
   - le **rapport du soir** est publié en issue GitHub (envoyée par e-mail).
3. **La nuit** (session Claude programmée), le CIO réunit les analystes. Ils couvrent tout le marché,
   pas seulement nos positions. Le CIO :
   - enregistre dans `config/house_views.yaml` les nouvelles vues publiées, datées et sourcées ;
   - écrit la note `docs/research/daily/<date>.md` ;
   - propose les changements de modèle sous forme d'hypothèses pré-enregistrées.

## Le desk GitHub (depuis le 17/11/2026)
À chaque rafraîchissement (3 fois par jour en semaine), `scripts/desk_run.py` (`src/macro/desk.py`) écrit une note
calculée pour chaque membre dont le travail se chiffre. Pas d'IA, pas de tokens. Les notes sont dans
`docs/research/desk/` et sur la page **Portfolio → Desk**, et la page Team affiche la dernière note de chaque membre.

**Ce que couvre chaque note, sur tout son marché et pas seulement nos lignes :**
- **Analystes de zone et de secteur** :
  - par instrument : rendements à 1, 3 et 12 mois, distance au plus haut, volatilité, momentum 12-1 ;
  - z-score du mouvement d'un mois, percentile sur 5 ans, bêta et corrélation au S&P 500, rupture de corrélation ;
  - les scores de chaque famille de signaux, avec leur accord, le surplus de rendement attendu du modèle et le
    consensus des vues publiées (désaccords signalés) ;
  - le poids détenu par rapport au 60/40, et une idée de valeur relative à débattre ;
  - le scan des séries de leur marché : spreads souverains, prime de terme, breakevens, positionnement CFTC,
    inflation de zone, différentiels de taux, matières premières, conditions financières.
- **Macro** : régime, facteurs, nowcast, récession, inflation, emploi et règle de Sahm, banques centrales et prix
  de marché, plus un tour d'horizon cross-asset de tous les marchés suivis, classés par ampleur du mouvement.
- **Quants** : tests et deflated Sharpe, variantes, contribution et cohérence des familles de signaux,
  contraintes saturées, rotation et coûts.
- **Risque** : volatilité, TE, VaR et ES, contributions au risque, stress tests et crises rejouées, qualité des
  données, news notées, veille des publications.
- **CIO** : synthèse et liste des points à débattre au comité du soir.

**Le comité Claude de la nuit part de ces notes.** Il ajoute ce que le code ne sait pas faire : lire les
publications nouvelles, juger les événements, débattre et trancher.

## Contrôles du process (depuis le 17/11/2026)
Calculés dans GitHub à chaque rafraîchissement (`scripts/process_controls.py`, `src/macro/fund_process.py`) :
- **Registre des paris** (`archive/decisions.csv`). Chaque vue du comité est enregistrée avant les faits :
  - un instrument ou une série, un seuil, un horizon et une probabilité ;
  - le résultat est constaté à partir des données, sans jugement humain ;
  - le **score de Brier** est calculé par analyste (0 = parfait, 0,25 = toujours 50 %) et affiché sur la page Team.
- **Revues de pertes**. Toute position qui a coûté plus de 1 % de la VL sur 4 semaines déclenche un diagnostic
  automatique :
  - mouvement en écarts-types, part expliquée par le marché, position à sa borne, vues qui la portaient ;
  - il est écrit dans `docs/research/postmortems/` et complété par le comité (donnée, signal, taille ou malchance).
- **Stress tests prospectifs** (`config/stress_scenarios.yaml`), chaque jour sur le portefeuille du jour :
  - krach IA, cycle mémoire, pétrole, carry yen, crédit, taux, stagflation, dollar, Chine-Taïwan ;
  - limites : 15 % de la VL, et pas plus que la perte du 60/40 plus 2 points ;
  - un dépassement ouvre une issue pour le comité, sans changer les poids de lui-même.

## Garde-fous
- Aucune vue personnelle de l'IA n'est enregistrée comme « vue de maison ». Seules les positions
  publiées par une institution identifiable le sont, avec la date et le lien.
- Aucun paramètre n'est modifié par l'équipe : un changement est une hypothèse, testée avant d'être adoptée.
- Les sources payantes, les contenus derrière un paywall et le scraping de sites qui l'interdisent sont exclus.
