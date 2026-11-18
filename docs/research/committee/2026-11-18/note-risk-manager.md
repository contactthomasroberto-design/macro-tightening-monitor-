# risk-manager — contrôle indépendant (comité du 17/11/2026)

*Recalcul local live (`portfolio_bundle`, cible au 20/11). Aucune recherche web : calcul seulement.*

**1. Vu et important.** Les chiffres du desk se vérifient : vol ex ante 8,41 % (égale au 60/40, plafond saturé), TE 3,19 %, VaR 95 % à 1 semaine 1,83 %, ES 2,71 %. Le seul dépassement est le stress crédit à −15,9 % (−15,7 % au desk), contre −20,5 % pour le 60/40. Il vient de l'actif risqué (SPY −8,7 pts, VGK −3,3, EWJ −1,4) et pas du crédit (0 % HYG/LQD). C'est le prix d'avoir 60 % d'actions nettes avec un plafond de 15 %. Le put rapporte +3,8 pts ; sans lui, −19,7 %.

**2. Manqué.**
- **Couverture duration.** La corrélation SPY-AGG est de −0,60 sur 13 semaines, −0,21 sur 26, +0,14 sur 52 et +0,07 sur 156. Les stress supposent qu'elle est négative. Si on rejoue 2022 (corrélation positive), l'AGG coûte −4,4 pts au lieu d'amortir.
- **Concentration IA comptée deux fois.** Les titres semis, EWT et EWY ne pèsent que 7,1 % du poids, mais 21,2 % du risque. Il faut y ajouter SPY (43,7 %), dont le R² contre SOXX est de 0,62 sur 3 ans. EEM (6,6 %) recouvre aussi Taïwan et la Corée. L'exposition réelle à l'IA dépasse donc nettement 21 %, et le risk budget ne la mesure pas.
- **Ordre initial du 20/11.** Sans livre précédent, le premier ordre achète la cible entière, soit 100 % de brut. Cette cible est presque l'équilibre, alors que le livre du backtest diffère de 35 %. Liquidité : BNO à 4 % pour 100 M$ représente 13 % d'un ADV de 30 M$. C'est au-delà de la règle (1 % de l'ADV, 1 jour à 10 % de participation).
- **Brier.** `archive/decisions.csv` ne contient que l'en-tête. Aucun pari n'est scoré : la calibration du comité reste inconnue.

**3. Vue.** Le mandat est respecté sauf le stress crédit, un dépassement de structure. Le risque principal cette semaine est un choc commun taux et IA (Fed le 9/12, Nvidia). Confiance 65 %.

**4. Changerait d'avis si** la corrélation sur 52 semaines repasse sous −0,2.

**5. Implication.** Le livre est en retard sur le régime. La couverture est calibrée pour un monde à corrélation négative. Il faut : initialiser `w_prev` sur le livre du backtest ; ajouter un stress à corrélation positive ; agréger l'IA (SPY, semis, EM Asie) dans le risk budget ; et alimenter `decisions.csv` dès ce soir.

**6. PARI NOTABLE.** AGG (return, below, 0,0) du 17/11 au 18/12/2026 : 45 %.

Question aux quants : peut-on ajouter au risk budget un facteur IA estimé par régression sur SOXX ?

```yaml
views: []
```
