# Measuring a change

A unit test proves a mechanism; the **learner simulator** says whether the
tutor got better. Compare A (before) and B (after) on the same scenarios,
personas and seeds.

## Learner simulator (`src-tauri/src/sim/`, tests only)

- The production loop (`advance_with`, `ask_in_loop`) with real Holo calls.
- The screen is a headless Chrome over the DevTools protocol; nothing touches the desktop.
- The learner is a model playing a persona (`diligent`, `novice`, `distracted`,
  `curious`); misclicks and questions are drawn from a seeded generator, so a
  seed replays the same mistakes.
- The grade is a JavaScript check in the page (`success` in the scenario), not a model.

```sh
cd h-tutor/src-tauri
cargo test --lib sim::tests::browser_drives_the_notebook -- --ignored   # driver only, no model
SIM_SCENARIO=notebook-groceries SIM_PERSONA=diligent,novice SIM_SEEDS=2 \
  cargo test --lib sim::tests::simulate -- --ignored --nocapture
```

Scenarios live in `h-tutor/sim/scenarios/*.json`; reports in
`h-tutor/sim/results/` (not committed). Key report fields: `success`,
`false_done` (the tutor said done, the check failed: the worst outcome),
`milestones_done/total`, `learner_actions`, `misclicks`, `questions`,
`holo_requests`, `prompt_tokens`, `errors`.

**Quota**: the H account (tier 1) allows 30 requests/min on `holo4-27b`. Run
one simulation at a time; parallel runs fail on 429 and measure nothing.

## A/B recipe

1. `scripts/worktree.sh ab-baseline <base-commit>` → baseline A in its own worktree.
2. Copy the *same* simulator into A (`src-tauri/src/sim/`), so only the tutor differs.
3. Run A then B alternately, one at a time, same scenarios × personas × seeds.
4. Compare `success`, `false_done`, actions and time; read the journals of
   every run that changed outcome before concluding. With 8 runs per side it
   is a trend, not proof.

## Retrieval quality (no model)

```sh
cargo test --lib platform::tests::retrieval_quality -- --ignored --nocapture
```
Milestone-like goals against the configured platform (`RIO_API_URL`,
`RIO_API_TOKEN` in `h-tutor/.env`). Tune `MIN_COSINE` and friends on it.

## Session journal and explorer

Every run writes `h-tutor/sessions/<id>/` (`events.jsonl`, `tutorial.json`,
`shots/`). `python3 tools/session_explorer.py --open` builds an HTML index and
one timeline per session.

Useful events: `step` (action, reasoning, latency, tokens, `context_tokens_est`),
`learner`, `action_outcome`, `answer_challenged`, `invalid_action`,
`milestone_knowledge` / `plan_knowledge` / `knowledge_error`, `explain`,
`learner_question`, `ask_learner`, `holo_retry`, `holo_rate_limited`,
`holo_first_chunk`, `stale_step`, `sim_learner`, `sim_action`, `sim_error`.
