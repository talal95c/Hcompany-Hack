# Rio

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
- Type a goal, press Enter. Follow the ghost cursor; progress also shows in the menu bar.
- Esc hides the bar when no tutorial is running. Right-click the menu bar icon to quit.

## Voice

- **Speech-to-text: Gladia Live.** Click the mic in the bar: on the home screen you dictate a goal; during a tutorial you ask a question ("where is it?", "I'm done", "show me again") and Holo answers out loud, points, skips or repeats. Needs `GLADIA_API_KEY` and microphone permission for your terminal.
- **Text-to-speech: Gradium Phonon 40m multilingual**, running locally (Rust `ptts` crate, CPU, ~20× real time). The model is gated: accept its terms on [Hugging Face](https://huggingface.co/gradium/phonon-40m-multilingual) and set `HF_TOKEN` or run `hf auth login`. Without access it falls back to the public Phonon 31m. Weights are CC BY-NC 4.0 (non-commercial).

## Tutorials and sessions

A tutorial is a **graph of milestones** (`tutorials/*.json`), not a click script: each milestone has an imperative `goal`, a screen-checkable `done_when`, optional `hints` (known path, may be outdated), `teach`, and graph edges (`next`, `requires`, `optional`). Holo finds the clicks live.

- **Two entries, one harness**: pick a tutorial from the library, or type a goal and Holo plans the milestones from your screen first.
- **Harness**: each milestone runs as its own Holo task (fresh conversation, `Task:` + success criterion + hints). A `<progress>` block with the overall goal and milestone states is re-injected before every screenshot. `answer` reports an explicit `success`, `blocked` or `unknown` outcome. Success alone is insufficient: a separate Holo acceptance check on a freshly captured screenshot must explicitly confirm the full `done_when` before the milestone is closed, in both tutor and Rio modes. Missing, negative, ambiguous or malformed checks fail closed. Quoted exact-text criteria are also compared verbatim against the check's visual transcription; the existing AX helper only exposes interactive elements on macOS, not a complete OCR/text tree on Linux. Checks and their fresh screenshots are journaled as `milestone_check` / `milestone_check_failed`.
- **Sessions** are journaled in `sessions/<timestamp>-<slug>/`: `session.json` (outcome), `tutorial.json`, `events.jsonl` (milestones, steps with reasoning and latency, learner events, questions) and `shots/` (with `-marked` copies showing where Holo pointed).
- **Save as tutorial** at the end of a run writes it back to the library with the path actually taken as each milestone's hints.

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

- Import a tutorial from a URL with the Agents SDK (`h/web-surfer-pro` + `answerSchema`).
- "Do it for me" button with the desktop agent (`holo local desktop`).
