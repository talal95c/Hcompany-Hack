# engine/bus/

## Responsabilité
Bus et transports.

## Entrées
messages validés.

## Sorties
événements routés et reconnexion.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/engine.md) et [guide des agents](../../AGENTS.md).

## État et validation
Bus asyncio à files bornées par abonné, compteur de pertes et signalement de saturation.
Validation JSON Schema stricte avec registre de références partagé. Les transports restent à intégrer.
Tests : `pytest -q tests/engine/test_foundation.py`.
