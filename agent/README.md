# Face agent : catalogue prouvé, MCP et H Skills

## Disponible

Python 3.11 asyncio ; SDK MCP officiel (`FastMCP`), stdio et HTTP streamable.
Outils : `list_apps`, `find_procedure`, `get_procedure`, `run_procedure`,
`report_broken`. Durée `perf_counter` de chaque appel sur stderr, sans arguments
ni jetons. HTTP écoute sur loopback ; aucune authentification entreprise :
ne pas exposer au réseau.

Le catalogue rescane `AGENT_LESSONS_DIR` (défaut `lessons/`), valide chaque
`**/lesson.json` avec `contracts/lesson.schema.json`, exige `proven` globalement
et par étape ainsi que tous les fichiers de preuve. Aucun recalcul de preuve.
Les liens symboliques ne doivent pas sortir de la révision. Preuves JSON
retournées comme objets, autres fichiers en base64. Empreinte SHA-256 des octets
de la leçon ; identités dupliquées refusées. Rejets et raisons dans `list_apps`.
Le dépôt n'a pas encore de vraie leçon prouvée : les fixtures ne sont pas des
preuves réelles, y compris la fixture LibreOffice Calc v2.

Le catalogue accepte les leçons v2 avec `app` (id, nom, version et capteur).
`lesson_app` centralise la compatibilité v1 : Blender, version issue de
`blender_version`, capteur `addon`. L'identité est le quadruplet
`(lesson_id, revision, app_id, app_version)` ; une recherche ambiguë sans
`app_id` est refusée. Les rejets indiquent l'application/version si connues.
`list_apps` agrège uniquement les leçons prouvées par application, avec nom,
capteurs, compte par version et compte total. `find_procedure` cherche dans
le titre, l'identifiant et les skills, sans distinction de casse ; filtres
optionnels `app_id`, `app_version`, `skill_id`. `get_procedure` et
`run_procedure` exigent `app_version`, avec `app_id` optionnel.
L'argument MCP `blender_version` reste un alias obsolète de
`app_id="blender", app_version=...` ; les filtres contradictoires sont refusés.

Tickets JSON persistants dans `AGENT_STATE_DIR` (défaut
`~/.local/state/hcompany-hack/agent`). Seul un triage `confirmed` met la
révision en quarantaine, toutes applications et versions confondues. Aucune réparation.

## Installation et commandes

```sh
uv python install 3.11
uv venv --python 3.11 ~/.venvs/hcompany-hack
uv pip install --python ~/.venvs/hcompany-hack/bin/python -e '.[agent]'
source ~/.venvs/hcompany-hack/bin/activate
python -m agent.server --transport stdio
python -m agent.server --transport http --host 127.0.0.1 --port 8000
# HTTP : http://127.0.0.1:8000/mcp
python -m agent.triage TICKET_ID confirmed
python -m agent.skill_export LESSON_ID REVISION --app-id libreoffice-calc --app-version 24.2 --output ~/skill-exports
# Version positionnelle historique et --blender-version restent acceptés :
python -m agent.skill_export LESSON_ID REVISION --blender-version 5.2.3 --output ~/skill-exports
# HAI_API_KEY injectée dans l'environnement, jamais en argument :
python -m agent.skill_export LESSON_ID REVISION BLENDER_VERSION --output ~/skill-exports --publish
```

## Exécution : blocage explicite approuvé

`run_procedure` exige consentement non vide, session et révision servable.
Un verrou exclusif au serveur renvoie `busy` au second appel concurrent ;
annulation et erreur le libèrent. Exploiter un seul serveur par bureau :
ce verrou n'est pas inter-processus. Un jeton non vide n'authentifie pas sa portée.
Interface `Runner` injectable pour tests : résultat refusé sans
`checks_passed: true` et `run_id`.

Le runner de production ne déclenche **aucune action** et renvoie :

```text
engine_protocol_unavailable: engine delegation contract not yet defined in contracts/; lesson identity/revision, consent, run_id and check results not representable in desktop-ws v1
```

Issue ouverte : définir dans `contracts/` identité leçon, révision, version
Blender, consentement authentifié et portée, `session_id`, `run_id`, corrélation
requête/progression/résultat, résultats de checks (pass/fail/unknown, étape,
génération, révision de scène), annulation et erreurs.
`user.intent` v1 n'accepte que texte/source ; `lesson.state` n'est pas une preuve
de checks. Aucun protocole WebSocket inventé, aucune URL engine utilisée.
Donc aucun message runner inter-processus à valider ; leçons validées avec
jsonschema, enveloppes MCP validées par le SDK. Doubles runner uniquement unitaires.

## Export et publication H réels

Identité distante déterministe par application × leçon × version. Le nom historique
`blender-lesson-` conserve le hash JSON de `[lesson_id, version]` ; les autres
applications utilisent `<app_id>-lesson-` et `[app_id, lesson_id, version]`.
`compatibility` contient le nom de l'application et sa version ;
`execution_context.app` décrit l'application. `blender_version` n'est conservé
que si présent dans la leçon. Chaque révision de
leçon publiée crée une révision distante de cette même Skill. Fichier local
distinct par leçon × révision × version (`-rN.json`), toujours immuable.
Contenu : objectif,
préconditions, étapes, checks, cibles descriptives sans coordonnées, limites de
preuve, contexte, empreinte. Export identique sans réécriture ; mutation d'une
même révision refusée. Publication GET puis POST si absente ; contenu distant
identique = aucune écriture ; révision de leçon distante plus ancienne = PATCH
avec `If-Match` utilisant l'ETag lu. Révision plus récente, conflit à révision
égale, autre identité/version, métadonnées invalides ou ETag absent = refus.
Une concurrence produisant HTTP 412 est refusée, sans écriture aveugle ni reprise.
Échec distant :
catalogue local inchangé.

Documentation officielle consultée :
- https://hub.hcompany.ai/agents-api/skills/overview
- https://hub.hcompany.ai/agents-api/skills/create
- https://hub.hcompany.ai/agents-api/skills/patch
- https://hub.hcompany.ai/agents-api/skills/list-revisions
- https://hub.hcompany.ai/agents-api/skills/delete

Agents API distincte de Models API. Base européenne :
`https://agp.eu.hcompany.ai/api/v2`, Bearer `HAI_API_KEY`.
`POST /skills` crée avec `name`, `description`, `body` Markdown,
`compatibility` optionnel ; réponse 201. `GET /skills/{name}` lit.
`PATCH /skills/{name}` crée une nouvelle révision avec `If-Match` possible.
`GET /skills/{name}/revisions` liste l'historique ; `DELETE /skills/{name}`
supprime la Skill et ses révisions (204). Test live : nom unique par exécution,
création réelle d'une Skill privée marquée « Integration fixture only »,
PATCH depuis la révision de leçon 1 vers 2, vérification des deux révisions
distantes, republication idempotente sans troisième révision, puis suppression
dans un bloc de nettoyage et vérification de son absence. Aucun agent attaché,
aucune action bureau. Les numéros locaux sont embarqués dans le contenu ; les
numéros distants suivent l'ordre des publications réussies, pas nécessairement
les numéros locaux si certaines révisions n'ont pas été publiées.

## Mesures et vérification

Mesures locales sur cinq fixtures, pas des garanties de production :

| Appel MCP | stdio aller-retour | HTTP aller-retour |
|---|---:|---:|
| list_apps | 19,355 ms | 7,878 ms |
| find_procedure | 17,943 ms | 8,368 ms |
| get_procedure | 12,085 ms | 7,437 ms |
| run_procedure (refus contrat) | 9,573 ms | 5,597 ms |
| report_broken | 3,153 ms | 4,735 ms |

Durées internes stdio : list 15,199 ms ; find 11,865 ms ; get 6,717 ms ;
run refusé 7,019 ms ; report 0,248 ms.
H authentifié : `GET https://api.hcompany.ai/v1/models` **200**, 239,142 ms ;
`GET https://agp.eu.hcompany.ai/api/v2/skills` **200**, 660,691 ms ;
publication initiale GET+POST et réponse : 736,374 ms.

Recette live révisions (nom unique, nettoyé) :

| Requête | HTTP | Durée mesurée |
|---|---:|---:|
| GET Models | 200 | 258,001 ms |
| GET Skill absente | 404 | 519,287 ms |
| POST Skill révision 1 | 201 | 221,707 ms |
| GET avant PATCH | 200 | 521,764 ms |
| PATCH vers leçon révision 2 | 200 | 254,293 ms |
| GET Skill courante | 200 | 524,777 ms |
| GET historique (deux révisions) | 200 | 223,893 ms |
| GET republication idempotente | 200 | 524,851 ms |
| GET historique après no-op | 200 | 207,292 ms |
| DELETE nettoyage | 204 | 246,410 ms |

Durées complètes publisher : création 745,980 ms ; mise à jour 781,830 ms ;
no-op 534,112 ms. Aucun troisième numéro de révision créé par le no-op.
Exécution bureau : non mesurée (est.), fonctionnalité bloquée.

```sh
ruff check agent tests/agent
pytest -q tests/agent -m 'not live'
# Clé injectée pour les appels réels :
pytest -q tests/agent -m live
pytest -q
```

Tests : chaque outil via `ClientSession` stdio et HTTP, catalogue vide, erreurs,
consentement absent, concurrence, annulation, refus sans checks, triage,
export idempotent, échec distant. Mesures reproductibles avec `--capture=tee-sys`.
Publication : création, PATCH protégé, no-op, conflits de version/révision,
échec de PATCH et fichiers locaux distincts couverts par MockTransport.
Pas de recette visuelle ni d'exécution Blender/desktop revendiquée.

Sans `httpx`, `mcp` ou `uvicorn`, les modules de tests agent sont explicitement
skipped avec la raison `agent extra not installed: pip install -e '.[agent]'`.
CI doit installer `.[agent]` (`.github/workflows/ci.yml:18`) pour réellement
exécuter ces tests ; l'installation actuelle `-e .` ne les exécute pas.
