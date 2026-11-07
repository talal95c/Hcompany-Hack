# Contrat événements add-on v1
Transport : JSON lignes sur socket local authentifié, UTF-8, un objet par ligne. Taille maximale et fréquence à figer M0 ; files bornées, agrégation de scene.changed sans perdre les commandes.
## Enveloppe commune
| Champ | Type / requis | Règle |
|---|---|---|
| schema_version | string oui | "1.0" |
| session_id | string oui | session négociée au handshake |
| event_id | string oui | unique pour déduplication |
| seq | integer oui | croissant par connexion ; trou → snapshot |
| type | string oui | discriminant ci-dessous |
| ts_monotonic_ms | number oui | horloge émetteur ; pas de comparaison inter-processus sans synchronisation |
| scene_revision | integer oui | révision de l'état observé |
| payload | object oui | structure propre au type |
## Payloads
| Type | Champs | Usage |
|---|---|---|
| hello | blender_version:string, capabilities:string[] | compatibilité avant commandes |
| snapshot | mode:string, active:string ou null, objects:array | état complet ; objects vide valide |
| operator.executed | idname:string, properties:object | indice REGISTER, pas preuve universelle |
| scene.changed | changed_ids:string[], objects:array | delta associé à révision |
| mode.changed | previous:string, current:string | contexte d'action |
| selection.changed | selected_ids:string[], active:string ou null | sélection vide valide |
| regions.changed | ui_revision:int, regions:array | area_id, area_type optionnel (type de l'éditeur Blender), region_id, type de région, rect, scale, monitor_id |
| undo | count:int | annulations observées, à recouper avec état |
| command.result | command_id, status, detail, scene_revision | acquittement applicatif |
| heartbeat | uptime_ms:number | présence, pas progrès pédagogique |
## Exemple complet
```json
{"schema_version":"1.0","session_id":"s1","event_id":"e7","seq":7,"type":"operator.executed","ts_monotonic_ms":4200,"scene_revision":3,"payload":{"idname":"MESH_OT_primitive_torus_add","properties":{"major_radius":1.0}}}
```
```json
{"schema_version":"1.0","session_id":"s1","event_id":"e8","seq":8,"type":"snapshot","ts_monotonic_ms":4250,"scene_revision":4,"payload":{"mode":"OBJECT","active":"obj-1","objects":[{"id":"obj-1","name":"Torus","type":"MESH","primitive_provenance":"torus","mesh":{"verts":576,"edges":1152,"polys":576}}]}}
```
Les valeurs géométriques de cet exemple ne constituent pas une signature universelle du tore. Les objets réels incluent selon les checks : location, modifiers, materials, sélection et mesh. Une propriété absente signifie inconnue, pas zéro.
## Repères et erreurs
rect = x,y,width,height en coordonnées Blender régionales documentées, origine bas-gauche ; desktop transforme via métadonnées de fenêtre. Une révision UI change à chaque déplacement/redimensionnement. Type inconnu : journaliser et ignorer si extension mineure ; enveloppe invalide : rejeter ; version majeure incompatible : refuser la connexion. Ne pas avancer une étape sur un delta incomplet ; demander snapshot.
