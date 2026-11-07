# prep/sandbox/

## Responsabilité
Isolation Blender Linux Xvfb.

## Entrées
version exacte et fixture.

## Sorties
bureau graphique isolé et état vérifiable.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/preparation.md) et [guide des agents](../../AGENTS.md).

## État et validation
`BlenderSandbox` exécute les scripts bpy de confiance avec JSON, timeout, nettoyage et environnement sans variables *_API_KEY. Reset vide et checkpoints par étape ; vérification réelle sous Blender 4.5.9 dans tests/prep. Ce headless ne vérifie pas les gestes UI ni macOS.
