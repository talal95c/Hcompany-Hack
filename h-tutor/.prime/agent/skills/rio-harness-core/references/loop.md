# The step pipeline

All in `src-tauri/src/agent.rs` unless noted.

## Entry points

| Function | Called by | Does |
|---|---|---|
| `Session::new(tutorial, lang)` | `tutor_start` (lib.rs) | Opens the journal, starts the first milestone |
| `advance(brain, session, event, only_if_changed)` | `tutor_next`, `tutor_start`, `tutor_skip_milestone` | Captures the primary screen, then `advance_with` |
| `advance_with(..., stale_after, capture)` | `advance`, simulator | Injected capture; recomputes a slow step once if the screen moved |
| `ask_in_loop(brain, session, question, shot)` | `ask` (lib.rs), simulator | A learner question inside the milestone conversation; Holo replies with `explain` |
| `to_tutorial(session)` | save, skills | The run as a reusable tutorial, with the path that worked as hints |

## One `advance_on`

1. Unchanged screen and `only_if_changed`: return the current step.
2. `observe_outcome`: the last proposed action becomes `Changed`, `NoEffect`
   or `Unknown` (typing too small to see). Two `NoEffect` on the same target
   (points within `SAME_TARGET`) add a note telling Holo to stop insisting.
3. Loop while the tutorial is not finished:
   - blocked graph → error; no current milestone → error;
   - `ask_holo` → `Turn::Action(step)`: store it, return it;
   - `Turn::MilestoneDone(id)`: push to `completed`, `start_next_milestone`.
   Each closure finishes a milestone, so the loop is bounded by the graph.
4. Complete: journal, record the skill run, return a `done` step.

## One `ask_holo`

1. `ensure_knowledge`: once per milestone, `Brain::knowledge(app, goal)`; a
   relevant path is appended to the task message (message 1).
2. The pending call gets its tool result (the learner's event, or a neutral
   one): the conversation is always valid for the API.
3. `observe`: `compact` (history bounds), then a user message with the
   `<progress>` block, `<observation>` + screenshot, and on the very first
   look of a tutorial the `FIRST_LOOK` note. `trim_images` keeps 3 screenshots.
4. `choose(brain, session, tools, metrics)`:
   - up to `MAX_ATTEMPTS` requests; each response must pass `validate`
     (complete stream, exactly one offered tool, id, typed args, coordinates
     in [0, 1000], short non-empty `answer` evidence); a refusal adds feedback
     to the retry only, never to the milestone history;
   - `search` runs inside and is withdrawn after `MAX_SEARCHES`;
   - the accepted call is appended and becomes `pending_call`.
5. `answer` with `unproven()` (actions in this milestone, none effective):
   challenged, up to `MAX_CHALLENGES` per milestone, then `choose` again.
6. Journal the step (latency, model time, requests, tokens, context estimate).
7. Map the action to a `Step` (`click`, `write`, `scroll`, `press_key`,
   `ask_learner`; `hint_only` when `show_pointer` is false) and record it as
   `Proposed` for the next outcome check.

## Session state that matters

- `messages`: the current milestone's conversation only (reset per milestone).
- `pending_call`: the tool call waiting for the learner's result.
- `actions[milestone]`: `ActionRecord { path, outcome, typed, point }`.
- `facts`: learner entries and choices carried to later milestones.
- `status`, `current`, `finished`, `blocked`, `completed` (closed since the last shown step).
- `step`: what the UI shows; `pending` while a new milestone has no action yet.
- `before`: the screen the current step was computed on.

## Around the core

- `tutorial.rs`: `next(finished)` is the scheduler; `validate()` runs it to
  reject graphs whose required milestones can never start.
- `cancel.rs`: `Generation::run(gen, STEP_DEADLINE, work)`; Stop bumps the
  generation and the in-flight step is dropped at once.
- `holo.rs`: `chat_stream` (3 attempts on fresh connections, waits on 429),
  `Sse` (byte-buffered UTF-8, stops on `[DONE]`, a cut stream is an error).
- `watch.rs`: `Mode::for_kind` (Pointer, Typing, Keys) decides when the
  learner's action looks finished; `describe_event` is the text Holo receives.
