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

## Accessibilité native
`accessibility.AccessibilityNode` et `PhysicalBounds` typent l'entrée géométrique.
`node_rect()` convertit les bornes physiques `{x,y,w,h}` en `Rect` ;
`normalized_center(node, crop)` fournit le centre [0,1000] relatif au crop physique.
Le nœud entier doit être contenu dans le crop, sinon `ValueError` ; les bornes manquantes
ou invalides sont refusées. Aucune mise à l'échelle supplémentaire : utiliser ensuite
`normalized_point()` pour la conversion native, y compris à origine négative et scale 2.

Les tiers restent état structuré, accessibilité native, vision ; les décisions sont
dans l'engine Python, les lectures/actions OS dans le client Rust. Un snapshot partiel
n'est pas une preuve d'absence. Les champs sécurisés ne fournissent jamais de valeur.
Voir les [tests et limites du capteur](../../desktop/README.md#capteur-daccessibilité-générique).
Test local sans cloud : `HCOMPANY_LIVE=1 pytest -q -s desktop/tests -m live`.
Le test Calc utilise le fallback Rust et non un aller-retour engine/Tauri complet.
Mesures locales Linux : snapshots p50 812,377 ms / p95 878,204 ms sur cinq essais,
get 10,030 ms, capture fenêtre 366,734 ms. Les conversions Python sont vérifiées
par tests purs ; aucune mesure de leur temps d'exécution n'est revendiquée.
