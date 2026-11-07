# engine/services/

## Responsabilité
Clients IA cloud asynchrones : Holo (H Company), Jev (Codiv System One), Gladia (STT), Linkup (recherche).

## Modules
- `protocols.py` : Protocols `HoloClient`, `JevClient`, `SttClient`, `SttSession`, `SearchClient` et types (`Location`, `HoloAction`, `JevDecision`, `Transcript`, `SttEvent`, `SearchResult`).
- `holo.py` : `HoloCloudClient.locate(image_png, target_description) -> (x, y, confidence)` (coordonnées normalisées 0-1000, recadrage via `Region`, thinking off, température 0, préfixe système stable pour le cache) et `act(...)`, un tour de computer use avec les outils `click` / `type` / `key` / `done`. Les actions sont validées (bornes, touches autorisées) et converties en payload `input.action` ; leur exécution reste soumise au consentement, au verrou et au stop.
- `jev.py` : `CodivJevClient.decide(state, questions)` sur `POST /v1/systemone`, connexion HTTP/2 persistante, questions batchées, timeout 800 ms, budget partagé direct/spéculatif ; questions prêtes : intention (`question`, `fais_le`, `frustration`, `chut`, `other`), `stuck`/`thinking`, sévérité de déviation (`none`/`minor`/`major`).
- `gladia.py` : session live WebSocket (partiels, finals, `speech_start`/`speech_end`, endpointing, vocabulaire personnalisé) et `transcribe_file` (upload → job → polling, timestamps par mot, vocabulaire personnalisé). `decode_audio_chunk` convertit un message `audio.chunk` du contrat desktop-ws.
- `linkup.py` : `LinkupSearchClient.search` en `outputType=structured` avec sources, domaines et schéma issus du profil actif.
- `errors.py`, `latency.py`, `_retry.py` : erreurs distinctes (timeout, indisponibilité, quota, réponse invalide, auth), mesure de chaque appel (durée, statut, request_id, tokens) et bench p50/p95, retry idempotent et seau de jetons.

## Clés
`HAI_API_KEY`, `CODIV_API_KEY`, `GLADIA_API_KEY`, `LINKUP_API_KEY`, lues dans l'environnement, jamais journalisées.

## État et validation
`pytest -q tests/services` (unitaires, stubs locaux) ; `pytest -m live tests/services` appelle réellement les quatre services et écrit `tests/services/results/*.json`. Une réponse de modèle n'est jamais une preuve d'état applicatif : les checks restent l'autorité.

## Profils
`profiles.py` expose `AppProfile`, `load_profile`, `list_profiles` et
`profile_for_lesson_app`. Les données validées sont dans `apps/` (schéma draft 2020-12).
Les clients Jev, Gladia et Linkup acceptent `profile=` ; le repli est générique.
Les builders Jev et les appels Jev/Linkup permettent une surcharge par appel.
Gladia utilise le vocabulaire du profil si aucun vocabulaire explicite n'est fourni.
`build_clients` résout `app.id` depuis la leçon fournie ou `config.lesson`.
Les anciens champs de leçon sont associés aux profils dans `apps/legacy.json`.
Un identifiant inconnu utilise le profil générique.

Les appels Holo partagent un cadenceur de 24 requêtes/minute dans le processus.
Chaque tentative dure au plus 6 s (est.), avec une requête parallèle après 4 s
(est.), annulation des perdantes, backoff et `Retry-After` plafonné à 8 s (est.).
Les budgets de vérification, localisation et action sont de 30 s (est.). Les hedges
passent par le même cadenceur ; une réponse 429 déclenche le backoff, pas un hedge.
Les requêtes Holo ferment leur connexion HTTP après chaque tentative pour éviter
de réutiliser une connexion bloquée. Le budget reste prioritaire même si les trois
tours de retry ne tiennent pas tous dans ce délai. `HCOMPANY_ATTEMPT_LOG` active une
trace JSONL sans contenu utilisateur : décalage de départ, durée, statut,
`Retry-After`, identifiant de requête et chemin gagnant (primaire ou hedge).
Jev peut dupliquer une décision après 375 ms (est.), dans le même budget de 800 ms
(est.) ; chaque duplication consomme aussi un jeton de quota.
La confiance combine une auto-évaluation
avec grille explicite et, si disponibles, les probabilités des jetons du verdict.
Ce score n'est pas une probabilité d'exactitude calibrée.
Les percentiles des benches comprennent les appels échoués ; les comptes de
timeouts et autres erreurs sont explicites. Les tests live écrivent hors git sauf
avec `HCOMPANY_WRITE_RESULTS=1`, réservé à la génération explicite du snapshot.

## Vérification et boucle d'actions
`HoloVerifier.verify(image_png, assertion_text, region=None, profile=None)` juge une
assertion visible : `pass`, `fail` ou `unknown`. Pourquoi : une annonce `done`
n'est pas une preuve. Sous le seuil de confiance (0,6 par défaut), le résultat devient
`unknown`. Le modèle vaut `holo4-27b`, surchargeable par argument ou
`HOLO_VERIFY_MODEL`. Le contexte applicatif reste dans le message utilisateur pour
préserver le préfixe système stable. Une région recadre réellement le PNG via Pillow
(import paresseux) ; sans Pillow, une instruction limite l'évidence à cette région.
Ce jugement visuel ne remplace pas un check déterministe.

`run_steps` alterne capture fraîche, proposition Holo et exécution par callback.
Avec un vérificateur, `done` exige une nouvelle capture et un `pass` ; les refus
retournent dans l'historique. Sans vérificateur, `success` est seulement une annonce
non vérifiée (`final=None`). Sans assertion explicite, l'objectif sert d'assertion.
Le résultat inclut les tours, la dernière vérification et les latences mesurées par tour.
L'arrêt interrompt les attentes en cours et l'annulation asyncio est propagée.
Le caller doit garantir consentement, verrou, cible de capture et test après action ;
annuler un callback ne peut pas annuler une entrée native déjà injectée.

`XdotoolExecutor(window_id=None)` et `capture_x11(window_id=None)` sont uniquement
des helpers de test Linux X11 (xdotool et ImageMagick `import`). Les deux doivent
viser la même fenêtre ou l'écran entier. Les coordonnées normalisées sont converties
en pixels bornés de la fenêtre, puis translatées vers l'écran ; ce helper n'est pas
un backend natif de production. Aucun appel cloud ni bureau réel dans les unitaires.

## Mesures live du 7 novembre 2026 (Linux Xvfb, cloud réel)

Durées mesurées par le recorder autour des appels réseau, hors pacing Holo de
2,5 s et hors capture/injection. Les valeurs ci-dessous ne sont pas des estimations.
Les échantillons sont petits ; n=1 ne caractérise pas une distribution de latence.

| Recette / opération | n | p50 (ms, mesuré) | p95 (ms, mesuré) | Résultat |
| --- | ---: | ---: | ---: | --- |
| Holo vérification, quatre captures réelles | 12 | 396,1 | 634,9 | 12/12, aucun faux pass |
| Calc computer-use / act | 4 | 697,8 | 974,4 | succès vérifié en quatre tours |
| Calc computer-use / verify final | 1 | 336,0 | 336,0 | pass, A4=60 et formule visible |
| Jev / intentions Excel | 10 | 177,7 | 415,9 | 10/10 |
| Linkup / documentation Excel | 1 | 3398,8 | 3398,8 | sources support.microsoft.com |
| Holo / localisation historique | 18 | 269,4 | 365,6 | 18/18 cibles |
| Jev / lot historique, intentions et assessments | 23 | 161,6 | 220,0 | intentions 20/20 |
| Gladia / fichier complet | 3 | 4231,7 | 4314,9 | transcriptions et mots validés |
| Gladia / final après dernier chunk live | 2 | 736,4 | 804,4 | partiels et finals validés |
| Linkup / documentation 3D historique | 3 | 2979,1 | 3794,7 | domaines officiels validés |

La recette Calc complète a pris **14 258,1 ms mesurées**, démarrage applicatif,
captures, pacing et vérification compris. Les tours et captures sont conservés dans
`tests/services/results/computer_use.json` et `tests/services/results/computer_use/`.
Le premier essai avait échoué car Holo émettait la touche X11 Return ; le parseur
normalise maintenant cet alias vers l'identifiant natif enter, sans élargir les
actions autorisées. La trace d'échec est conservée séparément.
Les autres résultats sont dans `verify.json`, `jev_excel.json`, `linkup_excel.json`
et les quatre fichiers historiques du même dossier. Unknown compte comme incorrect.
Les seuils d'accuracy (80 %) sont des cibles de recette, pas des mesures de fiabilité
générale ; aucune validation macOS ni accessibilité Calc n'est déduite de ces tests.
