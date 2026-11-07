# Learner simulator

Runs the real tutor harness against a **simulated learner** in a headless
Chrome, and grades the result with code. Nothing touches the real desktop.

- **Tutor**: the production loop (`advance_with`, `ask_in_loop`) with real Holo calls.
- **Screen**: headless Chrome driven over the DevTools protocol (`src-tauri/src/sim/browser.rs`).
- **Learner**: a model playing a persona sees only the screenshot (with the
  tutor's pointer drawn) and the tutor's message, never the goal. How often it
  misclicks or asks a question is drawn by a seeded generator, so runs replay.
- **Grade**: a JavaScript check in the page (`success` in the scenario), not a model.

## Run

```sh
cd src-tauri
# Browser driver only, no model (fast):
cargo test --lib sim::tests::browser_drives_the_notebook -- --ignored
# Simulated sessions (real Holo calls, costs tokens):
SIM_SCENARIO=notebook-groceries SIM_PERSONA=diligent,novice SIM_SEEDS=2 \
  cargo test --lib sim::tests::simulate -- --ignored --nocapture
```

Reports land in `sim/results/<timestamp>-<scenario>.json` (not committed);
each run also has a full session journal in `sessions/`.

## Scenarios (`scenarios/*.json`)

`id`, `app`, `url` (`http(s)://…` or a path under `sim/`), `goal`, `lang`,
`max_steps`, `success` (JavaScript expression), optional fixed `tutorial`
(otherwise Holo plans it from the goal and the first screen).

- `notebook-groceries`, `notebook-journal`: local test app `apps/notebook.html`
  (menus, sidebar, dialogs, an unlabeled toolbar icon; state in `window.app`).
- `excalidraw-hello`: excalidraw.com (needs network).

## Personas (`src-tauri/src/sim/learner.rs`)

`diligent` (exact, no questions), `novice` (15 % misclicks, asks 25 % of
steps), `distracted` (30 % misclicks), `curious` (asks half the time).

## Report fields

`success` (the check passed), `tutor_done`, `false_done` (the tutor said done but the check failed), `milestones_done/total`,
`tutor_steps`, `learner_actions`, `misclicks`, `questions`,
`explanations_pointing`, `tutor_questions`, `hint_only_steps`, `reveals`,
`stuck`, `errors`, `wall_s`, `holo_requests`, `holo_model_s`,
`invalid_responses`, `retries`, `prompt_tokens`, `completion_tokens`, `session`.
