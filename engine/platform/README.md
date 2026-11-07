# engine/platform/

## Responsabilité
Adaptation des métadonnées OS.

## Entrées
rectangles, moniteur et scale du desktop.

## Sorties
repères cohérents, sans injection Python.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/engine.md) et [guide des agents](../../AGENTS.md).

## État et validation
`operating_system()` distingue macOS, Linux, Windows et plateformes non prises en charge.
`Rect` / `Monitor` valident valeurs finies et échelles positives ; `normalized_point()`
convertit [0,1000] → crop physique → bureau logique, borné au dernier pixel.
`blender_region()` inverse Y une seule fois depuis une région Blender bas-gauche.
Les crops chevauchant deux moniteurs sont refusés. Aucune capture ni injection Python.

Tests : `pytest -q engine/platform` (Retina, origine négative, dernier pixel, inversion
Y, coordonnées non finies, échelles invalides et frontière moniteur).
