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
- **Harness**: each milestone runs as its own Holo task (fresh conversation, `Task:` + success criterion + hints). A `<progress>` block with the overall goal and milestone states is re-injected before every screenshot. Holo calls `answer` when the success criterion is visible; the harness moves to the next milestone on the same screenshot.
- **Sessions** are journaled in `sessions/<timestamp>-<slug>/`: `session.json` (outcome), `tutorial.json`, `events.jsonl` (milestones, steps with reasoning and latency, learner events, questions) and `shots/` (with `-marked` copies showing where Holo pointed).
- **Save as tutorial** at the end of a run writes it back to the library with the path actually taken as each milestone's hints.

## How it works

### Bibliothèque de skills (Rust)

Une session réussie crée ou met à jour `skills/<tutorial_id>/skill.json` avec
le graph et le chemin réellement suivi, l'app et l'historique du journal.
Les écritures sont atomiques ; `compiled` reste vide (aucun script exécuté).
Les dates et `muted_until` sont des secondes Unix, `duration_s` est mesurée.

- `skills_list()` retourne les skills ; `skill_decline({skillId})` enregistre
  un refus. Deux refus consécutifs mettent le skill en sourdine pendant 24 h.
- Sans tutoriel actif, le contexte est vérifié toutes les 3 s via le nom de
  l'app ayant le focus (sans capture). Une app reçoit au plus une proposition
  toutes les 30 min ; `RIO_SKILLS_COOLDOWN_SECONDS` règle ce délai pour les tests.
- `autopilot:propose` contient `{skill_id, title, goal, app}` ; `app` contient
  `name` et, lorsqu'il existe, `bundle_id`.
- `skill_propose_now({skillId})` propose immédiatement un skill déjà réussi,
  même en sourdine (demande explicite), et réinitialise le délai de l'app.
  Cette commande ne lance pas d'exécution automatique.

### Notch « Rio le fait pour toi »

La fenêtre native `notch` affiche les propositions en haut-centre, sans prendre
le focus. Le contrôleur Rust décide des états `hidden`, `expanded`, `compact`.
Après 15 s sans réponse, « Pas maintenant » ou Échap, il enregistre un refus.
Échap est enregistré globalement uniquement pendant l'affichage de la notch.

- `autopilot_accept({skillId})` prend le verrou exclusif et émet
  `autopilot:started {skill_id, title, total}`. Le pilote n'est pas encore
  implémenté : la notch attend, sans prétendre exécuter la tâche.
- `autopilot:progress {skill_id, index, total, label}` actualise la progression
  (index entre 0 et total). `autopilot:done {skill_id, outcome, message?}` termine
  l'affichage après 3 s ; seul `completed` affiche « Fait ✓ ».
- `autopilot_stop()` positionne le drapeau `autopilot::stop_requested()`, libère
  le verrou et émet `autopilot:done` avec `stopped`. Le futur pilote doit consulter
  ce drapeau avant chaque action et après chaque attente.
- `autopilot_decline()` refuse la proposition affichée ; `autopilot_view()`
  fournit son état initial au front, ensuite relayé par `autopilot:view`.

Le front ne décide ni du délai, ni de la fin, ni de l'acquisition du verrou.
Les actions n'injectent encore aucune entrée sur le bureau.

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
