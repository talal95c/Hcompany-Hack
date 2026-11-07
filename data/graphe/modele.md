# Modèle du graphe (proposition)

Statut : proposé, non implémenté. Stockage non décidé.

## Nœuds
| Nœud | Clé | Exemple | Rempli par |
|---|---|---|---|
| `App` | `app`, `app_version` | `blender` 4.5.9 | ui-map, leçons |
| `Area` | type de zone Blender | `VIEW_3D`, `PROPERTIES` | événements add-on |
| `Menu` | `menu_id` | `VIEW3D_MT_add` | ui-map |
| `Element` | description stable (jamais des pixels) | « Add › Mesh › Torus » | ui-map, GroundCUA, ScreenSpot-Pro |
| `Operator` | `idname` | `MESH_OT_primitive_torus_add` | ui-map, preuves |
| `Check` | `name` + `params` | `object_exists {type: MESH, primitive: torus}` | preuves |
| `Step` | `lesson_id/step_id` | `donut/add_torus` | leçons |
| `Skill` | `skill_id` | `add_torus` | leçons, `engine/learner` |
| `Task` (hors Blender) | `source/id` | Spider2-V `excel/0326d92d…` | Spider2-V, OSWorld |

## Liens
| Lien | De → vers | Source | Confiance |
|---|---|---|---|
| `IN_MENU` | Element → Menu | ui-map | exacte |
| `TRIGGERS` | Element → Operator | ui-map | exacte |
| `VERIFIED_BY` | Step → Check | preuves | exacte |
| `USES` | Step → Operator | preuves | exacte |
| `NEXT` | Step → Step | leçons | exacte |
| `TEACHES` | Step → Skill | leçons | exacte |
| `CHANGED_IN` | Element → App(version) | `diff_ui_maps` | exacte |
| `LOCATED_IN` | Element → Area | événements add-on | observée |
| `SEEN_AT` | Element → observation de position | `TargetCache` + check | observée, datée |
| `PHRASED_AS` | phrase → Element | ScreenSpot-Pro, consignes de leçons | annotée |
| `NEAR` | Element → Element | GroundCUA (bbox d'une même capture) | annotée |

Chaque lien porte `source`, `revision`, `confidence`, `last_verified_at`.

## Utilisation attendue par l'engine
1. Étape à guider → `Step` → `USES` → `Operator` → `TRIGGERS` (inverse) → `Element` → `IN_MENU`.
2. Si un `menu_id` est connu : `wm.call_menu`, pas de Holo.
3. Sinon, si `LOCATED_IN` est connu : capture recadrée sur la zone, puis Holo.
4. Sinon : Holo sur la capture entière.
5. Toujours : check de l'étape. Si le check passe, on renforce les liens utilisés ; sinon on baisse leur confiance.

Les points 2 et 3 sont des hypothèses : le gain doit être mesuré dans `bench/` avant d'être annoncé.
