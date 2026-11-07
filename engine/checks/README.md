# engine/checks/

## Responsabilité
Bibliothèque de vérification.

## Entrées
snapshot et paramètres.

## Sorties
pass/fail/unknown et détail.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/engine.md) et [guide des agents](../../AGENTS.md).

## État et validation
`SceneState.apply()` construit l'état depuis snapshot, deltas, mode et sélection.
Un trou de révision rend les checks inconnus jusqu'au prochain snapshot. Les huit
checks de `NAMES` sont disponibles via `evaluate()`, sans appel réseau. Le progrès
pertinent est exposé par `progress_signature()` ; le nom d'objet n'est jamais une preuve.

Tests : `pytest -q tests/engine/test_checks.py`. Question ouverte pour le propriétaire
des contrats : le schéma de leçon v1 n'autorise que `object_exists` ; les autres
checks restent accessibles par API, sans assouplissement de la validation des leçons.
