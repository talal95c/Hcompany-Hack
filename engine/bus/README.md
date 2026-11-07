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
Validation JSON Schema stricte avec registre de références partagé. TCP JSON lignes
et WebSocket desktop disponibles dans `servers.py` : authentification, limites,
déduplication bornée, trous de séquence et corrélation avec délai. Les deltas de scène
consécutifs sont agrégés sans supprimer les acquittements ni les commandes.
Question ouverte : le hello add-on ne comporte pas de jeton dans le contrat v1 ;
seul son identifiant de session est vérifiable. Le socket reste lié à ENGINE_HOST.
Tests : `pytest -q tests/engine/test_foundation.py`.
