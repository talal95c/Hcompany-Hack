# Contrat leçon v1
Statut : JSON Schema exécutable v1 dans contracts/lesson.schema.json.
| Champ | Type / obligatoire | Sens et contraintes |
|---|---|---|
| schema_version | string oui | "1.0", major incompatible refusé |
| lesson_id / revision | string / integer oui | identité stable / révision immuable positive |
| title / language | string oui | titre affiché / locale |
| blender_version | string oui | version exacte prouvée, pas une plage supposée |
| status | enum oui | draft, pending, failed, proven |
| source | object oui | uri, sha256, droits d'usage à vérifier |
| skills | string[] oui | compétences travaillées |
| steps | object[] oui | ordonnées et non vides ; id unique |
| proof | object oui | method, evidence_ref, ui_path_verified ; artefact versionné |
## Étape
| Champ | Type / obligatoire | Sens |
|---|---|---|
| id / skill_id | string oui | identité étape et compétence |
| instruction | string oui | consigne utilisateur |
| preconditions | object oui | mode et contraintes avant action |
| check | object oui | name whitelist + params typés ; pas de code généré |
| target | object oui | description, area_type, region_type ; aucune coordonnée persistée |
| why | string oui | explication compilée |
| audio_ref | string ou null oui | chemin relatif contrôlé ; null tant que TTS absent |
| known_errors | object[] oui | code, check, hint ; vide autorisé |
| procedure_ref | string oui | procédure autorisée de secours |
| proof | object oui | statut, méthode, evidence_ref et ui_path_verified par étape |
| challenge | boolean non | false par défaut ; réussite sans aide débloque la compétence |
| help | object non | menu_id optionnel (carte UI de la version prouvée), safe_demo=false par défaut, checkpoint_id ; safe_demo=true exige un checkpoint |

## Whitelist des checks
Les paramètres sont fermés et partagés avec les checks d'erreurs connues. Sauf mode_is,
les nouveaux checks acceptent les filtres optionnels type et primitive.
| name | params |
|---|---|
| object_exists | type et primitive (obligatoires, compatible v1) |
| object_count | count entier ≥0 obligatoire |
| modifier_present | modifier_type obligatoire, params scalaires/vecteurs optionnels |
| material_color | color RGBA (4 nombres entre 0 et 1) obligatoire |
| shading_smooth | smooth boolean, true par défaut |
| mode_is | mode obligatoire |
| selection | active boolean optionnel (sinon sélection entière) |
| object_transform | au moins un vecteur location, rotation ou scale de 3 nombres |
modifier_present, material_color et object_transform acceptent tolerance ≥0, par défaut 1e-5.

Au chargement d'une leçon proven, le runtime refuse les id dupliqués et exige des
preuves non vides existantes, relatives au dossier de la leçon (sans sortie par symlink).
source.sha256 doit être le SHA256 réel de l'archive source locale désignée par source.uri
(chemin relatif ou URI file). Pour une URI distante, load_lesson exige source_path explicite
pointant l'archive téléchargée : aucun accès réseau implicite ni hash illustratif accepté.
La version Blender du hello doit correspondre exactement à blender_version avant toute
validation d'étape ou mémorisation de réussite. Les exemples ci-dessous restent structurels.
Les primitives exigent provenance et mesh.verts/edges/polys cohérents ; l'absence de edges
donne unknown. Le contrôle d'Euler (0 pour tore, 2 pour sphère/cube) complète les contraintes
de comptage ; il ne prétend pas reconstruire toute la géométrie à partir de ces résumés.
Les métadonnées help sont consommées par le runtime, sans injection de contexte dans les tests.
Une scène sans objet ne valide pas object_exists. Un objet MESH arbitraire ne prouve pas primitive=torus ; sans provenance et géométrie suffisantes, résultat unknown. Ne pas utiliser le nom de l'objet comme preuve.
## Exemple complet de leçon minimale
```json
{
  "schema_version": "1.0",
  "lesson_id": "donut",
  "revision": 1,
  "title": "Créer un donut",
  "language": "fr-FR",
  "blender_version": "5.2.3",
  "status": "proven",
  "source": {"uri": "fixture://donut", "sha256": "EXEMPLE_NON_PUBLIE"},
  "skills": ["add_primitive"],
  "steps": [{
    "id": "add_torus",
    "skill_id": "add_primitive",
    "instruction": "Ajoute un tore dans la vue 3D.",
    "preconditions": {"mode": "OBJECT"},
    "check": {"name": "object_exists", "params": {"type": "MESH", "primitive": "torus"}},
    "target": {"description": "Ajouter › Maillage › Tore", "area_type": "VIEW_3D", "region_type": "WINDOW"},
    "why": "Le tore fournit la forme annulaire du donut.",
    "audio_ref": null,
    "known_errors": [{
      "code": "cube_instead_of_torus",
      "check": {"name": "object_exists", "params": {"type": "MESH", "primitive": "cube"}},
      "hint": "Tu as ajouté un cube. Choisis Tore dans Maillage."
    }],
    "procedure_ref": "donut/add_torus",
    "proof": {"status": "proven", "method": "bpy", "evidence_ref": "proof/add_torus.json", "ui_path_verified": false}
  }],
  "proof": {"method": "per_step", "evidence_ref": "proof/manifest.json", "ui_path_verified": false}
}
```
Cet exemple illustre un artefact, pas une preuve réellement obtenue dans ce dépôt. Un export réel exige des hashes et fichiers existants. Leçon vide, version inconnue, check absent ou preuve manquante : validation refusée ou pending, jamais proven.
