# Rio — le prof qui te regarde faire

[![Rio](brand/rio-hill.jpg)](https://rio.vignemale.com)

> Dis ce que tu veux apprendre, colle un tuto YouTube ou choisis-en un dans la bibliothèque. Rio le transforme en **prof qui te regarde faire, dans ta version du logiciel**, et qui s'efface quand tu sais.
> Puis la même leçon, réussie une fois, devient un **skill** : Rio peut la refaire à ta place, en vérifiant chaque étape à l'écran.

## Le problème

Apprendre un logiciel (Blender, DaVinci Resolve, un outil interne…), c'est un tuto d'un côté et le logiciel de l'autre :
- tu fais sans arrêt pause et retour en arrière ;
- le tuto est sur une autre version que la tienne, les menus ont bougé ;
- personne ne te dit si tu as bien fait, ni pourquoi ça ne marche pas ;
- une semaine plus tard, tu ne sais plus le refaire.

Les assistants « je vois ton écran, je te montre le bouton » répondent à la question, mais tu n'apprends pas : ils font à ta place ou te donnent la réponse, sans vérifier que tu as compris ni que le résultat est vraiment là.

## Ce que fait Rio

1. **Préparer.** Un objectif, un tuto YouTube (transcrit par Gladia) ou une page web devient un **graphe de jalons** : chaque jalon est un sous-but vérifiable à l'écran (« une note Groceries existe »), pas une suite de clics. La base de connaissances de l'équipe (aujourd'hui Blender 5.2.3 : 162 skills, et DaVinci Resolve 20.1 : 110 skills, recalés sur ta version) est donnée à Holo **à chaque jalon** : « Ctrl+R, puis Entrée pour confirmer » plutôt qu'une supposition.
2. **Apprendre.** Tu fais chaque action toi-même. Un curseur fantôme montre où cliquer, Rio regarde ton écran (captures, clics, rythme des frappes, jamais leur contenu) et réagit : réussite, erreur, blocage. Tu peux lui poser une question à voix haute en cours de route ; il te répond, te montre l'élément, et s'en souvient pour la suite. Il te pose aussi des questions (« à ton avis, quel menu ? »), et **son aide s'efface** : sur une action que tu as déjà réussie, plus de pointeur, juste la consigne, avec « Show me » si tu bloques.
3. **Déléguer.** Une fois qu'un tuto a réussi, il devient un skill. La prochaine fois que tu es dans le logiciel, la notch propose « Rio le fait pour toi ». Rio exécute alors lui-même, avec ta permission, et ne dit « Fait ✓ » qu'après avoir **vérifié chaque jalon puis le but entier sur une capture neuve**. Quand c'est possible, un script compilé par Devin remplace les clics.
4. **Partager.** La plateforme ([rio.vignemale.com](https://rio.vignemale.com)) réunit la bibliothèque de tutoriels de l'équipe, sa base de connaissances, ses membres et ses statistiques (questions sans réponse, jalons où l'on bloque). Le cœur du harness est aussi décrit comme un skill pour les agents (`.prime/agent/skills/rio-harness-core/`).

## Comment on sait que ça marche

Rio est **mesuré**, pas seulement testé. Un **apprenant simulé** (un modèle qui joue un débutant, un distrait, un curieux…) suit de vrais tutoriels dans un Chrome invisible, avec des erreurs tirées au sort mais rejouables, et **c'est du code qui note le résultat** en lisant l'état réel de l'app. Chaque changement du tuteur est comparé à la version précédente sur les mêmes scénarios et les mêmes graines, une idée reprise de [harness2](https://github.com/google-research/harness2) (Google).

Ce que ça a déjà donné (petits échantillons, des tendances plutôt que des preuves) :
- **Tuteur** : 3 réussites sur 8 contre 2 avant les corrections, et moins de « terminé » annoncé à tort. Corrections trouvées en lisant les journaux : validation sans preuve contestée, acharnement sur un élément mort repéré, réponses honnêtes aux questions, plans qui gardent les noms de la demande.
- **Autopilote** : de 0 à **6 réussites sur 8**, et de 6 à **0 fausse réussite**, grâce à la vérification du but entier avant « Fait ✓ ».
- 110 tests Rust, et un explorateur HTML de toutes les sessions (`python3 tools/session_explorer.py --open`).

## Partenaires

| Brique | Rôle dans Rio |
|---|---|
| **H Company · Holo4** (Models API, Agents API) | voir l'écran et choisir chaque action (`holo4-27b`), localiser et vérifier vite (`holo4-35b-a3b`), planifier les jalons, vérifier un résultat sur capture, jouer l'apprenant du simulateur ; agents `h/deep-search-pro` et `h/web-surfer-pro` pour fabriquer un tuto depuis un objectif ou une page |
| **Gladia** | ta voix en direct (langue détectée ou fixée : Auto / EN / FR) et la transcription des tutos YouTube |
| **Gradium** | la voix de Rio, synthétisée en local (Phonon) |
| **Linkup** | recherche web de secours quand la base de l'équipe n'a rien |
| **Devin** | compile les skills réussis en scripts testés, et relit les PR |
| **Cloudflare** (Workers, D1) | la plateforme : API, console, base de connaissances |

## Plateformes

L'app desktop tourne sur **macOS** (Tauri v2, Rust + React). L'autopilote fonctionne aussi sous **Linux X11** ; Wayland est refusé explicitement. La plateforme et la console tournent sur Cloudflare.

## Le dépôt

```
src-tauri/   l'app desktop en Rust : boucle du tuteur, autopilote, voix, capture, simulateur (src/sim)
src/         l'interface de l'app : barre, curseur fantôme, notch
platform/    l'API et la console web (Cloudflare Worker), base de connaissances (platform/knowledge)
landing/     le site rio.vignemale.com
tutorials/   tutoriels d'exemple (graphes de jalons)
sim/         scénarios et app de test du simulateur
tools/       explorateur de sessions
.prime/      skill « rio-harness-core » pour les agents
```

## État

Rio se lance depuis les sources (`npm run tauri dev`, détail ci-dessous) ; un installeur en un clic est prévu. Le tuteur, l'autopilote et la plateforme fonctionnent de bout en bout ; leurs points faibles mesurés sont la précision du pointage de Holo (environ 79 % des clics à moins de 30 points de la cible) et les plans faits sur des demandes vagues (« rends l'arbre plus réaliste »).

---

*Documentation technique (en anglais).*

## Run

```bash
cp .env.example .env   # then set HAI_API_KEY
npm install
npm run tauri dev
```

On first use, macOS asks for **Screen Recording** permission (System Settings › Privacy & Security). Grant it to your terminal, then restart.

## Use

- **⌥⇧Space** (or the cursor icon in the menu bar) opens the bar at the bottom of the screen, even over full-screen apps.
- **Language**: the `Auto / EN / FR` button next to the mic. *Auto* detects each sentence (an accent can fool it: "help me" heard as "m'a aidé"); *EN* or *FR* pins what the speech recognizer hears and the language Holo answers in. The choice is remembered.
- Type a goal, press Enter. Follow the ghost cursor; progress also shows in the menu bar.
- Esc hides the bar when no tutorial is running. Right-click the menu bar icon to quit.

## Voice

- **Speech-to-text: Gladia Live.** Click the mic in the bar: on the home screen you dictate a goal; during a tutorial you ask a question ("where is it?", "I'm done", "show me again") and Holo answers out loud, points, skips or repeats. Needs `GLADIA_API_KEY` and microphone permission for your terminal.
- **Text-to-speech: Gradium Phonon 40m multilingual**, running locally (Rust `ptts` crate, CPU, ~20× real time). The model is gated: accept its terms on [Hugging Face](https://huggingface.co/gradium/phonon-40m-multilingual) and set `HF_TOKEN` or run `hf auth login`. Without access it falls back to the public Phonon 31m. Weights are CC BY-NC 4.0 (non-commercial).

## Tutorials and sessions

A tutorial is a **graph of milestones** (`tutorials/*.json`), not a click script: each milestone has an imperative `goal`, a screen-checkable `done_when`, optional `hints` (known path, may be outdated), `teach`, and graph edges (`next`, `requires`, `optional`). Holo finds the clicks live.

- **Two entries, one harness**: pick a tutorial from the library, or type a goal and Holo plans the milestones from your screen first.
- **Harness**: each milestone runs as its own Holo task (fresh conversation, `Task:` + success criterion + hints). A `<progress>` block with the overall goal and milestone states is re-injected before every screenshot. `answer` reports an explicit `success`, `blocked` or `unknown` outcome. When Rio's autopilot runs a skill on its own, success alone is insufficient: a separate Holo acceptance check on a freshly captured screenshot must explicitly confirm the full `done_when` before the milestone is closed (in tutor mode the learner is there, and the milestone closes on Holo's answer). Missing, negative, ambiguous or malformed checks fail closed. Quoted exact-text criteria are also compared verbatim against the check's visual transcription; the existing AX helper only exposes interactive elements on macOS, not a complete OCR/text tree on Linux. Checks and their fresh screenshots are journaled as `milestone_check` / `milestone_check_failed`.
- **Guarantees**: a model response only acts once validated (complete stream, exactly one known tool, typed arguments, coordinates in [0, 1000], short non-empty `answer` evidence); otherwise it is retried with feedback, up to 3 times, and the milestone stays open. A graph whose required milestones can never start is rejected on load and reported as blocked, never as done. Stop cancels the in-flight step at once; each step has a total deadline of 150 s (est.). When Holo is slow, the bar says so; a stalled stream is retried on a fresh connection.
- **Context window**: each milestone is a fresh conversation, so context never grows with the tutorial. Inside a milestone: the last 3 screenshots, at most 6 observation turns verbatim (fewer when the estimate passes 12k tokens (est.)), older turns folded into a one-line-per-action summary, search results capped at 4,000 characters. Across milestones, `<progress>` is a window that moves with the current milestone: 3 neighbours on each side in full, the rest counted, plus how the last milestone was done and the learner's typed entries. The journal logs our token estimate next to the real prompt tokens to calibrate the budget.
- **Screen watch**: readiness depends on the action. Clicks fire when the screen settles, typing waits for keyboard silence or Enter (key presses are counted, never recorded, and only if macOS already grants the listen permission), shortcuts also fire without visible effect.
- **Learner in the loop**: a question asked during a tutorial joins the current milestone's conversation (as the result of the pending action), Holo answers with `explain` (spoken answer, optional element shown directly, a choice to remember), and the next steps know what was asked. Holo can also ask the learner (`ask_learner`, with optional choices) to make them predict or explain, and fades its help: on actions the learner already did successfully it can hide the pointer (`show_pointer: false`), with a "Show me" button to reveal it.
- **Memory and outcomes**: each action given to the learner is judged on the next screenshot (screen changed, no visible effect, or too small to see for typing). The same action failing twice in a row is pointed out to Holo. Text the learner typed and the evidence of finished milestones carry over to later milestones. A step that took over 4 s (est.) is recomputed once if the screen moved meanwhile. Searches are cached per app and query for an hour (est.); screenshots are written to the journal in the background.
- **Sessions** are journaled in `sessions/<timestamp>-<slug>/`: `session.json` (outcome), `tutorial.json`, `events.jsonl` (milestones, steps with reasoning and latency, learner events, questions) and `shots/` (with `-marked` copies showing where Holo pointed).
- **Agent skill**: `.prime/agent/skills/rio-harness-core/` describes the harness core for [prime-agent](https://github.com/PrimeIntellect-ai/prime-agent) (Agent Skills format, also readable by other agents): the loop, its invariants with their guarding tests, how to measure a change on the simulator, and scripts (`check.sh`, `worktree.sh` to work without restarting the running app, `sim.sh`).
- **Explore sessions**: `python3 tools/session_explorer.py --open` builds `sessions/index.html` (every session, live or simulated, filterable, with outcome, milestones, steps, questions, tokens and Holo stalls) and one page per session (timeline by milestone: screenshot with Holo's point, action and reasoning, the learner's moves, questions and answers, outcomes, retries and challenges). The pages stay in `sessions/`, never committed, since they show the learner's screen.
- **Save as tutorial** at the end of a run writes it back to the library with the path that worked as each milestone's hints: actions never shown, or without effect and then retried, are left out.

## Learner simulator

Rio is measured, not just unit-tested: a **simulated learner** takes real
tutorials and the result is graded by code. Everything lives in
`src-tauri/src/sim/` (tests only, never shipped); details in [sim/README.md](sim/README.md).

1. **The tutor is the real one**: the production loop (`advance_with`, `ask_in_loop`) with real Holo calls, the planner and the knowledge base.
2. **The screen is a headless Chrome**, driven from Rust over the DevTools protocol: it opens a web app (a local notes app in `sim/apps/`, or excalidraw.com), takes screenshots, clicks and types at the chosen points. The real desktop is never touched.
3. **The learner is a model playing a persona** (`diligent`, `novice`, `distracted`, `curious`). It only sees the screenshot, with the tutor's pointer drawn on it, and the tutor's message, never the goal. It decides to do the action (where to click, what to type), answer the tutor's question, or say it is stuck, and proposes a question it could ask.
4. **Mistakes are drawn from a seeded generator** ("misclick 15 % of the time", "ask a question on 25 % of the steps"): the same seed replays the same mistakes, so two versions of the tutor are compared under the same conditions.
5. **After each action** the simulator describes what happened with the same function as the real screen watcher ("the learner clicked the highlighted element, and the screen changed") and hands back to the tutor.
6. **The grade is code, not a model**: a JavaScript check reads the app's real state at the end ("a note Groceries exists with Bread marked important"). This also catches **false completions**: the tutor said "done", the check says no.
7. **Each run** writes a report (success, milestones, actions, mistakes, questions, tokens, time) to `sim/results/` and a full journal to `sessions/`, browsable with the session explorer.

**How it is used**: run version A (before a change) and B (after) on the same scenarios, personas and seeds, one run at a time, read the journals of the failures, fix, repeat. One such series gave 3 successes out of 8 for B against 2 for A, with fewer false completions; a small sample, a trend rather than proof. Many tutor fixes came from reading those journals: unproven "done" challenged, a dead target recognized when Holo rewords it, honest answers to questions, plans that keep the request's names, evidence that is a result and not an icon.

**Inspired by Google's [harness2](https://github.com/google-research/harness2).** This way of working comes from harness2's idea: the *harness* around a model (system prompt, tools, memory, guardrails) is what you improve, and you improve it by **testing variants against an automatic evaluation** instead of trusting intuition. Rio applies it to tutoring: the harness is the tutor loop (`agent.rs`, the prompts, the tools, the knowledge injection), the evaluation is the learner simulator with code-graded scenarios, and each change is a variant measured against the previous one on the same seeds, like harness2's contrastive probing. What Rio did not take is harness2's code: it drives Codex and OpenCode agents on text and code tasks, with no interface for an external agent such as a Rust app, nothing on screens or a human in the loop, and Linux with Gemini on Vertex, so it was not installed or run. Its automatic loop (propose a variant, probe it, keep the best) is not built here yet: a human, or a coding agent with the [`rio-harness-core`](.prime/agent/skills/rio-harness-core/SKILL.md) skill, plays that role by hand. The pieces for automating it are in place (seeded simulator, A/B, graded reports); the main limit is the H quota of 30 requests per minute (a series of 8 runs takes about 20 min (est.)).

## Web search: H agents and Linkup

Rio looks things up on the web in two places. [Linkup](https://linkup.so) is only ever a fallback.

| Where | What it searches with, in order | Code |
|---|---|---|
| **Desktop app**, during a lesson or a question (the agent's `search` tool) | 1. the team's knowledge on the platform (`RIO_API_URL` + `RIO_API_TOKEN`) · 2. **Linkup**, only if `LINKUP_API_KEY` is set in `.env` · 3. Holo answering from what it knows (simulated, marked as such) | `src-tauri/src/search.rs` |
| **Platform**, a tutorial made from a **goal** ("make a pivot table in Calc") | 1. H's deep-search agent **`h/deep-search-pro`** (parallel web workers, cross-checked sources) · 2. **Linkup** web search if the agent cannot start (quota, outage) or brings back nothing | `platform/src/ingest.ts` (`searchGoal`, `searchLinkup`) |
| **Platform**, a tutorial made from a **pasted page** | the page's text; if it is empty or thin (JavaScript, blocked), H's web agent **`h/web-surfer-pro`** reads it in a real browser. No Linkup here | `platform/src/ingest.ts` (`readPage`) |
| **Platform**, a tutorial made from a **YouTube link** | no web search: Gladia transcribes the video, Holo designs the steps | `platform/src/ingest.ts` |

Keys: `LINKUP_API_KEY` in `.env` for the desktop app, and as a Worker secret (`npx wrangler secret put LINKUP_API_KEY`) for the platform. Without it, the desktop app skips straight to step 3, and the platform lets Holo design the goal from its own knowledge (the tutorial says so).

## How it works

### Bibliothèque de skills (Rust)

Une session réussie crée ou met à jour `skills/<tutorial_id>/skill.json` avec
le graph et le chemin réellement suivi, l'app et l'historique du journal.
Les écritures sont atomiques ; `compiled` contient les artefacts de compilation.
Les dates et `muted_until` sont des secondes Unix, `duration_s` est mesurée.
La version du skill est pilotée par l'empreinte structurelle du goal, du départ
et des milestones (identifiants, goals, `done_when`, arêtes et caractère optionnel).
Un run identique ou une modification des hints, de la langue ou de la source
conserve la version et l'éligibilité des scripts ; une modification structurelle
l'incrémente et périme les anciens scripts. L'ordre des milestones est conservé
car il définit aussi le parcours des graphes linéaires sans arêtes explicites.

- `skills_list()` retourne les skills ; `skill_decline({skillId})` enregistre
  un refus. Deux refus consécutifs mettent le skill en sourdine pendant 24 h.
- Sans tutoriel actif, le contexte est vérifié toutes les 3 s via le nom de
  l'app ayant le focus (sans capture). Une app reçoit au plus une proposition
  toutes les 30 min ; `RIO_SKILLS_COOLDOWN_SECONDS` règle ce délai pour les tests.
- `autopilot:propose` contient `{skill_id, title, goal, app, mode}` ; `app` contient
  `name` et, lorsqu'il existe, `bundle_id`.
- `skill_propose_now({skillId})` propose immédiatement un skill déjà réussi,
  même en sourdine (demande explicite), et réinitialise le délai de l'app.
  Cette commande ne lance pas d'exécution automatique.

### Notch « Rio le fait pour toi »

La fenêtre native `notch` affiche les propositions en haut-centre, sans prendre
le focus. Le contrôleur Rust décide des états `hidden`, `expanded`, `compact`.
Après 15 s sans réponse, « Pas maintenant » ou Échap, il enregistre un refus.
Échap est enregistré globalement uniquement pendant l'affichage de la notch.
Les callbacks de raccourcis retournent avant toute opération native : le traitement
est déporté hors du thread d'événements pour éviter l'attente circulaire X11 lors
du désenregistrement d'Échap. Un refus concurrent avec le timer n'est enregistré
qu'une fois ; aucun verrou de contrôleur/proposition n'entoure les appels Tauri
ou l'écriture du refus.

- `autopilot_accept({skillId})` prend le verrou exclusif et émet
  `autopilot:started {skill_id, title, total}`, puis lance un script éligible ou le pilote voie A.
  Il réutilise le graph, ses hints et `agent::advance` : chaque action Holo est
  injectée par notre code existant porté vers `act.rs` (enigo), puis une nouvelle
  capture vérifie les `done_when`. Seul le retour `done` autorise « Fait ✓ ».
- `autopilot:progress {skill_id, index, total, label}` actualise la progression
  (index entre 0 et total). `autopilot:done {skill_id, outcome, message?}` termine
  l'affichage après 3 s ; seul `completed` affiche « Fait ✓ ».
- `autopilot_stop()` positionne le drapeau `autopilot::stop_requested()`, libère
  le verrou d'affichage et émet `autopilot:done` avec `stopped`. Le pilote vérifie
  l'arrêt avant chaque action et sous-étape ; aucun autre run ni tutoriel ne peut
  démarrer avant la fin effective du nettoyage des entrées.
- `autopilot_decline()` refuse la proposition affichée ; `autopilot_view()`
  fournit son état initial au front, ensuite relayé par `autopilot:view`.

Le front ne décide ni du délai, ni de la fin, ni de l'acquisition du verrou.
Une seule surface reprend le verre noir, Geist, les bordures et l'ombre de la
barre Rio, avec les rayons et la courbe d'apparition du site. Le morph utilise
le spring de `motion` déjà installé ; les contenus se croisent en fondu/flou.
La fenêtre conserve son encombrement maximal pour ne pas couper l'animation ;
le Rust reçoit les limites visuelles via `notch_surface` et laisse passer les
clics hors de la surface, y compris dans les coins arrondis. Le repli termine
son animation avant le masquage natif. `prefers-reduced-motion` supprime les
transitions, le flou animé et le shimmer de progression.
Le pilote est borné à 20 actions par jalon, 80 au total, 300 s et 3 échecs Holo
ou tours sans progrès consécutifs. Le délai de stabilisation est de 650 ms
(configuration, pas une mesure). Une session `mode: rio` et les événements
`rio_action`, `rio_no_progress`, `rio_holo_failure`, `rio_done` sont journalisés ;
chaque issue ajoute un run avec durée mesurée au skill. Le déclencheur de skills
et les clics tuteur sont suspendus pendant l'exécution. Les fenêtres Rio sont
masquées sur le thread UI avant chaque capture envoyée à Holo (y compris Linux),
puis seule la notch est réaffichée. Elle est également masquée pendant l'injection
pour ne pas intercepter un clic destiné à l'application. Un identifiant de run
invalide les sous-actions retardées après un arrêt ; sur macOS, les événements
injectés sont en plus marqués et ignorés par le capteur de clics utilisateur.
Les événements `autopilot:done` reçus du front
ne peuvent pas déclarer une réussite.

Linux nécessite X11 (`DISPLAY`) ; Wayland est refusé explicitement. Sur macOS,
il faut aussi autoriser Rio dans **Accessibilité**. Les raccourcis utilisent les
touches et modificateurs connus ; textes vides, multilignes ou de plus de
512 caractères, touches inconnues et actions non prises en charge sont refusés.
Les coordonnées partagent la conversion du pointeur (origine du moniteur principal,
pixels physiques, puis facteur d'échelle pour les coordonnées logiques macOS).

### Scripts testés par Devin (voie B)

`skill_compile({skillId})` démarre une compilation en arrière-plan, avec une seule
session en vol par skill. Après une réussite, Rio compile aussi automatiquement
si aucun artefact terminé ne correspond à la version du graph ;
`RIO_AUTO_COMPILE=0` désactive ce déclenchement. `DEVIN_API_KEY` et `DEVIN_ORG_ID`
sont lus dans le même environnement/.env que Holo, uniquement côté Rust.
Le client utilise l'API v3 et demande une sortie structurée, un script paramétré
et l'exécution de chaque test `done_when` sur la plateforme cible.

- `RIO_COMPILE_MAX_ACU` : plafond par session, 2 par défaut.
- `RIO_COMPILE_TIMEOUT_SECONDS` : délai maximal, 1800 par défaut ; polling toutes les 30 s.
- `autopilot:compile {skill_id, status, url?}` : création, suivi et issue.
- `compiled[]` conserve la session, les paramètres, les preuves, l'ACU retourné,
  le SHA-256 et la version du graph, avec écritures atomiques.

Seuls les artefacts terminés, `tested: true`, sur l'OS courant et la version
courante, dont le hash recalculé correspond, sont proposés en mode `script`.
Une session Devin `waiting_for_user` n'est acceptée que si elle a fourni sa sortie
structurée ; une attente sans sortie, une approbation ou une erreur ne suffit pas.
La notch affiche « Script testé par Devin » ; le front ne sélectionne pas le mode.

Les paramètres par défaut sont transmis comme arguments séparés, sans shell
intermédiaire. Le processus reçoit un environnement restreint, sans clés API.
Arrêter tue son groupe de processus ; `RIO_SCRIPT_TIMEOUT_SECONDS` limite aussi
l'exécution (300 s par défaut). Une capture fraîche et `advance` vérifient toujours
le résultat. Tout échec du script ou de cette vérification provoque un repli
journalisé vers la voie A. Le run est enregistré en mode `script`, ou `rio` en cas
de repli ; aucun succès n'est déclaré sur le seul code de sortie du processus.

```
Bar (React)                Rust (src-tauri)                          H Models API
───────────                ────────────────                          ────────────
goal + Enter ──────────▶   plan_tutorial: screenshot + goal ──────▶  holo4-27b → steps {instruction, target}
step i ────────────────▶   locate: screenshot + target ───────────▶  holo4-35b-a3b → (x, y) in 0..1000
                           → logical px ──▶ overlay: ghost cursor
user clicks ───────────▶   clicks.rs: real click near target? ──▶   step done (no API call)
"Done" button ─────────▶   check_step: BEFORE + NOW screenshots ──▶  {done, feedback}
```

- `src-tauri/src/capture.rs`: primary display capture (xcap), downscaled to 1600 px, JPEG.
- `src-tauri/src/holo.rs`: Models API client (`structured_outputs`, thinking off).
- `src-tauri/src/clicks.rs`: watches real left clicks via CoreGraphics (no extra permission).
- `src-tauri/src/voice.rs`: Phonon TTS on a dedicated thread.
- `src-tauri/src/stt.rs`: microphone capture (cpal) → 16 kHz PCM → Gladia Live WebSocket.
- `src-tauri/src/panel.rs`: turns windows into non-activating `NSPanel`s so they float over full-screen apps.
- `src-tauri/src/tray.rs`: menu bar icon, bottom bar placement, global shortcut.
- `src-tauri/src/lib.rs`: Tauri commands, click-through overlay, coordinate mapping.
- `src/panel/`: the bar UI. `src/overlay/`: the ghost cursor.

Both windows are excluded from screen captures, so Holo never sees the app itself.

## Next

- Apply the autopilot's final goal check to tutor mode, which can still announce "done" too early.
- Ask the learner what they want before planning a vague request ("more realistic": bark? leaves? shape?).
- Pre-localize the pointer at the start of a step and cache it, to cut the wait before the ghost cursor appears.
- A one-click installer for macOS.
