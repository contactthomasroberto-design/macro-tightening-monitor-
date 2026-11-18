# Leçons du comité

Mémoire de l'équipe : ce que les paris notés, les revues de pertes et les verdicts du laboratoire ont appris.
Le comité la relit au début de chaque séance et y ajoute au plus 3 leçons par soir, chacune datée, sourcée
(pari, revue de perte ou hypothèse concernés) et formulée comme une règle de conduite vérifiable.

## 2026-11-17
- **Vérifier que chaque famille de signaux produit vraiment des vues avant d'interpréter un backtest.** La
  famille « régime » était vide depuis sa création (bug d'alignement des dates, corrigé en 0.3.1) : les
  verdicts H33-H44 du jour avaient été obtenus sans elle. Source : docs/MODEL_CHANGELOG.md, 0.3.1.
- **La complexité ne se justifie que par les preuves.** La v0.3 (shorts, 51 instruments, hebdomadaire) ne bat
  pas la variante simple façon v0.2 ; le put S&P 500 et les shorts n'apportent rien de mesurable (H33-H35).
- **Séparer la performance du biais de sélection.** Un tiers de l'avantage de Sharpe venait des six valeurs
  choisies en 2026 (H39) : toujours lire le chiffre « sans les choix de 2026 ».
