# prep/ui_map/

## Responsabilité
Cartes menus par version.

## Entrées
Blender exact et menus.

## Sorties
descriptions, menu_id et diff de chemins.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/preparation.md) et [guide des agents](../../AGENTS.md).

## État et validation
`dump_ui_map`, `diff_ui_maps`, `step_signature` : menus extraits par AST, signatures RNA et empreintes des primitives calculées dans Blender. Cache JSON par version dans ~/.cache/hcompany-prep/ui_maps. Tests de diff et extraction réelle dans tests/prep ; extraction statique conservative, pas une preuve visuelle.
