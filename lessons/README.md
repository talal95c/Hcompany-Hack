# lessons/

## Responsabilité
Stockage des artefacts versionnés.

## Entrées
résultats de preuve et compilation.

## Sorties
leçons, audio et manifestes de preuves.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../docs/contrats/lecon.md) et [guide des agents](../AGENTS.md).

## État et validation
Pas encore de code. Les modules décrits sont une cible, pas une implémentation disponible. Ajouter tests nominal/vide/erreur et timeout avant intégration ; ne pas remplacer un check par une déclaration de modèle.
