# Rio

[![Rio](brand/rio-hill.jpg)](https://rio.vignemale.com)

A live software coach. Tell it what you want to learn: Holo (H Company) looks at your screen, breaks the task into steps, and a ghost cursor shows you where to click. You do each action yourself; the app sees your click and moves on.

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

## Démo observation

Depuis `h-tutor/`, sur macOS :

```sh
npm run demo:skill
RIO_OBSERVE=1 RIO_OBSERVE_STEPS=3 RIO_SKILLS_COOLDOWN_SECONDS=0 RIO_AUTO_COMPILE=0 npm run tauri dev
```

Le modèle Holo doit déjà être configuré et Rio doit avoir l’autorisation
d’enregistrer l’écran. L’observation envoie des captures au cloud : utiliser un
bureau de démonstration sans données privées, sur l’écran principal. Ne pas
lancer de tutoriel ni d’autopilot pendant l’observation.

L’installateur copie `demo/textedit-courses/skill.json` vers
`skills/demo-textedit-courses/skill.json`, exactement le dossier lu par
`skills::dir()` (pas de variable d’environnement de remplacement actuellement).
Ce dossier local est ignoré par Git. Une installation identique est laissée
inchangée ; un dossier différent provoque un refus explicite, sans écrasement.
La fixture contient **une réussite synthétique réservée à la démo**, pas une
preuve d’une exécution réelle, et aucun script compilé. Le graphe est inclus
dans `skill.json` : aucun tutoriel séparé n’est nécessaire.

1. Ouvrir **TextEdit**, créer un document vide avec `⌘N`, choisir **Format →
   Convertir au format RTF** si le document est en texte brut. Fermer les
   dialogues ; garder le document sur l’écran principal et TextEdit au premier
   plan. Son nom d’application est `TextEdit` (xcap lit `kCGWindowOwnerName` ;
   le watcher compare les noms sans tenir compte de la casse).
2. Attendre une première prise de référence locale (environ 4 s, est.), puis
   redimensionner franchement la fenêtre et la laisser immobile environ 20 s
   (est.). Cela déclenche le contrôle du premier jalon : document ouvert.
3. Saisir exactement **`Liste de courses`**, sans Retour. Redimensionner à
   nouveau la fenêtre, puis attendre environ 20 s (est.), sans changer d’app.
4. Sélectionner le titre avec `⌘A`, puis `⌘B` pour le mettre en gras. Avec la
   souris, placer le curseur à la fin du titre, sans Retour. Redimensionner à
   nouveau et attendre environ 20 s (est.).
5. La proposition attendue est **« Tu es en train de faire Préparer une liste
   de courses (3/6). Je termine pour toi ? »**. Cliquer **Oui, vas-y**.
   Rio GUI revérifie les jalons existants puis ajoute `Pommes`, `Pain`, `Lait`,
   chacun sur sa propre ligne, en expliquant ses actions en français.

Le premier critère reste vrai après la saisie du titre : c’est volontaire pour
que la reprise GUI puisse revérifier les trois premiers jalons sans effacer le
travail déjà fait. Les critères suivants exigent le texte exact et l’ordre des
lignes. Résultat attendu :

```text
Liste de courses     ← en gras
Pommes
Pain
Lait
```

Les changements de quelques lettres peuvent être trop petits pour la miniature
locale ; le redimensionnement après chaque étape assure un changement net avant
la stabilisation. Si la proposition n’apparaît pas, rester dans TextEdit et
redimensionner à nouveau. Une vérification inconnue ne compte jamais. Une autre
skill TextEdit à égalité empêche la proposition ; changer d’app réinitialise les
jalons observés. Deux refus activent toujours la sourdine de 24 h, même avec le
cooldown à zéro. L’installateur ne réinitialise pas une skill modifiée : sauvegarder
ou déplacer explicitement son dossier local avant une nouvelle installation.

### Variante Microsoft Excel pour Mac — Calculer le total des courses

Microsoft Excel doit être installé et activé sur le Mac. Depuis `h-tutor/` :

```sh
npm run demo:skill -- excel
RIO_OBSERVE=1 RIO_OBSERVE_STEPS=3 RIO_SKILLS_COOLDOWN_SECONDS=0 RIO_AUTO_COMPILE=0 npm run tauri dev
```

Sans argument, l’installateur continue d’installer TextEdit. L’argument `excel`
installe `demo/excel-courses/skill.json` dans
`skills/demo-excel-courses/skill.json`, sans toucher à TextEdit. Les mêmes règles
de refus d’écrasement s’appliquent. La réussite incluse est synthétique, réservée
à la démo, et aucun script n’est compilé. Le nom d’application attendu par xcap
est **`Microsoft Excel`**, pas `Excel`.

Les permissions, l’écran principal et les précautions de confidentialité décrits
ci-dessus restent nécessaires. Garder Excel au premier plan pendant les étapes :

1. Ouvrir un **nouveau classeur vierge** avec `⌘N`. Fermer les dialogues,
   afficher la feuille avec **A1:B5** visibles et la barre de formule affichée
   (onglet **Affichage**, si nécessaire). Attendre environ 4 s (est.) pour la
   référence locale, redimensionner franchement la fenêtre, puis la laisser
   immobile environ 20 s (est.) pour le premier contrôle.
2. Cliquer **A1**, saisir exactement **`Produit`**, appuyer sur **Tab**, saisir
   **`Prix`**, puis **Entrée** pour valider. Redimensionner à nouveau et attendre
   environ 20 s (est.), sans changer d’application.
3. Cliquer **A2**, saisir exactement **`Pommes`**, **Entrée**, **`Pain`**,
   **Entrée**, **`Lait`**, **Entrée**. Ne pas saisir les prix soi-même.
   Redimensionner à nouveau et attendre environ 20 s (est.).
4. Accepter **« Tu es en train de faire Calculer le total des courses (3/7).
   Je termine pour toi ? »** avec **Oui, vas-y**. Rio GUI revérifie les trois
   jalons puis saisit les prix, la somme, et met les deux lignes en gras.

Résultat attendu :

| Cellule | Contenu |
|---|---|
| A1 / B1 | **Produit / Prix** |
| A2 / B2 | Pommes / 2 |
| A3 / B3 | Pain / 3 |
| A4 / B4 | Lait / 1,5 (ou 1.5) |
| A5 / B5 | **Total / 6,5 (ou 6.5)** |

Pour prouver le cinquième jalon sur **une seule capture**, B5 doit être
sélectionnée : la cellule affiche **6,5** ou **6.5** et la barre de formule
montre **`=SOMME(B2:B4)`** ou **`=SUM(B2:B4)`**, selon la langue d’Excel.
Une constante `6,5` ne suffit pas. Les hints indiquent les deux noms de fonction,
le séparateur décimal local et les actions concrètes cellule/Entrée/Tab/`⌘B`.
Le premier critère reste vrai après remplissage du classeur pour permettre la
reprise sans effacer les données. Si le contrôle reste inconnu, redimensionner
de nouveau en gardant Excel actif ; une autre skill Excel à égalité empêche la
proposition et les refus conservent la sourdine habituelle.

## Next

### Opt-in skill observation

Autopilot GUI actions are narrated in French by the local Phonon TTS, including
the first action of each new milestone. The sentence is also shown in the notch.
Set `RIO_NARRATE=0` to disable narration (default on). Speech waits at most six
seconds including synthesis (est.), then is cut off before the action; Stop
interrupts playback immediately. Missing/unavailable TTS is logged and does not
prevent execution. No extra model call is made for narration: the existing action
response supplies the French sentence.

`RIO_OBSERVE=1` enables cloud vision observation while no tutorial or autopilot
is running. Default off: the existing focus-only proposals do not send observation
screenshots to Holo. Only apps with a previously successful, unmuted skill are
observed. A local thumbnail change followed by a stable sample triggers at most
one fresh visual check, at most ten checks/minute. The watcher samples every
three seconds (est.); progress resets on app change or five minutes of inactivity
(est.). `RIO_OBSERVE_STEPS` sets the proposal threshold (default 3).

Only explicit `met` with evidence counts. A unique leading skill is proposed;
cooldown and two-declines mute still apply. Acceptance remains required. Observed
proposals always use the Rio GUI driver, never a full-task Devin script. The
driver checks existing milestones on fresh screens before continuing rather than
trusting old observation matches as completed work. Observation captures the
primary display, so keep the target app there for this demo.

- Import a tutorial from a URL with the Agents SDK (`h/web-surfer-pro` + `answerSchema`).
- "Do it for me" button with the desktop agent (`holo local desktop`).
