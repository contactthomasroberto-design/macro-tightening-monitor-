# Note de stratégie 2027 — le fonds multi-actifs systématique

*17 novembre 2026. Portefeuille modèle suivi sur papier, aucun ordre passé ; pas un conseil en investissement.*

## 1. Ce que disent les grandes maisons

Les perspectives 2027 publiées ces dernières semaines dessinent un consensus **constructif sur les
actions, prudent sur le crédit et divisé sur le dollar et l'or**.

| Maison | Date | Actions | Obligations et crédit | Or, dollar, matières premières |
|---|---|---|---|---|
| Goldman Sachs | 16 nov. | Surpondère US et Japon, neutre émergents, sous-pondère Europe ; S&P 500 à 8 700 | Spreads plus larges, haut rendement US sous-performant | Or en couverture (mais deux baisses d'objectif en un mois) ; Brent 78 $ fin 2027 |
| Morgan Stanley | 16 nov. | Surpondération maximale de toutes les régions | Obligations « core » neutres, crédit en ligne ; préfère Bund et gilt | Dollar en hausse modeste, yen plus faible (162) ; or premier choix (5 250 $) |
| BlackRock | 9 nov. | US neutre, émergents surpondérés | Préfère les Treasuries courts | Risque : ralentissement du capex IA en 2027 |
| J.P. Morgan AM (long terme) | 19 oct. | Marchés développés devant émergents | Obligations les plus attractives depuis 20 ans (5,3 %) | Alternatives : Sharpe +21 % dans un 60/40 |
| Amundi | nov. | Rotation vers US et Japon, Europe neutre | — | — |
| HSBC (émergents) | oct. | Surpondère Taïwan, Chine, Brésil ; sous-pondère Inde | — | — |
| Merrill (BofA) | 9 nov. | Actions devant obligations, biais qualité | — | — |
| Analystes mémoire (KB, RBC, Hana, UBS) | nov. | DRAM +40 % et HBM +80 à 121 % en 2027 ; production vendue jusqu'en 2029 | — | — |

Sources : voir `config/house_views.yaml`, chaque entrée porte son lien.

## 2. Comment le fonds s'en sert, et pourquoi pas davantage

Ces vues entrent dans l'allocation comme **une famille parmi huit**, avec une confiance de 10 % pendant
six mois. Elles ne peuvent pas être backtestées : on ne connaît pas l'historique des recommandations.
Les familles testées depuis 2005 pèsent plus lourd :
- tendance (30 %) ;
- macro (20 %) ;
- micro sur les semis (20 %) ;
- régime (15 %) ;
- portage (15 %) ;
- valeur (10 %).

La leçon du monitor tient toujours : **le consensus n'est pas une prévision**. Sur la Fed, le prix de
marché a battu nos règles. Le travail utile consiste à repérer où nos signaux et le consensus divergent,
et à comprendre pourquoi (page Research).

## 3. Les paris structurants du fonds

- **Actions mondiales légèrement surpondérées**, avec la tendance comme garde-fou. L'exposition nette
  reste entre 20 % et 90 %.
- **Semi-conducteurs mémoire** : c'est la conviction du propriétaire. La poche nette est entre 5 % et
  15 %, SK Hynix et Samsung sont détenus à au moins 1,5 % chacun. Le modèle ajuste les poids avec le
  momentum, le cycle mémoire lu dans les comptes de Micron et la tonalité des news. Le risque sectoriel
  peut être couvert par une vente à découvert de l'indice SOXX.
- **Couverture de queue** : achat mensuel de puts sur le S&P 500. On couvre davantage quand la tendance
  américaine se retourne, et plus encore quand la volatilité est bon marché.
- **Diversifiants** : or, managed futures, yen et franc suisse en cas de stress. Ils entrent dans
  l'allocation quand les signaux le justifient, pas par principe.

## 4. Ce qui ferait changer le fonds de cap
- Un retournement de tendance des actions mondiales : les vues de tendance passent négatives et la
  couverture monte.
- Une remontée de la prime de risque crédit (EBP) : sous-pondération actions et crédit, duration en hausse.
- Une inflation sous-jacente qui réaccélère : TIPS et matières premières contre obligations nominales.
- Un retournement du cycle mémoire (croissance du chiffre d'affaires de Micron qui décélère) : la poche
  semis va vers son plancher, avec couverture par SOXX.

## 4 bis. Savoir ce que l'on porte vraiment
- **Budget de risque par source** (page Risk) : part de la variance venant des actions, de la duration,
  de l'inflation, du crédit, des devises, des semis, des matières premières et des alternatifs
  (contributions d'Euler, ex ante et réalisées sur 3 ans). On voit ainsi qu'un book « diversifié » peut
  rester dominé par une seule source.
- **Expositions de style** : régression sur marché, value, momentum, qualité, équipondéré et faible
  volatilité. La part du rendement actif qu'expliquent ces facteurs pourrait s'acheter en ETF ; seul
  l'alpha résiduel revient au modèle (hypothèse H46, testée chaque semaine par le laboratoire quant).
- **Optimisation rééchantillonnée** (Michaud) : en test seulement (H47). Elle serait adoptée si elle réduit
  la rotation d'au moins 20 % sans coûter plus de 0,05 de Sharpe.

## 4 ter. Les contrôles de fonctionnement
- **Face à des fonds qu'on peut acheter.** Le modèle est comparé, sur leur historique commun et nets
  de leurs frais, à quatre ETF :
  - DBMF (managed futures) ;
  - RPAR (risk parity) ;
  - QAI et HDG (réplication de hedge funds).

  Si le fonds ne fait pas mieux que ces produits, sa complexité ne paie pas. C'est sur la page
  Portfolio → Backtest.
- **Liquidité.** Pour un fonds notionnel de 100 M$, on calcule combien de jours il faudrait pour sortir
  de chaque ligne à 10 % du volume quotidien. Une ligne est signalée au-delà d'un jour ou de 1 % du volume
  d'une journée. Les volumes sont des estimations arrondies et datées, pas des données en direct :
  l'ordre de grandeur compte, pas la décimale. C'est sur la page Risk.
- **Qualité des prix.** Toutes les deux heures, deux contrôles :
  - un saut de plus de 6 écarts-types que le secteur ne confirme pas ;
  - un cours de clôture qui diffère de plus de 2 % entre Yahoo et Stooq.

  Chaque anomalie est archivée et ouvre une alerte GitHub. Elle apparaît aussi dans le rapport du soir.
  Elle ne modifie jamais une position d'elle-même.
- **Santé du modèle.** La page Portfolio → Model health suit :
  - la rotation des poids ;
  - la volatilité prévue face à la volatilité réalisée ;
  - les limites saturées ;
  - les contraintes relâchées par l'optimiseur ;
  - l'écart entre le carnet papier et le backtest.

## 5. Limites, sans fard
- Biais du survivant : les six valeurs semis ont été choisies en 2026.
- Les puts sont synthétiques (Black-Scholes au VIX majoré). Les ETF sur pétrole et managed futures
  supportent des coûts de roulement.
- Les ventes à découvert sont modélisées par un coût d'emprunt seulement, sans rappel des titres ni
  short squeeze.
- Seul le carnet papier, à partir du 20 novembre 2026, jugera honnêtement le fonds.
