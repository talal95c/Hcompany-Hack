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
preuves Blender réelles.

Tickets JSON persistants dans `AGENT_STATE_DIR` (défaut
`~/.local/state/hcompany-hack/agent`). Seul un triage `confirmed` met la
révision en quarantaine, toutes versions Blender confondues. Aucune réparation.

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
python -m agent.skill_export LESSON_ID REVISION BLENDER_VERSION --output ~/skill-exports
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

Identité déterministe par leçon × révision × version Blender. Contenu : objectif,
préconditions, étapes, checks, cibles descriptives sans coordonnées, limites de
preuve, contexte, empreinte. Export identique sans réécriture ; mutation d'une
même révision refusée. Publication GET puis POST ; contenu distant identique =
aucune écriture, contenu différent = refus plutôt qu'écrasement. Échec distant :
catalogue local inchangé.

Documentation officielle consultée :
- https://hub.hcompany.ai/agents-api/skills/overview
- https://hub.hcompany.ai/agents-api/skills/create
- https://hub.hcompany.ai/agents-api/skills/patch
- https://hub.hcompany.ai/agents-api/skills/list-revisions

Agents API distincte de Models API. Base européenne :
`https://agp.eu.hcompany.ai/api/v2`, Bearer `HAI_API_KEY`.
`POST /skills` crée avec `name`, `description`, `body` Markdown,
`compatibility` optionnel ; réponse 201. `GET /skills/{name}` lit.
`PATCH /skills/{name}` crée une nouvelle révision avec `If-Match` possible.
L'export immuable n'utilise pas PATCH : une nouvelle révision locale donne une
nouvelle identité distante. Test live : création réelle d'une Skill privée
explicitement marquée « Integration fixture only », puis lecture idempotente ;
aucun agent attaché, aucune action bureau.

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
publication GET+POST et réponse : 736,374 ms.
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
Pas de recette visuelle ni d'exécution Blender/desktop revendiquée.
