# Standard des notes de recherche

Le niveau attendu est celui d'un analyste senior de hedge fund : de la matière, des chiffres vérifiables,
une thèse qui se défend, et une conclusion qui se traduit en position. Chaque note est **écrite dans le dépôt**,
jamais dans un dossier temporaire. Elle est lue par le CIO, débattue en comité et suivie jusqu'à la décision.

## Où écrire
- Recherche approfondie de la journée : `docs/research/notes/<AAAA-MM-JJ>/<agent>.md`
- Notes et débats du comité du soir : `docs/research/committee/<AAAA-MM-JJ>/note-<agent>.md` et `debat-<n>-<sujet>.md`
- Notes quant : `docs/research/quant/notes/<AAAA-MM-JJ>-<agent>.md`

## Longueur
- Recherche approfondie : 1 500 à 3 000 mots, tableaux compris.
- Note de comité : 800 à 1 500 mots.
- Note quant : sans limite, code et chiffres à l'appui.
La longueur ne remplace pas la matière : chaque paragraphe apporte un fait, un chiffre ou un argument.

## Plan obligatoire
1. **Thèse en trois lignes** : ce que nous pensons, à quel horizon, avec quelle confiance (0-100 %).
2. **Ce qui a changé** depuis la note précédente du même auteur (lire la précédente avant d'écrire).
3. **Les données** : un tableau au moins, avec les chiffres du dépôt (desk, rapport du jour) et des sources
   primaires datées (statistiques officielles, banques centrales, comptes d'entreprises, recherche publiée).
4. **L'analyse** : fondamentaux, valorisation (par rapport à l'historique et aux pairs), positionnement et flux,
   technique (tendance, momentum, volatilité), catalyseurs datés des 3 prochains mois.
5. **Le consensus et notre écart** : ce que disent les banques et les gérants (vues datées et sourcées), et
   pourquoi nous sommes d'accord ou non.
6. **Les scénarios** : central, haussier, baissier, chacun avec sa probabilité et l'effet attendu sur les
   instruments de l'univers, en pourcentage.
7. **Les risques et ce qui nous ferait changer d'avis** : des seuils précis (un niveau, une statistique).
8. **L'implication pour le portefeuille** : comparer avec nos poids et nos signaux actuels (desk, section
   « 1 bis » du rapport). Sommes-nous bien positionnés, en avance ou en retard ?
9. **Propositions** (bloc YAML, obligatoire) : ce que le comité doit trancher.
   ```yaml
   proposals:
     - ticker: EWJ            # instrument de config/portfolio.yaml
       direction: above      # above / below
       threshold: 0.03       # rendement décimal à l'horizon
       horizon: 2027-02-18
       probability: 0.62
       rationale: "BoJ, gouvernance, flux étrangers ; voir sections 4 et 6"
   ```
10. **Vues publiées** (bloc YAML `views:`) : seulement des positions explicites d'institutions identifiables,
    datées de moins de 30 jours, avec le lien.
11. **Sources** : la liste des liens datés.

## Règles
- Ne jamais inventer un chiffre. Dire quand la preuve est faible ou de seconde main.
- Pas de contenu payant ni de scraping interdit.
- Pas de recommandation à quiconque : portefeuille modèle sur papier.
- Toute anomalie de donnée ou de code repérée est signalée à l'équipe ingénierie (docs/engineering/bugs.md).

## Du travail des analystes à l'allocation
- Le CIO lit **toutes** les notes du jour (recherche approfondie, comité, desk) avant le comité.
- Chaque proposition est soit **adoptée** et enregistrée comme décision du comité (archive/decisions.csv,
  agent chief-investment-officer), ce qui la fait entrer dans les poids, soit **rejetée avec sa raison**.
- La note du soir contient le tableau « Propositions des analystes » : auteur, proposition, adoptée ou rejetée,
  raison, décision enregistrée.
- Chaque proposition est aussi notée comme pari de son auteur : le score de Brier dit qui a raison au fil du
  temps, et le CIO pondère les avis en conséquence.
