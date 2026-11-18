# Santé du système — 18/11/2026 22:10 UTC

11 contrôles OK sur 13. Généré par scripts/health_check.py à chaque rafraîchissement ; l'équipe ingénierie corrige chaque échec avec un test (docs/engineering/bugs.md).

| Contrôle | État | Détail |
|---|---|---|
| view family 'trend' produces views | ✅ | 51 instruments |
| view family 'macro' produces views | ✅ | 50 instruments |
| view family 'regime' produces views | ✅ | 51 instruments |
| view family 'value' produces views | ✅ | 29 instruments |
| view family 'carry' produces views | ✅ | 10 instruments |
| view family 'micro' produces views | ✅ | 6 instruments |
| view family 'house' produces views | ✅ | 31 instruments |
| regime series is computed | ✅ | 4093 weeks |
| regime used by the model is not dated after the as-of date | ✅ | label 'growth down, inflation down' at 2026-11-20 |
| no non-positive raw prices (masked in the model, to clean at the source) | ❌ | HYNIX |
| universe prices less than a week old | ✅ | none |
| monthly macro series without missing months (36 months) | ❌ | CPIAUCSL: 2025-10; CPILFESL: 2025-10; UNRATE: 2025-10 (changes must use calendar months, see desk.monthly_change) |
| every desk note computed | ✅ | all |
