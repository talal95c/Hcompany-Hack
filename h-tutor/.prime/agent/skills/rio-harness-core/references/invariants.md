# Invariants

What must stay true, where it is enforced, and the test that guards it
(`cargo test --lib <test name>` in `h-tutor/src-tauri`). Breaking one of
these is a regression even if the tutor seems to work.

| Invariant | Enforced in | Guarding test |
|---|---|---|
| Only a validated response can act or close a milestone; a refused one is never executed | `validate`, `choose` | `truncated_answers_leave_the_milestone_open`, `a_refused_answer_on_the_last_attempt_is_not_executed`, `every_explaining_answer_is_refused` |
| Tools are those offered for the turn (no `click` while answering a question, no `explain` in an action turn) | `validate(msg, offered)` | `tools_are_kept_to_their_turn` |
| Coordinates out of [0, 1000] are refused, never clamped | `point` | `rejects_out_of_range_and_missing_fields` |
| "Done" means the graph says complete; a blocked graph is an error, never "done" | `Tutorial::next`, `start_next_milestone` | `chaining_through_every_milestone_finishes_for_real`, `blocked_graph_reports_an_error_not_done`, `mutual_requires_is_blocked_and_rejected` |
| A closed milestone's pointer is never shown again; progress survives a failed request | `start_next_milestone` (`pending` step), `completed` | `failed_transition_keeps_progress_and_drops_the_old_pointer`, `skipping_drops_the_previous_pointer` |
| Every tool call gets its result before the next message (valid conversation) | `ask_holo`, `ask_in_loop`, search pushed with its result | `learner_report_answers_the_pending_call`, `a_question_joins_the_milestone_conversation` |
| An `answer` after only ineffective actions is challenged, at most twice per milestone | `ask_holo` + `unproven` | `an_unproven_answer_is_challenged_twice` |
| A dead target repeated twice is pointed out, even when Holo rewords it | `observe_outcome` + `same_target` | `a_reworded_dead_click_still_counts_as_a_repeat` |
| History is bounded: 3 screenshots, ≤ 6 turns verbatim, ~12k tokens (est.), searches ≤ 4,000 chars | `trim_images`, `compact`, `MAX_SEARCH_CHARS` | `long_milestones_keep_a_bounded_history`, `a_huge_search_result_folds_turns_early`, `long_search_results_are_cut` |
| The knowledge base is asked once per milestone; nothing relevant adds nothing | `ensure_knowledge`, `platform::relevant` | `each_milestone_gets_its_knowledge_once`, `nothing_relevant_adds_nothing`, `keeps_only_real_matches` |
| Saved tutorials keep only the path that worked | `Session::worked`, `to_tutorial` | `saved_tutorial_keeps_only_the_path_that_worked` |
| Stop drops the in-flight step at once; nothing is shown after it | `cancel::Generation` | `stop_interrupts_a_slow_step`, `stopped_before_start_never_runs` |
| A streamed answer is complete or an error (UTF-8 intact, `[DONE]` ends it) | `holo::Sse` | `sse_keeps_a_character_split_across_chunks`, `sse_stops_on_done_marker`, `sse_cut_before_the_end_is_an_error` |
| A click while nothing is pointed at is not a "miss" | `watch::describe_event` | `a_click_on_a_shortcut_step_is_not_a_miss` |

## Rules of the house

- Holo picks, the learner performs; Rio never clicks for the learner.
- Model output is never trusted raw: parse into typed structs, validate, then act.
- Durations and thresholds not measured carry `(est.)`; measured ones say how.
- No key in git, logs or prompts. Screenshots stay local (`sessions/` is ignored).
- Product text shown to the learner follows the learner's language; the UI chrome is English.
