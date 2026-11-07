# engine/cache/

## Responsabilité
Cache invalidable.

## Entrées
audio et cible/contextes UI.

## Sorties
hit valide ou miss.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/engine.md) et [guide des agents](../../AGENTS.md).

## État et validation
Caches LRU bornés : `TargetCache` compare version, taille, échelle, cible, origine,
moniteur, langue, révision UI, visibilité et contexte de menu. `on_event()` invalide
sur modification des régions ou du contexte. `AudioCache` indexe octets et référence
audio par texte. `Preloader` lance une localisation sans commande native et annule
la tâche précédente au changement de génération ; l'orchestrateur fournit la capture
N+1 et un appel borné. Aucun menu n'est ouvert par ce module.
Tests : `pytest -q tests/engine/test_cache.py`.
