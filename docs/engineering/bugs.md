# Registre des bugs

Tenu par l'équipe ingénierie (software-engineer, qa-engineer). Chaque correction : symptôme, cause, correctif,
test de non-régression. La détection automatique tourne à chaque rafraîchissement (docs/engineering/health.md).

| Date | Symptôme | Cause | Correctif | Test |
|---|---|---|---|---|
| 2026-11-17 | Famille de vues « régime » toujours vide | Masque de validité appliqué après le décalage de publication | Masque avant le décalage (version 0.3.1) | test_regime_series_is_not_empty_on_monthly_data |
| 2026-11-17 | Refresh en échec sur l'indice des conditions financières | Une variable sans donnée exploitable vidait toutes les lignes | Variable écartée et signalée | test_fci_lite_survives_a_lagging_variable |
| 2026-11-18 | CPI « 12 mois » du desk = 13 mois (octobre 2025 non collecté) | Variation comptée en lignes | Variation en mois calendaires (desk.monthly_change) ; le modèle n'était pas touché | test_monthly_change_does_not_bridge_a_missing_month |
| 2026-11-18 | Régime affiché daté dans le futur (desk, rapport) | Série décalée par le délai de publication, dernier point affiché | Affichage limité à la date du modèle | contrôle health « regime … not dated after » |
| 2026-11-18 | Spreads souverains présentés comme quotidiens | Moyennes mensuelles BCE | Libellé explicite dans le desk | — (affichage) |
| 2026-11-18 | Fausse alerte de saut sur les titres coréens | Comparaison au proxy US le même jour alors que Séoul clôture avant New York | Proxy comparé le jour même et le suivant | test_jump_explained_by_next_day_proxy_is_not_an_anomaly |
| 2026-11-18 | Prix ajustés négatifs (SK Hynix 2000-2002) | Donnée source | Prix ≤ 0 écartés dans usd_prices | test_usd_prices_drop_non_positive_prices |
| 2026-11-18 | Vue ING sur le franc encodée sur FXF | Prévision EUR/CHF appliquée à CHF/USD | Vue corrigée à 0 (comité) | — (donnée) |
