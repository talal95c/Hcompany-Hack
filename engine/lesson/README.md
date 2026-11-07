# engine/lesson/

## Responsabilité
Machine de progression.

## Entrées
leçon et checks.

## Sorties
étape/génération courante.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/engine.md) et [guide des agents](../../AGENTS.md).

## État et validation
Chargement strict des leçons prouvées, table des transitions, garde de précondition de mode,
génération et avancement dédupliqué disponibles. Orchestration live restant à intégrer.
Tests : `pytest -q tests/engine/test_foundation.py`.
