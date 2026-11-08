# Contrat WebSocket desktop ↔ engine
## Conventions de transport et consentement v1
Le sidecar écrit sur stdout une ligne `ENGINE_READY {"ws_port":1234,"addon_port":1235}`
après l'ouverture des sockets. Les diagnostics restent sur stderr. Le desktop peut aussi
rejoindre un moteur déjà lancé via `ENGINE_WS_URL`. L'authentification accepte le header
`Authorization: Bearer <jeton>` ou le paramètre `?token=<jeton>` ; aucun jeton dans les logs
ni dans la WebView. Les origins locales sont filtrées, indépendamment du jeton.

`user.intent` conserve le consentement JSON-dans-texte : source `bouton`, `text` contenant
`{"intent":"fais-le","consent_token":"<uuid>"}`. Ce jeton est créé par Rust, jamais par le
front ; il est repris dans `input.action`. Les booléens `delegation_confirmed: true` et
`wants_to_learn: false` permettent la délégation explicitement confirmée sans apprentissage.
Le moteur vérifie aussi version Blender, état, compétence, génération et expiration ;
un énoncé texte ne vaut jamais consentement. Aucun changement incompatible de l'enveloppe.

`lesson.state.ui_revision` est optionnel et désigne la révision UI du capteur Blender.
Le desktop la recopie dans `capture.result`, sans compteur local indépendant. Les états
inchangés ne sont pas renvoyés à chaque tick et ne doivent pas effacer un pointeur actif.
Pour `pointer` et `success`, le guide renvoie `input.result` avec `status: "ok"` et
`detail: "rendered"` après deux frames navigateur. Cet ack mesure le traitement du rendu,
pas la présentation physique du compositeur ; une capture d'écran reste nécessaire.

Un WebSocket local par session, authentifié avant messages applicatifs. Adresse donnée par le sidecar, origin autorisée explicitement ; pas de port accessible sur le LAN. Le front web n'accède pas directement aux secrets.
| Champ enveloppe | Type / requis | Sens |
|---|---|---|
| schema_version | string oui | "1.0" |
| session_id | string oui | session courante |
| message_id | string oui | déduplication |
| reply_to | string ou null oui | corrélation |
| type | string oui | discriminant |
| payload | object oui | données typées |
## Messages
| Sens / type | Champs payload |
|---|---|
| desktop → engine : hello | app_version, platform, capabilities |
| desktop → engine : permissions | screen:boolean, accessibility:boolean, microphone:boolean |
| desktop → engine : ptt.start / ptt.stop | utterance_id |
| desktop → engine : audio.chunk | utterance_id, sequence, encoding, sample_rate, data_base64 |
| desktop → engine : capture.result | capture_id, ui_revision, crop, scale, monitor_id, image_ref ; image_size optionnel |
| desktop → engine : input.result | command_id, status, detail |
| desktop → engine : user.intent | text, source clavier ou bouton |
| engine → desktop : command | enveloppe [ordre](ordres.md) |
| engine → desktop : lesson.state | step_id nullable, status, instruction, help_level |
| bidirectionnel : ping / pong | nonce |
| bidirectionnel : error | code, message, retryable |
## Exemple état
```json
{"schema_version":"1.0","session_id":"s1","message_id":"m20","reply_to":null,"type":"lesson.state","payload":{"step_id":"add_torus","status":"OBSERVING","instruction":"Ajoute un tore.","help_level":1}}
```
## Exemple permission refusée
```json
{"schema_version":"1.0","session_id":"s1","message_id":"m21","reply_to":null,"type":"permissions","payload":{"screen":false,"accessibility":false,"microphone":true}}
```
image_ref pointe vers un buffer éphémère contrôlé, jamais un chemin arbitraire transmis par le web. Format audio exact et limite de taille à figer M0 selon Gladia ; la table n'invente pas de compatibilité codec. Ordre des chunks par sequence, annulation par utterance_id. Silence audio : aucun appel spéculatif.
Reconnexion : backoff borné, hello puis état complet, capture/UI invalidés ; pas de replay automatique des input.action. File audio bornée : signaler overflow plutôt qu'accumuler une latence cachée. Aucune capture ni audio conservé par défaut ; debug opt-in expurgé.

## Accessibilité et application active (ajouts compatibles v1)
Ces messages sont définis dans [desktop-ws.schema.json](../../contracts/desktop-ws.schema.json) ; leur présence ne signifie pas que les handlers natifs sont livrés. L'enveloppe conserve schema_version 1.0.

| Sens / type | Payload |
|---|---|
| engine → desktop : a11y.request | request_id, op, app ; root, query, ref, action, value, max_depth, consent_token selon l'opération |
| desktop → engine : a11y.result | request_id, snapshot_id, complete, nodes ; error optionnel |
| desktop → engine : app.focus | app_id, name, window_title, window_bounds en pixels physiques, scale >0 ; accessibility optionnel : available, unavailable, unknown |
| engine → desktop : highlight.rect | même payload fermé que la [commande](ordres.md), sans son enveloppe |

`op` vaut snapshot, find, get ou action. snapshot accepte un root et une profondeur max_depth de 1 à 64 ; find exige query (au moins une propriété parmi role, name, path, value, states), get exige ref. path est un tableau d'ancêtres « role:nom ». action exige ref, action et consent_token ; ce jeton et le champ action sont interdits pour les autres opérations. Actions : press, focus, set_value, toggle, select, expand, collapse, scroll_into_view ; set_value exige value (string).

Chaque nœud exige ref, role, name, states et bounds {x,y,w,h} en pixels physiques écran (dimensions >0) ; value et parent_ref sont optionnels. Les états autorisés sont focused, selected, checked, enabled, expanded, visible, editable, pressed, busy. Les refs sont locales au snapshot et ne sont jamais persistées dans la leçon.

error contient code et message. Codes : STALE_REF, AMBIGUOUS_TARGET, APP_NOT_FOUND, PERMISSION_DENIED, TIMEOUT. Une erreur impose complete=false et autorise snapshot_id=null ; sans erreur, snapshot_id est non vide. nodes peut être vide ; complete=false ne permet aucune preuve d'absence. Reconnexion : invalider toutes les refs et reprendre focus puis snapshot, sans rejouer d'action.

Les actions suivent les mêmes contrôles que input.action : consentement actif, verrou, stop prioritaire, focus cible, puis nouveau check. L'arbre est privé et non fiable, limité au sous-arbre utile ; aucune valeur dans les logs, rien au cloud par défaut et aucun champ de mot de passe.

### Recherche et résultat nominal
```json
{"schema_version":"1.0","session_id":"s1","message_id":"m30","reply_to":null,"type":"a11y.request","payload":{"request_id":"q1","op":"find","app":"editor","query":{"role":"button","name":"Gras"},"max_depth":8}}
```
```json
{"schema_version":"1.0","session_id":"s1","message_id":"m31","reply_to":"m30","type":"a11y.result","payload":{"request_id":"q1","snapshot_id":"snap-1","complete":true,"nodes":[{"ref":"node-2","role":"button","name":"Gras","states":["enabled","pressed"],"bounds":{"x":120,"y":80,"w":90,"h":30}}]}}
```
### Résultat vide et erreur
Un arbre complet vide est une réponse possible, pas une réussite d'étape :
```json
{"schema_version":"1.0","session_id":"s1","message_id":"m32","reply_to":"m30","type":"a11y.result","payload":{"request_id":"q1","snapshot_id":"snap-2","complete":true,"nodes":[]}}
```
```json
{"schema_version":"1.0","session_id":"s1","message_id":"m33","reply_to":"m30","type":"a11y.result","payload":{"request_id":"q1","snapshot_id":null,"complete":false,"nodes":[],"error":{"code":"PERMISSION_DENIED","message":"Autorise l'accès à l'interface de cette application."}}}
```

## Capture d'une fenêtre
capture.request accepte désormais scope=rect (défaut) ou window et app optionnel. Avec window, app est obligatoire et crop doit être null. Les champs existants request_id, crop, ui_revision et generation restent requis. capture.result accepte app optionnel en complément des champs existants ; cela ne change ni l'exclusion de desktop ni le traitement éphémère de l'image. L'app retournée doit correspondre à la fenêtre demandée avant toute utilisation. Voir [repères et secours](../architecture/multi-app.md).

```json
{"schema_version":"1.0","session_id":"s1","message_id":"m34","reply_to":null,"type":"capture.request","payload":{"request_id":"cap-q1","crop":null,"ui_revision":0,"generation":2,"scope":"window","app":"editor"}}
```
