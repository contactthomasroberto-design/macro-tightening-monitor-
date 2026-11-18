# stress-testing-analyst — 9 stress + 3 nouveaux (17/11/2026)

*Code du dépôt (`fund_process.forward_stress`, covariance 156 semaines, put 15,3 % de la VL), fichier YAML non modifié. Aucune recherche web.*

**1. Vu.** Recalcul identique à ±0,3 pt. Le pire scénario est le crédit (−15,9 %, seul hors limite). Le livre fait mieux que le 60/40 dans 7 stress prospectifs sur 9, mais moins bien sur le yen (−4,6 % contre −3,9 %) et la mémoire (−3,7 % contre −2,5 %). En crises rejouées, il fait pire dans 5 sur 8 : Covid −24,3 % contre −21,5 %, T4 2018 −10,7 % contre −8,9 %. Il ne fait nettement mieux qu'en 2022 (−15,2 % contre −21,7 %).

**2. Manqué.**
- **Les stress prospectifs flattent le livre.** Les actifs non choqués suivent la covariance sur 3 ans, où la corrélation SPY-AGG vaut +0,07. Ces variations conditionnelles sont faibles. Les crises rejouées, elles, punissent les poids semis, EM et BNO.
- Le stress de taux choque TLT, mais pas l'AGG, qui pèse 27,6 % du livre.
- La perte du stress crédit vient du SPY, pas du crédit.

**3. Nouveaux scénarios (format YAML, chocs en %).**
- `rates_poscorr_2022` : rendements 03/01–14/10/2022 relevés dans les données du dépôt. Chocs : `{SPY: -24, TLT: -32, IEF: -17, AGG: -16, TIP: -13, VNQ: -33, UUP: 19}`. Livre −14,4 % (dont put +2,9), 60/40 −22,6 %, AGG −4,4 pts. À ×0,5 : livre −7,6 %, 60/40 −11,1 %. Pas de 1994 : TLT ne commence qu'en 2002.
- `memory_export`, calibré sur juin-déc. 2018 (HYNIX −37, SAMSUNG −28, MU −49, EWY −19, SPY −8) et sur juin-nov. 2026 (HYNIX −54, EWY −38). Chocs : `{HYNIX: -50, SAMSUNG: -40, MU: -50, EWY: -25, TSM: -25, EWT: -20, SOXX: -30, SPY: -8}`. Livre −5,8 %, 60/40 −5,0 %, dans la tolérance de 2 pts.
- `em_election`, calibré sur EWZ −25,8 % depuis le 23/10/2026. Chocs : `{EWZ: -27, EEM: -5}`. Livre −2,4 %, 60/40 −2,1 %.

**4. Vue.** Le risque est sous-estimé quand la corrélation actions-obligations est positive. Aucun scénario ne dépasse 15 %, mais celui de 2022 rejoué s'en approche, à −14,4 %. Confiance 60 %.

**5. Changerait d'avis si** une covariance de régime (core CPI > 3 %) donne une corrélation SPY-AGG négative.

**6. Implication.** Les stress sont en retard sur le régime d'inflation. Il faut ajouter `rates_poscorr_2022` à la config, journalisé dans `research_log`, et faire tourner les stress aussi sur la fenêtre « inflation > 3 % ».

**7. PARI NOTABLE.** HYNIX (return, below, −0,15) du 17/11/2026 au 17/02/2027 : 30 %.

```yaml
views: []
```
