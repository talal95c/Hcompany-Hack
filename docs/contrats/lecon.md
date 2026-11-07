# Contrat leçon v1
Statut : spécification à figer M0 ; futurs JSON Schema dans contracts/, aucun schéma exécutable encore livré.
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
