# Contrat leçon v1 et v2
Statut : JSON Schema exécutable dans [lesson.schema.json](../../contracts/lesson.schema.json). Les ajouts v2 sont structurels ; le routeur multi-app et les backends restent à implémenter.
| Champ | Type / obligatoire | Sens et contraintes |
|---|---|---|
| schema_version | string oui | "1.0" ou "2.0" ; autre version refusée |
| lesson_id / revision | string / integer oui | identité stable / révision immuable positive |
| title / language | string oui | titre affiché / locale |
| blender_version | string en v1, optionnel en v2 | version exacte prouvée, pas une plage supposée |
| app | object obligatoire en v2, interdit en v1 | id, name, version non vides ; sensor = addon, accessibility, vision ou auto |
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
| preconditions | object oui | mode obligatoire en v1 seulement ; window_title optionnel non vide ; objet vide possible en v2 |
| check | object oui | name whitelist + params typés ; pas de code généré |
| target | object oui | forme Blender en v1 ; en v2 forme Blender ou cible générique descriptive ; aucune coordonnée persistée |
| why | string oui | explication compilée |
| audio_ref | string ou null oui | chemin relatif contrôlé ; null tant que TTS absent |
| known_errors | object[] oui | code, check, hint ; vide autorisé |
| procedure_ref | string oui | procédure autorisée de secours |
| proof | object oui | statut, méthode, evidence_ref et ui_path_verified par étape |
| challenge | boolean non | false par défaut ; réussite sans aide débloque la compétence |
| help | object non | menu_id optionnel (carte UI de la version prouvée), safe_demo=false par défaut, checkpoint_id ; safe_demo=true exige un checkpoint |

## Whitelist des checks
Les paramètres sont fermés et partagés avec les checks d'erreurs connues. Les huit checks Blender ci-dessous acceptent aussi le préfixe `blender.`. Sauf mode_is et object_exists (filtres requis), ils acceptent les filtres optionnels type et primitive.
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
Pour une leçon Blender v1, la version Blender du hello doit correspondre exactement à blender_version avant toute
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

## Ajouts v2 : cible et checks génériques
La cible générique exige `description` et accepte `role`, `name`, `path` (tableau d'ancêtres « role:nom », de la racine vers la cible) et `app_region`. Ses propriétés sont fermées. Aucune ref de snapshot ni coordonnée n'est persistée.

| name | params fermés |
|---|---|
| element_exists | target requis ; present=true par défaut, timeout_ms optionnel |
| element_value | target et value (string, number ou boolean) requis ; match=equals par défaut, contains ou regex ; tolerance ≥0 optionnel, timeout_ms optionnel |
| element_state | target requis ; states et/ou absent_states, au moins une liste non vide ; timeout_ms optionnel |
| window_title | value non vide requis ; match=contains par défaut, equals ou regex |
| visual_assert | assertion requise : question fermée oui/non à Holo sur capture fraîche de la fenêtre ; region optionnelle {x,y,w,h} en millièmes 0–1000 ; min_confidence entre 0 et 1, défaut 0.8 |

`timeout_ms` est un budget entier entre 0 et 30000 ms, pas une latence mesurée. Les états autorisés sont focused, selected, checked, enabled, expanded, visible, editable, pressed et busy. Un arbre incomplet ou un check indisponible donne unknown, jamais pass. Une absence ne peut être prouvée par un sous-arbre tronqué.

La v1 garde sa cible Blender et son mode requis. La v2 peut garder `blender_version` et les checks spécialisés. Voir les [règles multi-app](../architecture/multi-app.md) et l'[ADR 0011](../decisions/0011-multi-app.md). Toute migration doit être explicite, avec nouvelle preuve avant export.

## Exemple v2 générique
Exemple structurel en brouillon, sans preuve obtenue ni procédure exécutable livrée :
```json
{
  "schema_version": "2.0",
  "lesson_id": "editor",
  "revision": 1,
  "title": "Activer le gras",
  "language": "fr-FR",
  "app": {"id": "editor", "name": "Éditeur", "version": "1.0", "sensor": "auto"},
  "status": "draft",
  "source": {"uri": "fixture://editor", "sha256": "EXEMPLE_NON_PUBLIE"},
  "skills": ["format_text"],
  "steps": [{
    "id": "bold",
    "skill_id": "format_text",
    "instruction": "Active le gras.",
    "preconditions": {"window_title": "Document"},
    "check": {"name": "element_state", "params": {
      "target": {"description": "Bouton Gras", "role": "button", "name": "Gras"},
      "states": ["pressed"]
    }},
    "target": {"description": "Bouton Gras du ruban", "role": "button", "name": "Gras", "path": ["window:Document", "toolbar:Format"]},
    "why": "Le gras met en évidence le texte sélectionné.",
    "audio_ref": null,
    "known_errors": [],
    "procedure_ref": "editor/bold",
    "proof": {"status": "draft", "method": "accessibility", "evidence_ref": "proof/bold.json", "ui_path_verified": false}
  }],
  "proof": {"method": "per_step", "evidence_ref": "proof/manifest.json", "ui_path_verified": false}
}
```
