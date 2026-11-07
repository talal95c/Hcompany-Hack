# engine/services/

## Responsabilité
Clients IA cloud asynchrones : Holo (H Company), Jev (Codiv System One), Gladia (STT), Linkup (recherche).

## Modules
- `protocols.py` : Protocols `HoloClient`, `JevClient`, `SttClient`, `SttSession`, `SearchClient` et types (`Location`, `HoloAction`, `JevDecision`, `Transcript`, `SttEvent`, `SearchResult`).
- `holo.py` : `HoloCloudClient.locate(image_png, target_description) -> (x, y, confidence)` (coordonnées normalisées 0-1000, recadrage via `Region`, thinking off, température 0, préfixe système stable pour le cache) et `act(...)`, un tour de computer use avec les outils `click` / `type` / `key` / `done`. Les actions sont validées (bornes, touches autorisées) et converties en payload `input.action` ; leur exécution reste soumise au consentement, au verrou et au stop.
- `jev.py` : `CodivJevClient.decide(state, questions)` sur `POST /v1/systemone`, connexion HTTP/2 persistante, questions batchées, timeout 800 ms, budget partagé direct/spéculatif ; questions prêtes : intention (`question`, `fais_le`, `frustration`, `chut`, `other`), `stuck`/`thinking`, sévérité de déviation (`none`/`minor`/`major`).
- `gladia.py` : session live WebSocket (partiels, finals, `speech_start`/`speech_end`, endpointing, vocabulaire personnalisé) et `transcribe_file` (upload → job → polling, timestamps par mot, vocabulaire personnalisé). `decode_audio_chunk` convertit un message `audio.chunk` du contrat desktop-ws.
- `linkup.py` : `LinkupSearchClient.search` en `outputType=structured` avec sources, limité par défaut à `docs.blender.org`.
- `errors.py`, `latency.py`, `_retry.py` : erreurs distinctes (timeout, indisponibilité, quota, réponse invalide, auth), mesure de chaque appel (durée, statut, request_id, tokens) et bench p50/p95, retry idempotent et seau de jetons.

## Clés
`HAI_API_KEY`, `CODIV_API_KEY`, `GLADIA_API_KEY`, `LINKUP_API_KEY`, lues dans l'environnement, jamais journalisées.

## État et validation
`pytest -q tests/services` (unitaires, stubs locaux) ; `pytest -m live tests/services` appelle réellement les quatre services et écrit `tests/services/results/*.json`. Une réponse de modèle n'est jamais une preuve d'état Blender : les checks restent l'autorité.
