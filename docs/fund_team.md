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

## Garde-fous
- Aucune vue personnelle de l'IA n'est enregistrée comme « vue de maison ». Seules les positions
  publiées par une institution identifiable le sont, avec la date et le lien.
- Aucun paramètre n'est modifié par l'équipe : un changement est une hypothèse, testée avant d'être adoptée.
- Les sources payantes, les contenus derrière un paywall et le scraping de sites qui l'interdisent sont exclus.
