---
name: rio-harness-core
description: Rio's tutor harness core in Rust (h-tutor/src-tauri/src/agent.rs and friends) - the loop where Holo, a vision model, picks one GUI action per step and a human learner performs it, organized as a graph of milestones. Use when reading, changing, debugging, testing or measuring that loop - validation of tool calls, milestone transitions, the answer challenge, context and history bounds, the knowledge base per milestone, learner questions (explain, ask_learner), cancellation - or when running the learner simulator or the session explorer. Explains the invariants that must hold and how to work without restarting the running dev app.
license: MIT
compatibility: Rust 1.88+ (edition 2024), macOS for the desktop app; Google Chrome for the learner simulator; Python 3 for the session explorer.
metadata:
  repo: https://github.com/Jacqkues/rio
  crate: h-tutor/src-tauri (lib rio_lib)
---

# Rio harness core

Rio teaches software by doing. Each step, **Holo** (H Company's vision model,
`holo4-27b`) looks at a screenshot and picks **one** GUI action through native
tool calls; **the learner performs it**; the next screenshot shows what
happened. A tutorial is a **graph of milestones** (screen-checkable sub-goals),
each run as its own short conversation.

The core is plain Rust, independent of the UI:

| File | Role |
|---|---|
| `src-tauri/src/agent.rs` | The loop: `Session`, `advance` / `advance_with` / `advance_on`, `ask_holo`, `choose`, `validate`, `ask_in_loop`, `compact`, `to_tutorial`, the `Brain` trait |
| `src-tauri/src/tutorial.rs` | Milestone graph, `Tutorial::next` → `Ready` / `Complete` / `Blocked`, `validate` |
| `src-tauri/src/cancel.rs` | `Generation`: Stop and the per-step deadline |
| `src-tauri/src/watch.rs` | When to look again (screen settles, keys, clicks), `describe_event` |
| `src-tauri/src/holo.rs` | Holo client: streaming (SSE), retries on fresh connections, 429 waits |
| `src-tauri/src/planner.rs` | Request → milestone graph |
| `src-tauri/src/platform.rs` | Organization knowledge base (`lookup`, relevance filter) |
| `src-tauri/src/sim/` | Learner simulator (tests only): headless Chrome, personas, graded by code |

`lib.rs` (Tauri commands, overlay, clicks) is the shell around the core, not the core.

## Before you change anything

1. **Do not restart the running app by accident.** `npm run tauri dev` rebuilds
   and relaunches Rio on every change under `src-tauri/` or `src/`; a learner's
   step in flight is lost. For experiments, work in an isolated worktree:
   `scripts/worktree.sh <branch>` (clones `target/` so the first build is fast).
   Editing files outside `src-tauri/` and `src/` (like this skill) is safe.
2. Read [references/loop.md](references/loop.md) for the step pipeline and
   [references/invariants.md](references/invariants.md) for what must stay true.
3. Every change keeps the gates green: `scripts/check.sh` (rustfmt, clippy with
   no warning, all unit tests). The `Brain` trait lets tests script Holo
   (`Fake` in `agent.rs` tests): no network, no screen.

## The loop in one paragraph

`advance` captures the screen and calls `advance_with`, which runs
`advance_on` and, if the step was slow and the screen moved, recomputes it
once. `advance_on` judges the previous action's outcome on the new screenshot,
then loops `ask_holo` until Holo gives an action, the tutorial is really
complete, or the graph is blocked. `ask_holo` loads the milestone's knowledge
once, appends an observation (progress block + screenshot), and calls
`choose`, which asks Holo until a response passes `validate` (searches run
inside). An `answer` closes the milestone, unless nothing the learner did had
any visible effect: then it is challenged (at most twice per milestone).

## Changing it safely

- Add the behavior behind the existing seams: a new tool → `tools()` /
  `question_tools()` + a typed args struct + a `validate` arm + its handling in
  `ask_holo`; a new memory → `Session` field + `progress_block`; a new limit →
  a named `const` with how it was measured, or `(est.)` if it was not.
- Write the test first with `Fake` (see `five_closures_then_an_action_on_the_sixth`,
  `an_unproven_answer_is_challenged_twice`, `a_question_joins_the_milestone_conversation`).
- Then measure on the simulator, A against B with the same seeds:
  [references/measure.md](references/measure.md). A unit test proves the
  mechanism; only the simulator says whether the tutor got better.
- Durations and thresholds that were not measured carry `(est.)` in comments.

## Scripts

- `scripts/check.sh [repo-dir]`: rustfmt check, clippy (warnings fail), unit tests.
- `scripts/worktree.sh <branch> [base]`: isolated worktree + cloned build cache, for work that must not restart the running app.
- `scripts/sim.sh <scenario> <personas> [seeds]`: learner simulator runs (real Holo calls, costs tokens; one at a time: the account allows 30 requests/min).
