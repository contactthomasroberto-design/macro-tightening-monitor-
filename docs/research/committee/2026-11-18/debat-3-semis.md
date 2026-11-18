# Débat du comité du soir, sujet 3 : poche mémoire et concentration IA (17/11/2026, fonds modèle sur papier)

**Question.** Après les résultats de Nvidia (8-K du 17/11 : CA 115,8 Md$, guidance T4 130 Md$, marge brute T4 de 71-72 % contre 74,8 %) et la règle BIS du 16/11, faut-il garder la poche mémoire (HYNIX et SAMSUNG au plancher de 1,5 %, MU 0,6 %, TSM 1,4 %) et la concentration IA (SPY 43,7 % du risque, EEM/EWT/EWY) ?

**Garde-fou d'ancrage.** La poche est la conviction du propriétaire (`sleeves.semis.min: 0.05`, planchers des noms à 0,015 dans `config/portfolio.yaml`). H39 : un tiers du Sharpe vient des 6 noms choisis en 2026. Sans eux, le modèle fait un Sharpe de 0,39 depuis le 20/12/2019, contre 0,44 pour le 60/40.

**Position majoritaire au tour 1.**
- Semis : « mémoire neutre ».
- Asie : « ne pas augmenter ».
- Émergents : neutre.
- Actions US : pas d'avis sur la poche, mais propose de basculer une partie de SPY vers RSP.

La majorité est donc **« garder sans renforcer »**. L'avocat du diable plaide l'inverse.

*Calculs : `/tmp/claude-0/c260/debate3/verify.py`, `nofloor.py`, `nofloor2.py`. Exécution locale en MACRO_MODE=live, prix au 17/11, sans données SEC (MU_REV, NVDA_REV et les tons GDELT sont en échec). Aucun fichier du dépôt n'a été modifié.*

---

## TOUR 2

### semis-tech-analyst
**Je conteste :**
1. us-equity : « SPY … porte 42 % du risque, en plus des semis : l'IA est comptée deux fois ». C'est vrai pour TSM (corrélation hebdomadaire sur 3 ans avec le SOX de 0,80) et pour MU (0,77). C'est faux pour la mémoire coréenne : HYNIX est à 0,59 et SAMSUNG à 0,47. Le risque coréen est idiosyncratique (won, KRX, contrats DRAM), ce n'est pas le bêta de Nvidia.
2. japan-asia : « pas de renfort tant que vol > 50 % ». La covariance réduit déjà la taille des positions volatiles. Une règle de volatilité ajoutée par-dessus compte deux fois le même risque.
3. Je retire ma propre phrase « les chiffres ne concordent pas ».

**Question à japan-asia :** −57 % et −62 % pour HYNIX, est-ce un écart de devise ?

**Ce qui me ferait changer d'avis :**
- des contrats DRAM du T1 2027 en baisse ;
- une marge de Nvidia inférieure à 71 % au T4 expliquée par le prix plutôt que par le coût de la mémoire ;
- une règle BIS étendue à la HBM.

### japan-asia-analyst
**Je conteste :**
1. semis-tech : « Les chiffres ne concordent pas : HYNIX −57 % (desk) contre −62 % (rapport) ». Le won est passé de 1 546 à 1 335 par dollar entre le 25/06 et le 17/11. Le desk mesure en USD, le rapport en KRW. Les deux chiffres sont justes.
2. semis-tech : « la marge baisse à cause du coût de la mémoire, ce qui favoriserait HBM/DRAM ». C'est une hypothèse non prouvée, présentée comme un argument. Une marge en baisse peut aussi venir d'une pression sur les prix exercée par les hyperscalers, et ce serait négatif pour toute la chaîne.

**Question à semis-tech :** quelle source publiée sur les contrats DRAM du T1 2027 soutient « les fondamentaux tiennent » ?

**Ce qui me ferait changer d'avis :** une tendance multi-horizon redevenue positive sur EWY, ou un 2ᵉ PIB japonais (8/12) qui confirme la récession.

### us-equity-analyst
**Je conteste :**
1. semis-tech : « Nvidia légèrement positif, 55 % ». HSBC est passé à Conserver (objectif 170 $). Morgan Stanley a coupé son objectif de 300 à 267 $. Le PDG est par intérim. La réaction après la clôture n'est pas vérifiée. Ce pari dépasse les preuves.
2. emerging-markets : « environ 13 % d'émergents ». Ce chiffre n'est vrai qu'en comptant HYNIX, SAMSUNG et TSM. Ce sont des noms tech, pas une exposition aux émergents.
3. Je maintiens ma propre affirmation : « le marché punit la concentration, pas les actions ».

**Question à emerging-markets :** quelle part de l'exposition émergente est de la tech asiatique ?

**Ce qui me ferait changer d'avis :** RSP qui décroche avec SPY (corrélation sur un mois supérieure à 0,9), ou le BPA à 12 mois en baisse de plus de 3 %.

### emerging-markets-analyst
**Je conteste :**
1. us-equity : « basculer 5 à 8 points de SPY vers RSP ». Cela ne touche ni EEM (4 %), ni EWT, ni EWY. La tech asiatique reste dans le livre par EEM.
2. japan-asia : « Poids faibles (EWY 0,8 %, EWT 1,2 %) ». Ces poids sont exactement ceux de l'équilibre (0,008 et 0,012). Ce ne sont pas des paris. Le risque, lui, n'est pas faible.

**Question à us-equity :** RSP n'est-il pas encore corrélé à SPY à plus de 0,8 ?

**Ce qui me ferait changer d'avis :** une mesure montrant que EEM, EWT et EWY ajoutent moins de 10 % du risque.

### AVOCAT DU DIABLE (risk-manager) : « plancher à zéro, et compter l'IA une seule fois »
La majorité dit « garder sans renforcer ». C'est l'ancrage décrit par H39 : on garde parce que la conviction est celle du propriétaire.

Trois faits :
1. **Les signaux sont en retard.** Sur 12-1, HYNIX, SAMSUNG et EWY sont tous au-dessus de +0,88 alors qu'ils perdent 24 à 34 % sur 3 mois. La tendance multi-horizon est négative sur les quatre lignes asiatiques (HYNIX, SAMSUNG, EWY, EWT).
2. **La vue maison vaut +1,0 sur HYNIX et SAMSUNG.** Elle pèse sur le rendement attendu sans être un signal testé.
3. **Le plancher fixe la poche à au moins 5 %, quels que soient les signaux.** Sans les 6 noms, le modèle est sous le 60/40.

Proposition, sur papier :
- planchers des noms à 0 ;
- **minimum de la poche (5 %) à 0** ;
- un budget unique « IA » qui regroupe semis, EWT, EWY et la part tech de SPY, plafonné à 25 % du risque.

---

## VÉRIFICATION par quant-researcher (code)

| Chiffre contesté | Mesure | Verdict |
|---|---|---|
| HYNIX −57 % ou −62 % | KRW : **−62,4 %** (plus haut le 22/06, ajusté 2 918 367 → 1 098 000). USD : **−56,6 %** | **Les deux sont justes**, c'est la devise (USDKRW 1 546 → 1 335). japan-asia a raison ; semis-tech avait tort de parler de discordance |
| SAMSUNG −39 % ou −47 % | KRW : **−46,5 %** (plus haut le 18/06). USD : **−38,9 %** (plus haut le 02/06) | Les deux sont justes, pour la même raison |
| Trend 12-1 | HYNIX **+0,97** (12-1 +173 %, 3 m −33,9 %, vol 85 %) ; SAMSUNG **+0,99** (+159 %, −28,3 %) ; EWY **+0,88** (+73 %, −24,1 %, vol 53 %) | japan-asia a raison (« +0,9, 12-1 +70 %, −24 %, vol 54 % »). Le « +1,0 » de semis-tech est un arrondi acceptable |
| Tendance multi-horizon (H37 : 4, 13 et 52 sem.) | HYNIX −0,10 ; SAMSUNG −0,11 ; EWY −0,19 ; EWT −0,24 | Le retard du 12-1 est confirmé |
| SPY dans le risque | **43,7 %** (poids 29,0 %) | us-equity disait 42 % : chiffre ancien, le sens reste le même |
| Semis et tech asiatique dans le risque | Semis **16,0 %** (16,2 % en ventilation par source). Noms mémoire : 3,1 % du poids, **10,6 %** du risque. EWT + EWY : 2,0 % du poids, **5,0 %** du risque. Semis + EWT + EWY = **21,0 %**. Avec EEM (6,6 %) : **27,7 %**. Avec SPY et SOXX : **64,9 %** | emerging-markets a raison : 2 % de poids pèse 5 % du risque |
| Corrélation hebdomadaire sur 3 ans avec le SOX | SPY 0,80 ; EWT 0,82 ; TSM 0,80 ; MU 0,77 ; EEM 0,76 ; EWY 0,71 ; HYNIX 0,59 ; RSP 0,58 ; SAMSUNG 0,47 | semis-tech a raison sur la mémoire coréenne. us-equity a raison pour TSM, EWT et SPY |
| Facteur SOX | Bêta du livre au SOX : 0,19. Variance réalisée sur 3 ans expliquée par le SOX : 69 % | Ce chiffre n'est **pas séparable du bêta actions**, puisque la corrélation SPY/SOX vaut 0,80. C'est un indice, pas une preuve |
| RSP et SPY sur un mois (21 séances, du 19/10 au 17/11) | RSP **+1,1 %**, SPY **−4,4 %**, SOXX −15,5 %. Corrélation quotidienne **0,81**, bêta 0,67. Sur un an : 0,77. Sur 63 séances : RSP −2,5 %, SPY −4,5 % | Les rendements d'us-equity sont justes. emerging-markets a raison sur la corrélation : RSP diversifie peu |
| « long mémoire à 3,6 % » | En local : HYNIX 1,5 + SAMSUNG 1,5 + MU **0,10** = 3,1 % (TSM 1,67 %). Les chiffres du sujet (MU 0,6, TSM 1,4) donnent 3,6 % | Les deux sont cohérents. L'écart vient du terme micro sans données SEC en local. Le chiffre officiel est celui de GitHub |
| « environ 13 % d'émergents » | 13,4 % en comptant HYNIX, SAMSUNG et TSM ; **8,7 %** en ETF seuls (EEM 4, EWT 1,2, EWY 0,8, INDA 1,2, EWZ 1,54) | us-equity a raison sur la définition |
| Proposition du risk-manager | Planchers des noms à 0 : HYNIX 0,17 %, SAMSUNG 0,68 %, MU 1,09 %, TSM 2,50 %. **La poche reste à 5,00 %** et son risque passe de 16,0 à **16,8 %**. Si l'on met aussi le minimum de la poche à 0 : poche à 3,66 %, risque 12,8 %, SPY 42,3 %, vol 8,41 % (inchangée), TE 3,06 % | Le plancher des noms ne réduit pas le risque IA : il le **déplace** vers MU et TSM, plus corrélés au SOX. Il faut retirer le minimum de la poche pour réduire le risque, et le gain n'est que de 3,2 points |

**Web (2 recherches).**
- La réaction de Nvidia après la clôture du 17/11 **n'est pas trouvée**. Dernier prix vu : clôture de 162,85 $ le 13/11 ([FourWeekMBA](https://fourweekmba.com/nvidia-stock/), source secondaire). La date de publication du 17/11 est confirmée par [Kiplinger](https://www.kiplinger.com/news/live/nvidia-earnings-live-updates-and-commentary-november-2026).
- Contrats DRAM : le [tracker de novembre de Counterpoint](https://counterpointresearch.com/cn/reports/memory-price-tracker-november) indique que les premières négociations pour 2027 « signalent une nouvelle hausse au T1 2027 » (chiffres non visibles). TrendForce prévoyait +13 à 18 % pour la DRAM PC au T4 2026. Des réductions de 20 à 40 % de la production de DRAM PC chez Samsung et SK hynix en 2027 sont évoquées ([Sammyfans, 30/10](https://www.sammyfans.com/2026/10/30/dram-nand-prices-samsung-sk-hynix-pc-dram-2027/amp/)). Preuve faible à moyenne, de seconde main.

---

## TOUR 3

**semis-tech-analyst.** Je corrige « les chiffres ne concordent pas » : c'est la devise, japan-asia a raison. Sur les contrats DRAM, je réponds par Counterpoint : les négociations pour 2027 signalent une hausse au T1. Cela contredit mon « rien de publié », mais reste de seconde main et sans chiffre. Je maintiens que la mémoire coréenne n'est pas « l'IA comptée deux fois » : la corrélation au SOX est de 0,59 et 0,47. J'abandonne en revanche l'argument contre la levée du plancher : elle ferait monter MU et TSM, ce qui augmenterait le risque du facteur SOX. Je baisse le pari NVDA à 50 %, faute de réaction de cours vérifiée. Confiance de 45 à **40 %**.

**japan-asia-analyst.** Je maintiens le diagnostic de retard : multi-horizon EWY −0,19, EWT −0,24 contre +0,88 et +0,98 sur 12-1. J'accepte la critique d'emerging-markets : 0,8 et 1,2 % sont des poids d'équilibre, pas des paris, et ils portent 5 % du risque. J'accepte aussi celle de semis-tech sur la règle de volatilité : je retire « pas de renfort tant que vol > 50 % » comme règle et la garde comme simple observation. Sur la cause de la baisse de marge chez Nvidia, aucune des deux thèses n'est prouvée. Confiance pour la Corée maintenue à **45 %**.

**us-equity-analyst.** Je corrige : SPY porte 43,7 % du risque, pas 42 %. « L'IA comptée deux fois » vaut pour SPY, TSM, EWT et MU (corrélation au SOX de 0,77 à 0,82), pas pour HYNIX et SAMSUNG. Emerging-markets a raison : RSP reste corrélé à 0,81 avec SPY, avec un bêta de 0,67. La bascule vers RSP réduit l'exposition aux méga-capitalisations, pas le risque actions. Je ramène ma proposition à 3 à 5 points, à tester sur papier. Confiance de 60 à **55 %**.

**emerging-markets-analyst.** Je corrige : 8,7 % en ETF, 13,4 % seulement avec HYNIX, SAMSUNG et TSM, et ces trois noms ne devraient pas être comptés comme des émergents. Je maintiens : EEM, EWT et EWY pèsent 11,6 % du risque (6,6 + 2,8 + 2,2) pour 6 % du poids. Le seuil de 10 % qui me ferait changer d'avis n'est donc pas atteint. Ma phrase « restrictions … expliquent le −5,3 % » sur MCHI est une attribution sans test : je la retire. Confiance maintenue à **45-55 %**.

---

## Synthèse pour le CIO (5 lignes)

1. Les chiffres contestés sont **tous justes à la devise près**. HYNIX fait −62 % en KRW et −57 % en USD ; SAMSUNG −47 % et −39 %. Ce n'est pas une erreur de données, il faut simplement afficher la devise.
2. Le **retard du signal est confirmé**. Sur 12-1, HYNIX, SAMSUNG et EWY sont entre +0,88 et +0,99, alors que la tendance multi-horizon est négative (−0,10 à −0,24). La poche tient aujourd'hui grâce au 12-1, à la vue maison (+1,0) et au plancher.
3. Lever seulement le plancher des noms **ne réduit pas** le risque IA : la poche reste à 5 % et son risque passe de 16,0 à 16,8 %, via MU et TSM. Il faut aussi retirer le minimum de la poche : risque 12,8 %, soit −3,2 points.
4. La concentration réelle est d'environ 28 % du risque (semis, EWT, EWY et EEM), et 65 % avec SPY. Elle n'est pas séparable du bêta actions (corrélation SPY/SOX 0,80). RSP est un faible diversifiant (corrélation 0,81 avec SPY).
5. Recommandation : **garder sans renforcer jusqu'au 20/11**. Pré-enregistrer la levée du minimum de la poche et H56 (multi-horizon) avant tout changement. La réaction de Nvidia après la clôture et les contrats DRAM du T1 restent **non vérifiés** : il faut les relire demain avant toute décision.
