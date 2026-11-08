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
- **Harness**: each milestone runs as its own Holo task (fresh conversation, `Task:` + success criterion + hints). A `<progress>` block with the overall goal and milestone states is re-injected before every screenshot. Holo calls `answer` when the success criterion is visible; the harness moves to the next milestone on the same screenshot.
- **Guarantees**: a model response only acts once validated (complete stream, exactly one known tool, typed arguments, coordinates in [0, 1000], short non-empty `answer` evidence); otherwise it is retried with feedback, up to 3 times, and the milestone stays open. A graph whose required milestones can never start is rejected on load and reported as blocked, never as done. Stop cancels the in-flight step at once; each step has a total deadline of 150 s (est.). When Holo is slow, the bar says so; a stalled stream is retried on a fresh connection.
- **Context window**: each milestone is a fresh conversation, so context never grows with the tutorial. Inside a milestone: the last 3 screenshots, at most 6 observation turns verbatim (fewer when the estimate passes 12k tokens (est.)), older turns folded into a one-line-per-action summary, search results capped at 4,000 characters. Across milestones, `<progress>` is a window that moves with the current milestone: 3 neighbours on each side in full, the rest counted, plus how the last milestone was done and the learner's typed entries. The journal logs our token estimate next to the real prompt tokens to calibrate the budget.
- **Screen watch**: readiness depends on the action. Clicks fire when the screen settles, typing waits for keyboard silence or Enter (key presses are counted, never recorded, and only if macOS already grants the listen permission), shortcuts also fire without visible effect.
- **Learner in the loop**: a question asked during a tutorial joins the current milestone's conversation (as the result of the pending action), Holo answers with `explain` (spoken answer, optional element shown directly, a choice to remember), and the next steps know what was asked. Holo can also ask the learner (`ask_learner`, with optional choices) to make them predict or explain, and fades its help: on actions the learner already did successfully it can hide the pointer (`show_pointer: false`), with a "Montre-moi" button to reveal it.
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
  Aucune UI ni exécution automatique n'est ajoutée dans ce bloc.

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
