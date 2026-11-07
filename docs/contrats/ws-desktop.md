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
| desktop → engine : capture.result | capture_id, ui_revision, crop, scale, monitor_id, image_ref |
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
