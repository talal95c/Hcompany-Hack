# Contrat ordres engine → clients
## Enveloppe
| Champ | Type / requis | Sens |
|---|---|---|
| schema_version | string oui | "1.0" |
| session_id / command_id | string oui | routage / idempotence |
| step_id | string ou null oui | étape concernée |
| generation | integer oui | annuler les résultats périmés |
| recipient | enum oui | addon ou desktop |
| type | enum oui | commande de la table |
| deadline_ms | number oui | budget relatif à réception, pas timestamp d'une autre horloge |
| payload | object oui | paramètres validés |
| expected_scene_revision | integer ou null oui | garde contre état modifié |
## Commandes et paramètres
| type / destinataire | Payload requis | Effet |
|---|---|---|
| highlight / addon | area_id, region_id, color, duration_ms | surlignage temporaire |
| highlight.rect / desktop | rect, color, duration_ms | rectangle overlay en pixels physiques écran ; app, ref, snapshot_id et label optionnels |
| clear_highlight / addon | aucun | retire tous les handles session |
| open_menu / addon | menu_id, area_id, region_id | wm.call_menu validé, contexte réel |
| replay / addon | procedure_ref, params | bpy whitelist ; aucune chaîne Python |
| undo_demo / addon | checkpoint_id | annule uniquement démo isolée |
| request_snapshot / addon | aucun | état complet |
| pointer / desktop | capture_id, ui_revision, x, y | point normalisé [0,1000] sur la capture ; app, ref, snapshot_id optionnels ; affichage seulement |
| say / desktop | text, audio_ref nullable | lire cache ou texte |
| success / desktop | text | ✓ silencieux |
| input.action / desktop | action, consent_token, capture_id | une action native autorisée |
| stop / desktop | reason | priorité maximale, libère touches |
## Exemple complet
```json
{"schema_version":"1.0","session_id":"s1","command_id":"c12","step_id":"add_torus","generation":2,"recipient":"addon","type":"open_menu","deadline_ms":1000,"expected_scene_revision":4,"payload":{"menu_id":"VIEW3D_MT_mesh_add","area_id":"a1","region_id":"r1"}}
```
## Exemple de rectangle multi-app
`highlight` reste exclusivement destiné à l'add-on, inchangé. `highlight.rect` est destiné au desktop ; rect contient x/y et w/h strictement positifs pour les dimensions, en pixels physiques écran. color est une chaîne non vide, duration_ms un budget ≥0, label une chaîne d'au plus 120 caractères. app identifie l'application ; ref et snapshot_id sont éphémères et doivent être invalidés après changement UI. Ce surlignage ne constitue ni une action ni une preuve de réussite.

```json
{"schema_version":"1.0","session_id":"s1","command_id":"c13","step_id":"bold","generation":2,"recipient":"desktop","type":"highlight.rect","deadline_ms":1000,"expected_scene_revision":null,"payload":{"rect":{"x":120,"y":80,"w":90,"h":30},"color":"#FFD54F","duration_ms":1500,"app":"editor","ref":"node-2","snapshot_id":"snap-1","label":"Gras"}}
```

L'enveloppe reste en version 1.0 (ajout compatible). Les conversions pointer / capture et les garde-fous sont décrits dans l'[architecture multi-app](../architecture/multi-app.md).

## Résultat de commande
```json
{"command_id":"c12","status":"ok","detail":"menu ouvert","scene_revision":4}
```
status = ok, rejected, failed, expired ; detail lisible, error_code optionnel pour traitement : stale_state, bad_context, unknown_procedure, permission_denied, busy. ok signifie commande exécutée, pas étape réussie. Déduplication command_id : retourner le résultat connu ; résultat incertain après coupure : snapshot et réconciliation avant nouvelle mutation. Payload vide valide seulement pour les types sans paramètres ; coordonnées hors bornes ou consentement manquant rejetés.
