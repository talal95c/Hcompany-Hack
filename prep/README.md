# prep/

## Responsabilité
Pipeline de préparation Linux cloud.

## Entrées
tutoriel et version cible.

## Sorties
leçon prouvée ou rapport pending.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../docs/architecture/preparation.md) et [guide des agents](../AGENTS.md).

## État et validation
Sandbox Blender headless, cartes UI versionnées, preuves par différence, recherche Linkup et demandes de réparation locales disponibles. Validation : `ruff check .` et `pytest -q tests/ -m "not live"` ; réseau opt-in via marqueur `live`. Les étapes UI modifiées restent pending, sans preuve visuelle simulée.
