# Robustesse du modèle et tests pré-enregistrés (calcul GitHub)

*`quant-researcher` — 18/11/2026 06:40 UTC. Note calculée par GitHub Actions à partir des données et des modèles du dépôt : aucune opinion, les positions viennent des règles. Le comité du soir la discute.*

**En bref** : Deflated Sharpe 0.01 sur 10 configurations (< 0,95 : pas de preuve d'alpha au-delà de la chance).

- Backtest : +8,4 %/an, drawdown max -18,6 % (60/40 -38,2 %), Sharpe 0.73 vs 0.47.
- Deflated Sharpe 0.01 sur 10 configurations (< 0,95 : pas de preuve d'alpha au-delà de la chance).
- H29 memory cycle : IC +0.24, t = +0.9, n = 17.
- Variante long only (H35) : Sharpe 0.73, drawdown -17,7 %.
- Variante no tail hedge (H34) : Sharpe 0.81, drawdown -18,1 %.
- Variante no drawdown overlay : Sharpe 0.77, drawdown -21,3 %.
- Variante no views, no overlay (core) : Sharpe 0.59, drawdown -34,1 %.
- Variante v0.2 style: long only, monthly, trend/macro/micro : Sharpe 0.77, drawdown -18,3 %.

**À surveiller / à débattre**

- Deflated Sharpe sous 0,5 : rester prudent sur les tailles.
