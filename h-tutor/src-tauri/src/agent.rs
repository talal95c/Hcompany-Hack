//! The tutorial harness.
//!
//! A tutorial is a graph of milestones (see `tutorial.rs`). Each milestone is
//! run as its own Holo task, in the format Holo is trained on (H docs, "Build
//! an agent"): a fresh conversation, an imperative `Task:`, each screenshot as
//! an `<observation>`, only the last 3 screenshots kept, native tool calls
//! with `tool_choice: required`, thinking on, and `answer` when the task is
//! done. Fresh conversations keep the context short on long tutorials.
//!
//! Durable state is re-injected every turn as a `<progress>` block before the
//! observation: the overall goal, finished milestones and the current
//! milestone with its success criterion and hints.
//!
//! The twist: Holo picks each action, but the learner performs it. The action
//! is shown as the ghost pointer; what the learner did goes back to Holo as the
//! tool result, followed by the next screenshot.

use crate::capture::{SCREEN_CHANGED, Shot, capture_primary, thumb_diff};
use crate::holo::{self, Holo};
use crate::journal;
use crate::tutorial::{Milestone, Next, Status, Tutorial};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{HashMap, HashSet};

const MAX_IMAGES: usize = 3;
/// Observation turns kept verbatim in a milestone's conversation; older ones
/// are folded into a one-line summary so text context stays bounded too.
const MAX_TURNS: usize = 6;
/// Model requests per Holo turn before giving up on getting a valid action.
const MAX_ATTEMPTS: usize = 3;
/// Documentation searches per Holo turn.
const MAX_SEARCHES: usize = 2;
/// A step that took longer than this to compute is checked against a fresh
/// screen before it is shown (est.).
const STALE_AFTER: std::time::Duration = std::time::Duration::from_secs(4);
/// Estimated prompt size a milestone's conversation is folded down to
/// (est.: an observation costs ~1,600 image tokens at 1600 px, measured on
/// one request; text is counted at ~4 characters per token).
const CONTEXT_BUDGET: usize = 12_000;
const IMAGE_TOKENS: usize = 1_600;
/// A search result longer than this is cut before entering the conversation
/// (~1,000 tokens), so one result can never eat the whole budget.
const MAX_SEARCH_CHARS: usize = 4_000;
/// Observation turns always kept verbatim, whatever the budget.
const MIN_TURNS: usize = 2;
/// Milestones shown in full on each side of the current one in `<progress>`;
/// the rest of a long tutorial is counted, not listed.
const WINDOW: usize = 3;
/// Learner entries carried to later milestones' `<progress>`.
const MAX_FACTS: usize = 8;
/// Longest accepted `answer` evidence: past this it is explaining, not proving.
const MAX_EVIDENCE: usize = 240;

pub fn language_name(code: &str) -> Option<&'static str> {
    Some(match code {
        "en" => "English",
        "fr" => "French",
        "de" => "German",
        "es" => "Spanish",
        "pt" => "Portuguese",
        _ => return None,
    })
}

const SYSTEM: &str = "You are Holo, a hands-on software tutor. You complete computer tasks by choosing GUI actions, \
but a human learner performs each action for you: your action is shown to them as a highlighted pointer, they do it, \
and you then receive the next screenshot. The learner learns by doing, so you never explain the procedure in text: you \
lead them through it, one action at a time, until the task is really done on screen.
Each observation comes with a <progress> block: the tutorial's overall goal, what is already done, and your current \
task with its success criterion and known path. The known path may be outdated: trust the screen. The success \
criterion describes the intended state: judge it against the actual screen, which may differ from a fresh app \
(leftovers from earlier work, extra objects, other settings) and handle those differences within the current task.
Rules:
- Exactly one action per step.
- Fill `instruction` with one short, friendly sentence addressed to the learner (max 20 words): what to do and why. \
It is read aloud. Write it in the learner language given in <progress>, using informal \"tu\" in French. \
Never infer the learner's language from the language of the application or the operating system on screen. \
Element descriptions stay in English.
- Teach through the application's graphical interface; avoid terminal commands unless the task requires them.
- If you are unsure where something is in this application or version, or the known path did not work, call \
search(app_name, query) first: it returns up-to-date documentation, and the learner does nothing meanwhile.
- Only act on elements you can actually see in the latest observation. If the app is not open or the element is \
hidden, guide the learner step by step to reveal it.
- When the learner has to make a choice (a name, a file, an item in a list), point at a sensible default and say they can pick another one.
- If the previous action did not have the expected effect, notice it and help the learner recover.
- Call answer as soon as the latest screenshot meets the current task's success criterion, even if that happened \
before you acted. Only work on the current task, not the later ones.";

fn tool(name: &str, desc: &str, mut props: Value, mut required: Vec<&str>) -> Value {
    props["instruction"] = json!({
        "type": "string",
        "description": "One short friendly sentence in the learner's language telling them what to do and why (max 20 words), read aloud"
    });
    required.push("instruction");
    json!({ "type": "function", "function": {
        "name": name, "description": desc,
        "parameters": { "type": "object", "properties": props, "required": required }
    }})
}

fn tools(with_search: bool) -> Value {
    let el = json!({ "type": "string", "description": "Detailed description of the target UI element" });
    let x = json!({ "type": "integer", "minimum": 0, "maximum": 1000, "description": "X coordinate as integer in [0, 1000]" });
    let y = json!({ "type": "integer", "minimum": 0, "maximum": 1000, "description": "Y coordinate as integer in [0, 1000]" });
    let mut list = json!([
        tool("click", "Click at (x, y) coordinates",
            json!({ "element": el, "x": x, "y": y }), vec!["element", "x", "y"]),
        tool("write", "Type text into the element at (x, y)",
            json!({ "element": el, "x": x, "y": y, "content": { "type": "string", "description": "Text to type" } }),
            vec!["element", "x", "y", "content"]),
        tool("scroll", "Scroll at (x, y)",
            json!({ "x": x, "y": y, "direction": { "type": "string", "enum": ["up", "down", "left", "right"] } }),
            vec!["x", "y", "direction"]),
        tool("press_key", "Press a keyboard key or shortcut",
            json!({ "keys": { "type": "string", "description": "e.g. cmd+n, enter" } }), vec!["keys"]),
        { "type": "function", "function": {
            "name": "answer",
            "description": "Call when the latest screenshot shows the current task's success criterion is met.",
            "parameters": { "type": "object",
                "properties": { "content": { "type": "string",
                    "description": "What on the screenshot proves the task is done (one short English sentence)" } },
                "required": ["content"] }
        }}
    ]);
    // Once the search budget is spent, search is no longer offered at all.
    if with_search {
        list.as_array_mut().expect("tools").push(crate::search::tool());
    }
    list
}

#[derive(Serialize, Clone, Default, Debug)]
pub struct MilestoneView {
    pub id: String,
    pub goal: String,
    pub status: String,
    pub optional: bool,
    /// The source video at the moment that shows this milestone (YouTube imports).
    pub video_url: Option<String>,
}

/// What the learner should do now, as shown in the bar.
#[derive(Serialize, Clone, Default, Debug)]
pub struct Step {
    /// click | write | scroll | press_key | done, or pending while a new
    /// milestone's first action is not known yet
    pub kind: String,
    pub instruction: String,
    pub element: String,
    /// Normalized (0..1000) point, when the action has one.
    pub point: Option<(f64, f64)>,
    pub text: String,
    pub keys: String,
    /// True when the screen had not changed and no new step was computed.
    pub unchanged: bool,
    /// Current milestone and the whole graph's state.
    pub milestone: Option<MilestoneView>,
    pub progress: Vec<MilestoneView>,
    /// Milestones closed while computing this step (for a "✓" toast).
    pub completed: Vec<String>,
    pub teach: Option<String>,
}

/// What became of an action given to the learner, judged on the next
/// screenshot.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Outcome {
    /// Shown, not yet observed.
    Proposed,
    /// The screen changed after it.
    Changed,
    /// Nothing visibly changed after it.
    NoEffect,
    /// Too small to judge on a whole-screen thumbnail (typing in a field).
    Unknown,
    /// Never shown: the screen changed while it was being computed.
    Superseded,
}

#[derive(Clone, Debug)]
pub struct ActionRecord {
    /// "click Add menu in the top bar", "type \"Donut\" in Name field"
    pub path: String,
    pub outcome: Outcome,
    /// Text the learner was asked to type, if any.
    pub typed: Option<String>,
}

pub struct Session {
    pub tutorial: Tutorial,
    lang: Option<String>,
    status: HashMap<String, Status>,
    current: Option<String>,
    /// Conversation for the current milestone only.
    messages: Vec<Value>,
    pending_call: Option<String>,
    /// Actions given per milestone with what they did, used to turn this
    /// run into a tutorial with a verified known path.
    pub actions: HashMap<String, Vec<ActionRecord>>,
    /// The milestone closed last, whose path is recalled in `<progress>`.
    last_done: Option<String>,
    /// Durable learner choices ("typed \"MyDonut\" in Name field"), kept
    /// across milestones' fresh conversations.
    facts: Vec<String>,
    pub evidence: HashMap<String, String>,
    pub step: Step,
    /// Screen when the current step was given (for "did anything change?").
    pub before: Option<Shot>,
    pub finished: bool,
    /// Required milestones that can no longer start (the graph is stuck).
    pub blocked: Option<Vec<String>>,
    /// Milestones closed since the last step was shown: kept across a failed
    /// request so the learner still gets their "✓".
    completed: Vec<String>,
}

impl Session {
    pub fn new(tutorial: Tutorial, lang: Option<&str>) -> Self {
        let status = tutorial.milestones.iter().map(|m| (m.id.clone(), Status::Todo)).collect();
        journal::begin(&tutorial, lang);
        crate::platform::event("tutorial_started", &tutorial, None);
        let mut s = Self {
            tutorial,
            lang: lang.map(String::from),
            status,
            current: None,
            messages: Vec::new(),
            pending_call: None,
            actions: HashMap::new(),
            facts: Vec::new(),
            last_done: None,
            evidence: HashMap::new(),
            step: Step::default(),
            before: None,
            finished: false,
            blocked: None,
            completed: Vec::new(),
        };
        s.start_next_milestone();
        s
    }

    fn finished_set(&self) -> HashSet<String> {
        self.status
            .iter()
            .filter(|(_, s)| matches!(s, Status::Done | Status::Skipped))
            .map(|(id, _)| id.clone())
            .collect()
    }

    fn current_milestone(&self) -> Option<&Milestone> {
        self.current.as_deref().and_then(|id| self.tutorial.milestone(id))
    }

    /// Moves to the next available milestone and opens a fresh conversation
    /// for it, or marks the tutorial finished or blocked. Either way the
    /// previous step is dropped: its pointer belongs to a closed milestone and
    /// must never be shown again.
    fn start_next_milestone(&mut self) {
        self.current = None;
        self.pending_call = None;
        self.before = None;
        let m = match self.tutorial.next(&self.finished_set()) {
            Next::Ready(m) => m.clone(),
            Next::Complete => {
                self.finished = true;
                self.step = Step { kind: "pending".into(), progress: self.progress(), ..Default::default() };
                return;
            }
            Next::Blocked(ids) => {
                journal::event("tutorial_blocked", json!({ "milestones": ids }));
                self.blocked = Some(ids);
                self.step = Step { kind: "pending".into(), progress: self.progress(), ..Default::default() };
                return;
            }
        };
        self.status.insert(m.id.clone(), Status::Current);
        self.current = Some(m.id.clone());
        self.step = Step {
            kind: "pending".into(),
            milestone: Some(view(&self.tutorial, &m, "current")),
            progress: self.progress(),
            ..Default::default()
        };

        let hints = if m.hints.is_empty() {
            String::new()
        } else {
            format!("\nKnown path (may be outdated, trust the screen): {}", m.hints.join("; "))
        };
        self.messages = vec![
            json!({ "role": "system", "content": SYSTEM }),
            json!({ "role": "user", "content": format!(
                "Task: Guide the learner until this is actually done on their screen: \"{}\"\n\
                 Success criterion: {}{hints}\n\
                 This is one milestone of the tutorial \"{}\" (overall goal: {}).",
                m.goal, m.done_when, self.tutorial.title, self.tutorial.goal
            ) }),
        ];
        journal::event("milestone_start", json!({ "milestone": m.id, "goal": m.goal }));
    }

    fn close_current(&mut self, status: Status, evidence: &str) -> Option<String> {
        let id = self.current.take()?;
        if status == Status::Done {
            self.last_done = Some(id.clone());
            let typed = self.actions.get(&id).into_iter().flatten().filter(|a| a.typed.is_some());
            let new: Vec<String> = typed.filter(|a| a.outcome != Outcome::Superseded).map(|a| a.path.clone()).collect();
            self.facts.extend(new);
            let excess = self.facts.len().saturating_sub(MAX_FACTS);
            self.facts.drain(..excess);
        }
        self.status.insert(id.clone(), status);
        self.evidence.insert(id.clone(), evidence.to_string());
        let kind = if status == Status::Skipped { "milestone_skipped" } else { "milestone_done" };
        journal::event(kind, json!({ "milestone": id, "evidence": evidence }));
        let goal = self.tutorial.milestone(&id).map(|m| m.goal.clone());
        crate::platform::event(kind, &self.tutorial, goal.as_deref());
        Some(id)
    }

    /// Skips the current milestone (the learner asked to move on).
    pub fn skip_milestone(&mut self) {
        self.close_current(Status::Skipped, "skipped by the learner");
        self.start_next_milestone();
    }

    /// The `<progress>` block re-injected with every observation.
    /// The learner's language changed (they spoke or typed in another one).
    pub fn set_lang(&mut self, lang: Option<&str>) {
        if let Some(l) = lang.filter(|l| language_name(l).is_some())
            && self.lang.as_deref() != Some(l)
        {
            journal::event("language", json!({ "from": self.lang, "to": l }));
            self.lang = Some(l.to_string());
        }
    }

    fn progress_block(&self) -> String {
        let lang = self.lang.as_deref().and_then(language_name).unwrap_or("English");
        let tu = if lang == "French" { ", using \"tu\"" } else { "" };
        let mut out = format!(
            "<progress>\nLearner language: {lang}. Write every instruction in {lang}{tu}.\nTutorial goal: {}\n",
            self.tutorial.goal
        );
        // A window that moves with the current milestone: neighbours in
        // full, the rest of a long tutorial as counts.
        let all = &self.tutorial.milestones;
        let at = self.current.as_deref().and_then(|id| all.iter().position(|m| m.id == id));
        let shown = |i: usize| at.is_none_or(|c| i.abs_diff(c) <= WINDOW);
        let before = at.map_or(0, |c| c.saturating_sub(WINDOW));
        if before > 0 {
            let done = all[..before].iter().filter(|m| self.status.get(&m.id) == Some(&Status::Done)).count();
            out += &format!("… {before} earlier milestones ({done} done)\n");
        }
        for (i, m) in all.iter().enumerate() {
            let pinned = self.status.get(&m.id) == Some(&Status::Current) || self.last_done.as_ref() == Some(&m.id);
            if !shown(i) && !pinned {
                continue;
            }
            let (mark, extra) = match self.status.get(&m.id) {
                Some(Status::Done) => {
                    let seen = self.evidence.get(&m.id).filter(|e| !e.is_empty()).map(|e| format!(" (seen: {e})"));
                    let how = (self.last_done.as_deref() == Some(m.id.as_str()))
                        .then(|| self.worked(&m.id))
                        .filter(|p| !p.is_empty())
                        .map(|p| format!("\n  done via: {}", p.join("; ")));
                    ("✓", format!("{}{}", seen.unwrap_or_default(), how.unwrap_or_default()))
                }
                Some(Status::Skipped) => ("–", " (skipped)".to_string()),
                Some(Status::Current) => (
                    "→",
                    format!(
                        " (current; done when: {}){}",
                        m.done_when,
                        if m.hints.is_empty() {
                            String::new()
                        } else {
                            format!("\n  known path: {}", m.hints.join("; "))
                        }
                    ),
                ),
                _ => ("·", if m.optional { " (optional)".to_string() } else { String::new() }),
            };
            out += &format!("{mark} {}{extra}\n", m.goal);
        }
        let after = at.map_or(0, |c| all.len().saturating_sub(c + WINDOW + 1));
        if after > 0 {
            out += &format!("… {after} more milestones after these\n");
        }
        if !self.facts.is_empty() {
            out += &format!("Learner entries so far (reuse them): {}\n", self.facts.join("; "));
        }
        out + "</progress>\n"
    }

    pub fn progress(&self) -> Vec<MilestoneView> {
        self.tutorial
            .milestones
            .iter()
            .map(|m| MilestoneView {
                id: m.id.clone(),
                goal: m.goal.clone(),
                status: match self.status.get(&m.id) {
                    Some(Status::Done) => "done",
                    Some(Status::Skipped) => "skipped",
                    Some(Status::Current) => "current",
                    _ => "todo",
                }
                .into(),
                optional: m.optional,
                video_url: video_link(&self.tutorial, m),
            })
            .collect()
    }

    /// The actions that worked for a milestone: left out are actions never
    /// shown, not yet observed, or without visible effect and followed by
    /// another try (the last one before the milestone closed stays, even a
    /// shortcut with no visible effect).
    fn worked(&self, id: &str) -> Vec<String> {
        let records = self.actions.get(id).map(Vec::as_slice).unwrap_or_default();
        records
            .iter()
            .enumerate()
            .filter(|(i, a)| match a.outcome {
                Outcome::Changed | Outcome::Unknown => true,
                Outcome::NoEffect => *i + 1 == records.len(),
                Outcome::Proposed | Outcome::Superseded => false,
            })
            .map(|(_, a)| a.path.clone())
            .collect()
    }

    /// Judges the last action of the current milestone on the new screen.
    /// Returns a note for Holo when the same action has now failed twice.
    fn observe_outcome(&mut self, shot: &Shot) -> Option<String> {
        let before = self.before.as_ref()?;
        let changed = thumb_diff(&before.thumb, &shot.thumb) > SCREEN_CHANGED;
        let records = self.actions.get_mut(self.current.as_deref()?)?;
        let last = records.last_mut().filter(|a| a.outcome == Outcome::Proposed)?;
        last.outcome = match (changed, last.typed.is_some()) {
            (true, _) => Outcome::Changed,
            (false, true) => Outcome::Unknown,
            (false, false) => Outcome::NoEffect,
        };
        journal::event(
            "action_outcome",
            json!({ "milestone": self.current, "path": last.path, "outcome": format!("{:?}", last.outcome) }),
        );
        let path = last.path.clone();
        let repeats = records.iter().rev().take_while(|a| a.path == path && a.outcome == Outcome::NoEffect).count();
        (repeats >= 2).then(|| {
            format!(
                "Note: \"{path}\" was given {repeats} times in a row without visible effect. Do not repeat it as is: \
                 check the screen, try another way (another element, the menu, a search), or help the learner recover."
            )
        })
    }

    /// The last action was computed on a screen that changed meanwhile and
    /// was never shown.
    fn supersede_last(&mut self) {
        if let Some(a) = self.current.as_deref().and_then(|id| self.actions.get_mut(id)).and_then(|r| r.last_mut()) {
            a.outcome = Outcome::Superseded;
        }
    }

    /// Replaces all but the last `MAX_IMAGES` screenshots with a placeholder,
    /// keeping their `<observation>` wrappers.
    fn trim_images(&mut self) {
        let mut seen = 0;
        for msg in self.messages.iter_mut().rev() {
            let Some(parts) = msg["content"].as_array_mut() else { continue };
            for part in parts.iter_mut().rev() {
                if part["type"] == "image_url" {
                    seen += 1;
                    if seen > MAX_IMAGES {
                        *part = json!({ "type": "text", "text": "[screenshot evicted]" });
                    }
                }
            }
        }
    }

    /// Plain-text summary of the tutorial so far, for side questions.
    pub fn context(&self) -> String {
        let mut out = format!("Tutorial: \"{}\" (goal: {})\n", self.tutorial.title, self.tutorial.goal);
        for v in self.progress() {
            out += &format!("- [{}] {}\n", v.status, v.goal);
        }
        if !self.step.instruction.is_empty() {
            out += &format!("Current instruction: {}\n", self.step.instruction);
        }
        out
    }
}

fn video_link(t: &Tutorial, m: &Milestone) -> Option<String> {
    let url = t.source_url.as_deref()?;
    let at = m.video_at?;
    let sep = if url.contains('?') { '&' } else { '?' };
    Some(format!("{url}{sep}t={at}s"))
}

fn view(t: &Tutorial, m: &Milestone, status: &str) -> MilestoneView {
    MilestoneView {
        id: m.id.clone(),
        goal: m.goal.clone(),
        status: status.into(),
        optional: m.optional,
        video_url: video_link(t, m),
    }
}

/// What the harness needs from the model: one chat completion, and a
/// documentation search. Implemented by `Holo`, and by a scripted fake in tests.
pub trait Brain: Sync {
    /// Returns the assistant message, the request's duration in ms, and usage.
    fn chat(&self, body: &Value) -> impl std::future::Future<Output = Result<(Value, u128, Value), String>> + Send;
    fn search(&self, app_name: &str, query: &str) -> impl std::future::Future<Output = String> + Send;
}

impl Brain for Holo {
    async fn chat(&self, body: &Value) -> Result<(Value, u128, Value), String> {
        // Streamed: the bar shows Holo's reasoning while it decides.
        self.chat_stream(body, &crate::emit_thinking).await
    }
    async fn search(&self, app_name: &str, query: &str) -> String {
        crate::emit_status(&format!("Searching {app_name} docs: {query}"));
        crate::search::run(self, app_name, query).await.text
    }
}

/// Advances the session: reports what the learner did (`event`), sends the
/// new screenshot, and asks Holo for the next action. Milestones Holo
/// declares done are closed and the next one starts on the same screenshot,
/// until Holo gives an action, the tutorial is really complete, or the graph
/// is blocked. Each closure finishes one milestone, so the chain is bounded
/// by the tutorial's size.
pub async fn advance(
    brain: &impl Brain,
    session: &mut Session,
    event: Option<String>,
    only_if_changed: bool,
) -> Result<Step, String> {
    let capture = || async { tauri::async_runtime::spawn_blocking(capture_primary).await.map_err(|e| e.to_string())? };
    advance_with(brain, session, event, only_if_changed, STALE_AFTER, capture).await
}

/// `advance` with an injected screen capture. A step that took longer than
/// `stale_after` is checked against a fresh screen: if the screen changed
/// meanwhile (a dialog closed, a page loaded), the step is recomputed once
/// on the new screen instead of pointing at a stale position.
async fn advance_with<F, Fut>(
    brain: &impl Brain,
    session: &mut Session,
    event: Option<String>,
    only_if_changed: bool,
    stale_after: std::time::Duration,
    capture: F,
) -> Result<Step, String>
where
    F: Fn() -> Fut,
    Fut: std::future::Future<Output = Result<Shot, String>>,
{
    if session.finished {
        return Ok(session.step.clone());
    }
    let started = std::time::Instant::now();
    let step = advance_on(brain, session, event, capture().await?, only_if_changed).await?;
    if step.point.is_none() || step.unchanged || started.elapsed() < stale_after {
        return Ok(step);
    }
    let fresh = capture().await?;
    let moved = session.before.as_ref().map_or(0.0, |b| thumb_diff(&b.thumb, &fresh.thumb));
    if moved <= SCREEN_CHANGED {
        return Ok(step);
    }
    journal::event(
        "stale_step",
        json!({ "milestone": session.current, "diff": moved, "ms": started.elapsed().as_millis() }),
    );
    session.supersede_last();
    // The new step is judged against the screen it was computed on.
    session.before = None;
    session.completed = step.completed;
    let note = "Not shown to the learner: the screen changed while you were deciding. Look at the new screenshot \
                and give the next action from it.";
    advance_on(brain, session, Some(note.into()), fresh, false).await
}

/// `advance` on a given screenshot.
async fn advance_on(
    brain: &impl Brain,
    session: &mut Session,
    event: Option<String>,
    shot: Shot,
    only_if_changed: bool,
) -> Result<Step, String> {
    if session.finished {
        return Ok(session.step.clone());
    }

    if only_if_changed
        && session.step.kind != "pending"
        && let Some(before) = &session.before
        && thumb_diff(&before.thumb, &shot.thumb) < 0.6
    {
        return Ok(Step { unchanged: true, ..session.step.clone() });
    }
    if let Some(ev) = &event {
        journal::event("learner", json!({ "milestone": session.current, "event": ev }));
    }
    let shot_path = journal::shot(&shot.data_uri);

    let mut event = event;
    if let Some(note) = session.observe_outcome(&shot) {
        event = Some(match event {
            Some(ev) => format!("{ev}\n{note}"),
            None => note,
        });
    }
    while !session.finished {
        if let Some(ids) = &session.blocked {
            return Err(format!(
                "Le tutoriel est bloqué : aucune étape restante ne peut démarrer ({}).",
                ids.join(", ")
            ));
        }
        if session.current.is_none() {
            return Err("Aucune étape en cours".into());
        }
        match ask_holo(brain, session, event.take(), &shot, shot_path.as_deref()).await? {
            Turn::Action(step) => {
                let mut step = *step;
                step.completed = std::mem::take(&mut session.completed);
                session.step = step.clone();
                session.before = Some(shot);
                return Ok(step);
            }
            Turn::MilestoneDone(id) => {
                session.completed.push(id);
                session.start_next_milestone();
            }
        }
    }

    // Tutorial complete: every required milestone is done or skipped.
    journal::event("tutorial_done", json!({}));
    if let Some(run) = journal::skill_run()
        && let Err(error) = crate::skills::record_run(to_tutorial(session), run)
    {
        eprintln!("Impossible d'enregistrer le skill : {error}");
    }
    journal::end("completed");
    crate::platform::event("tutorial_finished", &session.tutorial, None);
    let step = Step {
        kind: "done".into(),
        instruction: String::new(),
        completed: std::mem::take(&mut session.completed),
        progress: session.progress(),
        ..Default::default()
    };
    session.step = step.clone();
    session.before = Some(shot);
    Ok(step)
}

enum Turn {
    Action(Box<Step>),
    MilestoneDone(String),
}

/// A tool call that passed validation. Only this can reach the learner or
/// change a milestone's status.
#[derive(Debug, Clone, PartialEq)]
enum Action {
    Click { element: String, x: f64, y: f64, instruction: String },
    Write { element: String, x: f64, y: f64, content: String, instruction: String },
    Scroll { x: f64, y: f64, direction: String, instruction: String },
    PressKey { keys: String, instruction: String },
    Search { app_name: Option<String>, query: String },
    Answer { evidence: String },
}

#[derive(Deserialize)]
struct ClickArgs {
    element: String,
    x: f64,
    y: f64,
    #[serde(default)]
    instruction: String,
}
#[derive(Deserialize)]
struct WriteArgs {
    element: String,
    x: f64,
    y: f64,
    content: String,
    #[serde(default)]
    instruction: String,
}
#[derive(Deserialize)]
struct ScrollArgs {
    x: f64,
    y: f64,
    direction: String,
    #[serde(default)]
    instruction: String,
}
#[derive(Deserialize)]
struct KeyArgs {
    keys: String,
    #[serde(default)]
    instruction: String,
}
#[derive(Deserialize)]
struct SearchArgs {
    #[serde(default)]
    app_name: Option<String>,
    query: String,
}
#[derive(Deserialize)]
struct AnswerArgs {
    content: String,
}

/// Why a model response was not accepted, and what to tell Holo.
#[derive(Debug)]
struct Invalid {
    reason: String,
    /// Corrective message for the retry; None to simply ask again.
    feedback: Option<String>,
    /// The offending call, when it is well-formed enough to be echoed back
    /// with the feedback as its tool result.
    call: Option<Value>,
}

impl Invalid {
    fn retry(reason: &str) -> Self {
        Self { reason: reason.into(), feedback: None, call: None }
    }
    fn tell(reason: &str, feedback: &str, call: Option<&Value>) -> Self {
        Self { reason: reason.into(), feedback: Some(feedback.into()), call: call.cloned() }
    }

    /// Adds the corrective feedback to the retry's messages.
    fn append_to(&self, messages: &mut Vec<Value>) {
        let Some(feedback) = &self.feedback else { return };
        match &self.call {
            Some(call) => {
                messages.push(json!({ "role": "assistant", "content": "", "tool_calls": [call] }));
                messages.push(json!({ "role": "tool", "tool_call_id": call["id"], "content": feedback }));
            }
            None => messages.push(json!({ "role": "user", "content": feedback })),
        }
    }
}

fn nonempty(v: String, what: &str, call: &Value) -> Result<String, Invalid> {
    let v = v.trim().to_string();
    if v.is_empty() {
        let msg = format!("Invalid action: `{what}` must not be empty. Call the tool again with every required field.");
        return Err(Invalid::tell(&format!("empty {what}"), &msg, Some(call)));
    }
    Ok(v)
}

fn point(x: f64, y: f64, call: &Value) -> Result<(f64, f64), Invalid> {
    let ok = |v: f64| v.is_finite() && (0.0..=1000.0).contains(&v);
    if ok(x) && ok(y) {
        Ok((x, y))
    } else {
        Err(Invalid::tell(
            "coordinates out of range",
            &format!("Invalid action: ({x}, {y}) is outside the screen. x and y are integers in [0, 1000]."),
            Some(call),
        ))
    }
}

/// Checks a model response before anything acts on it: complete response,
/// exactly one supported tool call with an id, arguments that parse into the
/// tool's type, required fields present, coordinates on screen, and short
/// non-empty evidence for `answer`.
fn validate(msg: &Value, with_search: bool) -> Result<(Value, Action), Invalid> {
    if msg["finish_reason"] == "length" {
        return Err(Invalid::retry("response cut off (length)"));
    }
    let calls = msg["tool_calls"].as_array().map(Vec::as_slice).unwrap_or_default();
    let call = match calls {
        [] => return Err(Invalid::retry("no tool call")),
        [call] => call,
        _ => {
            return Err(Invalid::tell("several tool calls", "Exactly one action per step: call a single tool.", None));
        }
    };
    if call["id"].as_str().is_none_or(str::is_empty) {
        return Err(Invalid::retry("tool call without id"));
    }
    let name = call["function"]["name"].as_str().unwrap_or("");
    let raw = call["function"]["arguments"].as_str().unwrap_or("");
    let Ok(args) = serde_json::from_str::<Value>(raw).map(|a| a.is_object().then_some(a)) else {
        return Err(Invalid::tell(
            "arguments are not valid JSON",
            "Your last tool call had incomplete or invalid JSON arguments. Call the tool again.",
            None,
        ));
    };
    let Some(args) = args else {
        return Err(Invalid::tell("arguments are not an object", "Tool arguments must be a JSON object.", None));
    };
    fn typed<T: serde::de::DeserializeOwned>(args: Value, name: &str, call: &Value) -> Result<T, Invalid> {
        serde_json::from_value(args).map_err(|e| {
            Invalid::tell(
                &format!("bad {name} arguments: {e}"),
                &format!("Invalid arguments for {name}: {e}."),
                Some(call),
            )
        })
    }
    let action = match name {
        "click" => {
            let a: ClickArgs = typed(args, name, call)?;
            let (x, y) = point(a.x, a.y, call)?;
            Action::Click { element: nonempty(a.element, "element", call)?, x, y, instruction: a.instruction }
        }
        "write" => {
            let a: WriteArgs = typed(args, name, call)?;
            let (x, y) = point(a.x, a.y, call)?;
            Action::Write {
                element: nonempty(a.element, "element", call)?,
                x,
                y,
                content: nonempty(a.content, "content", call)?,
                instruction: a.instruction,
            }
        }
        "scroll" => {
            let a: ScrollArgs = typed(args, name, call)?;
            let (x, y) = point(a.x, a.y, call)?;
            if !["up", "down", "left", "right"].contains(&a.direction.as_str()) {
                return Err(Invalid::tell(
                    "bad scroll direction",
                    "Invalid scroll: direction is one of up, down, left, right.",
                    Some(call),
                ));
            }
            Action::Scroll { x, y, direction: a.direction, instruction: a.instruction }
        }
        "press_key" => {
            let a: KeyArgs = typed(args, name, call)?;
            Action::PressKey { keys: nonempty(a.keys, "keys", call)?, instruction: a.instruction }
        }
        "search" if with_search => {
            let a: SearchArgs = typed(args, name, call)?;
            Action::Search {
                app_name: a.app_name.filter(|n| !n.trim().is_empty()),
                query: nonempty(a.query, "query", call)?,
            }
        }
        "answer" => {
            let a: AnswerArgs = typed(args, name, call)?;
            let evidence = nonempty(a.content, "content", call)?;
            if evidence.len() > MAX_EVIDENCE || evidence.contains('\n') {
                return Err(Invalid::tell(
                    "answer explains instead of proving",
                    "Refused: do not explain the procedure. If the success criterion is met on the screenshot, \
                     call answer with one short sentence of evidence; otherwise give the single next action.",
                    Some(call),
                ));
            }
            Action::Answer { evidence }
        }
        _ => {
            return Err(Invalid::tell(
                &format!("unknown tool {name:?}"),
                &format!("`{name}` is not available. Use one of the offered tools."),
                None,
            ));
        }
    };
    Ok((call.clone(), action))
}

/// Requests, time and tokens of one Holo turn, searches included.
#[derive(Default)]
struct Metrics {
    requests: u32,
    invalid: u32,
    searches: u32,
    model_ms: u128,
    search_ms: u128,
    prompt: u64,
    cached: u64,
    reasoning: u64,
    completion: u64,
}

impl Metrics {
    fn add(&mut self, ms: u128, usage: &Value) {
        self.requests += 1;
        self.model_ms += ms;
        let n = |v: &Value| v.as_u64().unwrap_or(0);
        self.prompt += n(&usage["prompt_tokens"]);
        self.cached += n(&usage["prompt_tokens_details"]["cached_tokens"]);
        self.reasoning += n(&usage["completion_tokens_details"]["reasoning_tokens"]);
        self.completion += n(&usage["completion_tokens"]);
    }
}

/// One Holo turn on the current milestone's conversation.
async fn ask_holo(
    brain: &impl Brain,
    session: &mut Session,
    event: Option<String>,
    shot: &Shot,
    shot_path: Option<&str>,
) -> Result<Turn, String> {
    let started = std::time::Instant::now();
    // A pending call always gets its tool result, or the conversation would
    // be malformed for the API.
    if let Some(id) = session.pending_call.take() {
        let content = event.unwrap_or_else(|| "No report from the learner.".into());
        session.messages.push(json!({ "role": "tool", "tool_call_id": id, "content": content }));
    }
    compact(&mut session.messages, CONTEXT_BUDGET);
    session.messages.push(json!({ "role": "user", "content": [
        { "type": "text", "text": session.progress_block() },
        { "type": "text", "text": "<observation>\n" },
        { "type": "image_url", "image_url": { "url": shot.data_uri } },
        { "type": "text", "text": "\n</observation>" }
    ]}));
    session.trim_images();

    let model = holo::smart_model();
    let mut metrics = Metrics::default();
    // Searches run inside the step: Holo asks, we fetch, Holo continues on
    // the same screenshot, until it picks an action for the learner. Search
    // is withdrawn once its budget is spent, so this loop ends.
    let (call, action, msg) = loop {
        let with_search = (metrics.searches as usize) < MAX_SEARCHES;
        let mut body = json!({
            "model": model,
            "messages": session.messages,
            "tools": tools(with_search),
            "tool_choice": "required",
            "temperature": 0.8,
            "reasoning_effort": std::env::var("HOLO_REASONING").unwrap_or_else(|_| "low".into()),
            // A runaway reasoning trace must not stall the step: a cut answer
            // is rejected below and asked again.
            "max_tokens": 3072,
        });

        // Only a validated response is accepted; when attempts run out, no
        // refused candidate can slip through.
        let mut accepted = None;
        for _ in 0..MAX_ATTEMPTS {
            let (m, t, u) = brain.chat(&body).await?;
            metrics.add(t, &u);
            match validate(&m, with_search) {
                Ok((call, action)) => {
                    accepted = Some((call, action, m));
                    break;
                }
                Err(invalid) => {
                    metrics.invalid += 1;
                    crate::emit_status("Holo's answer was incomplete, asking again…");
                    journal::event(
                        "invalid_action",
                        json!({ "milestone": session.current, "reason": invalid.reason,
                                "finish_reason": m["finish_reason"], "tool_calls": m["tool_calls"] }),
                    );
                    invalid.append_to(body["messages"].as_array_mut().expect("messages"));
                }
            }
        }
        let (call, action, msg) = accepted.ok_or("Holo n'a pas proposé d'action valide : réessaie pour continuer.")?;

        // Keep only the parsed action in history, never the reasoning.
        let assistant = json!({
            "role": "assistant",
            "content": msg["content"].as_str().unwrap_or(""),
            "tool_calls": [call.clone()],
        });
        if let Action::Search { app_name, query } = &action {
            metrics.searches += 1;
            let app_name = app_name.clone().unwrap_or_else(|| session.tutorial.app.name.clone());
            let t = std::time::Instant::now();
            let mut result = brain.search(&app_name, query).await;
            if result.len() > MAX_SEARCH_CHARS {
                let end = result.floor_char_boundary(MAX_SEARCH_CHARS);
                result.truncate(end);
                result += "\n[result truncated]";
            }
            metrics.search_ms += t.elapsed().as_millis();
            // Call and result go in together: a step cancelled during the
            // search leaves no unanswered call behind.
            session.messages.push(assistant);
            session.messages.push(json!({ "role": "tool", "tool_call_id": call["id"], "content": result }));
            continue;
        }
        session.messages.push(assistant);
        break (call, action, msg);
    };
    session.pending_call = call["id"].as_str().map(String::from);

    let reasoning = msg["reasoning"].as_str().or(msg["reasoning_content"].as_str()).unwrap_or("");
    let milestone_id = session.current.clone().unwrap_or_default();
    let args: Value =
        call["function"]["arguments"].as_str().and_then(|a| serde_json::from_str(a).ok()).unwrap_or_default();
    journal::event(
        "step",
        json!({
            "milestone": milestone_id, "model": model, "shot": shot_path,
            // Wall time of the whole turn (what the learner waited), then its parts.
            "latency_ms": started.elapsed().as_millis(),
            "model_ms": metrics.model_ms, "search_ms": metrics.search_ms,
            "requests": metrics.requests, "invalid": metrics.invalid, "searches": metrics.searches,
            // Our estimate next to the real prompt tokens, to calibrate CONTEXT_BUDGET.
            "context_tokens_est": estimate_tokens(&session.messages),
            // Summed over the requests that reported usage.
            "tokens": {
                "prompt": metrics.prompt, "cached": metrics.cached,
                "reasoning": metrics.reasoning, "completion": metrics.completion,
            },
            "finish_reason": msg["finish_reason"],
            "action": { "name": call["function"]["name"], "args": args }, "reasoning": reasoning,
        }),
    );

    let (kind, element, point, text, keys, instruction, path, typed) = match action {
        Action::Answer { evidence } => {
            let id = session.close_current(Status::Done, &evidence).ok_or("Aucune étape en cours")?;
            return Ok(Turn::MilestoneDone(id));
        }
        Action::Search { .. } => unreachable!("searches are handled in the loop"),
        Action::Click { element, x, y, instruction } => {
            let fallback = format!("Click {element}");
            let path = format!("click {element}");
            ("click", element, Some((x, y)), String::new(), String::new(), or(instruction, fallback), path, None)
        }
        Action::Write { element, x, y, content, instruction } => {
            let fallback = format!("Type \"{content}\" in {element}");
            let path = format!("type \"{content}\" in {element}");
            let typed = Some(content.clone());
            ("write", element, Some((x, y)), content, String::new(), or(instruction, fallback), path, typed)
        }
        Action::Scroll { x, y, direction, instruction } => {
            let fallback = format!("Scroll {direction}");
            let path = format!("scroll {direction}");
            ("scroll", String::new(), Some((x, y)), String::new(), String::new(), or(instruction, fallback), path, None)
        }
        Action::PressKey { keys, instruction } => {
            let fallback = format!("Press {keys}");
            let path = format!("press {keys}");
            ("press_key", String::new(), None, String::new(), keys, or(instruction, fallback), path, None)
        }
    };
    // Judged on the next screenshot (`observe_outcome`).
    session.actions.entry(milestone_id.clone()).or_default().push(ActionRecord {
        path,
        outcome: Outcome::Proposed,
        typed,
    });

    if let (Some(rel), Some((x, y))) = (shot_path, point) {
        journal::mark(rel, &shot.data_uri, x, y);
    }
    let current = session.current_milestone().cloned();
    Ok(Turn::Action(Box::new(Step {
        kind: kind.into(),
        instruction,
        element,
        point,
        text,
        keys,
        unchanged: false,
        milestone: current.as_ref().map(|m| view(&session.tutorial, m, "current")),
        progress: session.progress(),
        completed: Vec::new(),
        teach: current.and_then(|m| m.teach),
    })))
}

/// Rough prompt size of a conversation: text at ~4 characters per token,
/// and the screenshots that survive `trim_images` at `IMAGE_TOKENS` each.
fn estimate_tokens(messages: &[Value]) -> usize {
    let mut chars = 0;
    let mut images = 0;
    for m in messages {
        match &m["content"] {
            Value::String(t) => chars += t.len(),
            Value::Array(parts) => {
                for p in parts {
                    if p["type"] == "image_url" {
                        images += 1;
                    } else {
                        chars += p["text"].as_str().map_or(0, str::len);
                    }
                }
            }
            _ => {}
        }
        for c in m["tool_calls"].as_array().into_iter().flatten() {
            chars += c["function"]["arguments"].as_str().map_or(0, str::len) + 16;
        }
    }
    chars / 4 + images.min(MAX_IMAGES) * IMAGE_TOKENS
}

/// Keeps a milestone's conversation bounded: the system and task messages,
/// a one-line summary of folded turns, and the most recent observation
/// turns verbatim: at most `MAX_TURNS`, fewer when the estimate exceeds
/// `budget` tokens (long search results), never under `MIN_TURNS`. A turn
/// starts at an observation and holds the calls and tool results that
/// follow it, so call/result pairs are never split. Only the newest
/// observation keeps its `<progress>` block (it is re-sent each turn anyway).
fn compact(messages: &mut Vec<Value>, budget: usize) {
    const HEAD: usize = 2; // system + task
    const FOLDED: &str = "Earlier steps on this task (folded):";
    if messages.len() <= HEAD {
        return;
    }
    let is_observation = |m: &Value| m["role"] == "user" && m["content"].is_array();
    let starts: Vec<usize> = (HEAD..messages.len()).filter(|&i| is_observation(&messages[i])).collect();
    let mut keep = starts.len().min(MAX_TURNS);
    while keep > MIN_TURNS {
        let from = starts[starts.len() - keep];
        let head_and_tail: Vec<Value> = messages[..HEAD].iter().chain(&messages[from..]).cloned().collect();
        if estimate_tokens(&head_and_tail) <= budget {
            break;
        }
        keep -= 1;
    }
    if keep < starts.len() {
        let cut = starts[starts.len() - keep];
        let mut summary: Vec<String> = Vec::new();
        for m in messages.drain(HEAD..cut) {
            if let Some(text) = m["content"].as_str().and_then(|t| t.strip_prefix(FOLDED)) {
                summary.extend(text.lines().map(str::trim).filter(|l| !l.is_empty()).map(String::from));
            }
            for c in m["tool_calls"].as_array().into_iter().flatten() {
                let args: Value =
                    c["function"]["arguments"].as_str().and_then(|a| serde_json::from_str(a).ok()).unwrap_or_default();
                let what = ["element", "keys", "query", "content", "direction"]
                    .iter()
                    .find_map(|k| args[k].as_str())
                    .unwrap_or("");
                summary.push(format!("- {} {what}", c["function"]["name"].as_str().unwrap_or("?")));
            }
        }
        // Only the most recent folded actions are worth their tokens.
        let skip = summary.len().saturating_sub(12);
        let text = format!("{FOLDED}\n{}", summary[skip..].join("\n"));
        messages.insert(HEAD, json!({ "role": "user", "content": text }));
    }
    for m in messages.iter_mut().skip(HEAD) {
        if let Some(parts) = m["content"].as_array_mut()
            && parts.first().and_then(|p| p["text"].as_str()).is_some_and(|t| t.starts_with("<progress>"))
        {
            parts[0] = json!({ "type": "text", "text": "[progress superseded]" });
        }
    }
}

fn or(s: String, fallback: String) -> String {
    if s.trim().is_empty() { fallback } else { s }
}

/// Turns this run into a reusable tutorial: same milestones, with the path
/// that worked (`Session::worked`) as hints. A milestone with no kept
/// action keeps its previous hints.
pub fn to_tutorial(session: &Session) -> Tutorial {
    let mut t = session.tutorial.clone();
    for m in &mut t.milestones {
        let verified = session.worked(&m.id);
        if !verified.is_empty() {
            m.hints = verified;
        }
    }
    if t.source == "generated" {
        t.source = "recorded".into();
    }
    t.version += 1;
    t.language = session.lang.clone().or(t.language);
    t
}

#[cfg(test)]
mod tests {
    use super::*;

    fn call(name: &str, args: &str) -> Value {
        json!({ "role": "assistant", "finish_reason": "tool_calls", "tool_calls": [
            { "id": "c1", "type": "function", "function": { "name": name, "arguments": args } }
        ]})
    }

    #[test]
    fn accepts_a_well_formed_click() {
        let (_, a) =
            validate(&call("click", r#"{"element":"Add menu","x":120,"y":40,"instruction":"Ouvre Add"}"#), true)
                .unwrap();
        assert_eq!(a, Action::Click { element: "Add menu".into(), x: 120.0, y: 40.0, instruction: "Ouvre Add".into() });
    }

    #[test]
    fn truncated_answer_never_closes_a_milestone() {
        let e = validate(&call("answer", r#"{"content":"The object is"#), true).unwrap_err();
        assert!(e.call.is_none(), "a broken call is not echoed back");
        assert!(validate(&call("answer", "{}"), true).is_err());
        assert!(validate(&call("answer", r#"{"content":"  "}"#), true).is_err());
    }

    #[test]
    fn cut_off_response_is_rejected() {
        let mut m = call("answer", r#"{"content":"Torus visible"}"#);
        m["finish_reason"] = json!("length");
        assert!(validate(&m, true).is_err());
    }

    #[test]
    fn rejects_out_of_range_and_missing_fields() {
        assert!(validate(&call("click", r#"{"element":"e","x":8000,"y":10}"#), true).is_err());
        assert!(validate(&call("click", r#"{"element":"e"}"#), true).is_err());
        assert!(validate(&call("press_key", r#"{"keys":""}"#), true).is_err());
        assert!(validate(&call("scroll", r#"{"x":1,"y":1,"direction":"sideways"}"#), true).is_err());
        assert!(validate(&call("teleport", "{}"), true).is_err());
    }

    #[test]
    fn rejects_several_calls_and_missing_id() {
        let mut m = call("click", r#"{"element":"e","x":1,"y":1}"#);
        let first = m["tool_calls"][0].clone();
        m["tool_calls"].as_array_mut().unwrap().push(first);
        assert!(validate(&m, true).is_err());
        let mut m = call("click", r#"{"element":"e","x":1,"y":1}"#);
        m["tool_calls"][0]["id"] = json!("");
        assert!(validate(&m, true).is_err());
    }

    #[test]
    fn every_explaining_answer_is_refused() {
        // Refused each time, not only the first: validation has no "refused once" bypass.
        let long = format!(r#"{{"content":"{}"}}"#, "x".repeat(300));
        for _ in 0..3 {
            let e = validate(&call("answer", &long), true).unwrap_err();
            assert!(e.feedback.unwrap().starts_with("Refused"));
        }
        assert!(validate(&call("answer", r#"{"content":"line one\nline two"}"#), true).is_err());
    }

    #[test]
    fn search_is_refused_once_its_budget_is_spent() {
        let c = call("search", r#"{"app_name":"Blender","query":"add torus"}"#);
        assert!(validate(&c, true).is_ok());
        assert!(validate(&c, false).is_err());
        let names: Vec<_> = tools(false).as_array().unwrap().iter().map(|t| t["function"]["name"].clone()).collect();
        assert!(!names.contains(&json!("search")));
    }

    fn milestone(id: &str, requires: &[&str]) -> Milestone {
        Milestone {
            id: id.into(),
            goal: id.into(),
            done_when: id.into(),
            requires: requires.iter().map(|s| s.to_string()).collect(),
            ..Default::default()
        }
    }

    /// A session without journal side effects.
    fn session(milestones: Vec<Milestone>) -> Session {
        let tutorial =
            Tutorial { id: "t".into(), title: "t".into(), goal: "g".into(), milestones, ..Default::default() };
        let status = tutorial.milestones.iter().map(|m| (m.id.clone(), Status::Todo)).collect();
        let mut s = Session {
            tutorial,
            lang: None,
            status,
            current: None,
            messages: Vec::new(),
            pending_call: None,
            actions: HashMap::new(),
            facts: Vec::new(),
            last_done: None,
            evidence: HashMap::new(),
            step: Step::default(),
            before: None,
            finished: false,
            blocked: None,
            completed: Vec::new(),
        };
        s.start_next_milestone();
        s
    }

    #[test]
    fn many_closures_in_a_row_never_finish_early() {
        let mut s = session((0..6).map(|i| milestone(&format!("m{i}"), &[])).collect());
        for i in 0..5 {
            assert_eq!(s.current.as_deref(), Some(format!("m{i}").as_str()));
            let id = s.close_current(Status::Done, "visible").unwrap();
            s.completed.push(id);
            s.start_next_milestone();
            assert!(!s.finished);
        }
        assert_eq!(s.current.as_deref(), Some("m5"));
        assert_eq!(s.completed.len(), 5);
        s.close_current(Status::Done, "visible");
        s.start_next_milestone();
        assert!(s.finished);
    }

    #[test]
    fn skipping_drops_the_previous_pointer() {
        let mut s = session(vec![milestone("a", &[]), milestone("b", &[])]);
        s.step = Step { kind: "click".into(), point: Some((10.0, 10.0)), ..Default::default() };
        s.pending_call = Some("c1".into());
        s.skip_milestone();
        assert_eq!(s.step.kind, "pending");
        assert!(s.step.point.is_none() && s.before.is_none() && s.pending_call.is_none());
        assert_eq!(s.step.milestone.as_ref().unwrap().id, "b");
    }

    #[test]
    fn blocked_graph_is_not_complete() {
        let mut s = session(vec![milestone("a", &[]), milestone("b", &["c"]), milestone("c", &["b"])]);
        s.close_current(Status::Done, "visible");
        s.start_next_milestone();
        assert!(!s.finished);
        assert_eq!(s.blocked, Some(vec!["b".to_string(), "c".to_string()]));
    }

    // ---- advance() end to end, with a scripted model ----

    use std::collections::VecDeque;
    use std::sync::Mutex;

    /// Plays back scripted responses and records every request body.
    #[derive(Default)]
    struct Fake {
        replies: Mutex<VecDeque<Result<Value, String>>>,
        bodies: Mutex<Vec<Value>>,
        searches: Mutex<Vec<String>>,
    }

    impl Fake {
        fn new(replies: Vec<Result<Value, String>>) -> Self {
            Self { replies: Mutex::new(replies.into()), ..Default::default() }
        }
        fn requests(&self) -> usize {
            self.bodies.lock().unwrap().len()
        }
    }

    impl Brain for Fake {
        async fn chat(&self, body: &Value) -> Result<(Value, u128, Value), String> {
            self.bodies.lock().unwrap().push(body.clone());
            let reply = self.replies.lock().unwrap().pop_front().expect("unscripted request")?;
            Ok((reply, 5, json!({ "prompt_tokens": 100, "completion_tokens": 10 })))
        }
        async fn search(&self, _app: &str, query: &str) -> String {
            self.searches.lock().unwrap().push(query.into());
            format!("docs for {query}")
        }
    }

    fn answer() -> Result<Value, String> {
        Ok(call("answer", r#"{"content":"Visible on screen"}"#))
    }
    fn click() -> Result<Value, String> {
        Ok(call("click", r#"{"element":"Add menu","x":100,"y":50,"instruction":"Clique sur Add"}"#))
    }
    fn nothing() -> Result<Value, String> {
        Ok(json!({ "role": "assistant", "finish_reason": "stop", "content": "hmm", "tool_calls": null }))
    }

    fn shot() -> Shot {
        Shot { data_uri: "data:image/jpeg;base64,AA==".into(), thumb: image::GrayImage::new(96, 54) }
    }

    fn step(brain: &Fake, s: &mut Session, event: Option<&str>) -> Result<Step, String> {
        tauri::async_runtime::block_on(advance_on(brain, s, event.map(String::from), shot(), false))
    }

    fn linear(n: usize) -> Session {
        session((0..n).map(|i| milestone(&format!("m{i}"), &[])).collect())
    }

    #[test]
    fn five_closures_then_an_action_on_the_sixth() {
        let mut s = linear(6);
        let brain = Fake::new(vec![answer(), answer(), answer(), answer(), answer(), click()]);
        let st = step(&brain, &mut s, None).unwrap();
        assert_eq!(st.kind, "click");
        assert_eq!(st.completed, ["m0", "m1", "m2", "m3", "m4"]);
        assert_eq!(st.milestone.unwrap().id, "m5");
        assert!(!s.finished);
    }

    #[test]
    fn chaining_through_every_milestone_finishes_for_real() {
        let mut s = linear(6);
        let brain = Fake::new((0..6).map(|_| answer()).collect());
        let st = step(&brain, &mut s, None).unwrap();
        assert_eq!(st.kind, "done");
        assert_eq!(st.completed.len(), 6);
        assert!(s.finished);
    }

    #[test]
    fn truncated_answers_leave_the_milestone_open() {
        let mut s = linear(2);
        let cut = || Ok(call("answer", r#"{"content":"The object is"#));
        let brain = Fake::new(vec![cut(), cut(), cut()]);
        assert!(step(&brain, &mut s, None).is_err());
        assert_eq!(s.current.as_deref(), Some("m0"));
        assert_eq!(s.status["m0"], Status::Current);
        assert_eq!(brain.requests(), MAX_ATTEMPTS);
    }

    #[test]
    fn a_refused_answer_on_the_last_attempt_is_not_executed() {
        let mut s = linear(2);
        let long = Ok(call("answer", &format!(r#"{{"content":"{}"}}"#, "x".repeat(300))));
        let brain = Fake::new(vec![nothing(), nothing(), long]);
        assert!(step(&brain, &mut s, None).is_err());
        assert_eq!(s.status["m0"], Status::Current);
        assert!(s.completed.is_empty());
    }

    #[test]
    fn refusal_feedback_reaches_the_retry() {
        let mut s = linear(2);
        let long = Ok(call("answer", &format!(r#"{{"content":"{}"}}"#, "x".repeat(300))));
        let brain = Fake::new(vec![long, click()]);
        assert_eq!(step(&brain, &mut s, None).unwrap().kind, "click");
        let retry = &brain.bodies.lock().unwrap()[1];
        let last = retry["messages"].as_array().unwrap().last().unwrap();
        assert_eq!(last["role"], "tool");
        assert!(last["content"].as_str().unwrap().starts_with("Refused"));
        // The refusal stays out of the milestone's conversation.
        assert!(!s.messages.iter().any(|m| m["content"].as_str().is_some_and(|c| c.starts_with("Refused"))));
    }

    #[test]
    fn failed_transition_keeps_progress_and_drops_the_old_pointer() {
        let mut s = linear(3);
        let brain = Fake::new(vec![click()]);
        assert_eq!(step(&brain, &mut s, None).unwrap().kind, "click");
        // m0 closes, then the request for m1's first action fails.
        let brain = Fake::new(vec![answer(), Err("network down".into())]);
        assert!(step(&brain, &mut s, Some("The learner clicked")).is_err());
        assert_eq!(s.step.kind, "pending");
        assert!(s.step.point.is_none());
        assert_eq!(s.step.milestone.as_ref().unwrap().id, "m1");
        // The next success still reports m0 as completed.
        let brain = Fake::new(vec![click()]);
        assert_eq!(step(&brain, &mut s, None).unwrap().completed, ["m0"]);
    }

    #[test]
    fn blocked_graph_reports_an_error_not_done() {
        let mut s = session(vec![milestone("a", &[]), milestone("b", &["c"]), milestone("c", &["b"])]);
        let brain = Fake::new(vec![answer()]);
        let e = step(&brain, &mut s, None).unwrap_err();
        assert!(e.contains("bloqué"), "{e}");
        assert!(!s.finished);
    }

    #[test]
    fn searches_are_bounded_then_withdrawn() {
        let mut s = linear(1);
        let search = || Ok(call("search", r#"{"app_name":"Blender","query":"add torus"}"#));
        let brain = Fake::new(vec![search(), search(), click()]);
        assert_eq!(step(&brain, &mut s, None).unwrap().kind, "click");
        assert_eq!(brain.searches.lock().unwrap().len(), MAX_SEARCHES);
        let bodies = brain.bodies.lock().unwrap();
        let offers_search =
            |b: &Value| b["tools"].as_array().unwrap().iter().any(|t| t["function"]["name"] == "search");
        assert!(offers_search(&bodies[0]) && offers_search(&bodies[1]));
        assert!(!offers_search(&bodies[2]));
    }

    #[test]
    fn learner_report_answers_the_pending_call() {
        let mut s = linear(1);
        step(&Fake::new(vec![click()]), &mut s, None).unwrap();
        let brain = Fake::new(vec![click()]);
        step(&brain, &mut s, Some("The learner clicked the highlighted element")).unwrap();
        let msgs = brain.bodies.lock().unwrap()[0]["messages"].as_array().unwrap().clone();
        let tool = msgs.iter().find(|m| m["role"] == "tool").unwrap();
        assert_eq!(tool["tool_call_id"], "c1");
        assert_eq!(tool["content"], "The learner clicked the highlighted element");
    }

    #[test]
    fn long_milestones_keep_a_bounded_history() {
        let mut s = linear(1);
        for _ in 0..20 {
            step(&Fake::new(vec![click()]), &mut s, Some("The learner clicked")).unwrap();
        }
        let observations = s.messages.iter().filter(|m| m["role"] == "user" && m["content"].is_array()).count();
        assert!(observations <= MAX_TURNS + 1, "{observations} observations kept");
        let progress = s
            .messages
            .iter()
            .filter(|m| m["content"][0]["text"].as_str().is_some_and(|t| t.starts_with("<progress>")))
            .count();
        assert_eq!(progress, 1);
        assert!(s.messages[2]["content"].as_str().unwrap().contains("click Add menu"));
        // Every call still has its result, in order.
        for (i, m) in s.messages.iter().enumerate() {
            if m["role"] == "tool" {
                assert_eq!(s.messages[i - 1]["tool_calls"][0]["id"], m["tool_call_id"]);
            }
        }
    }

    // ---- outcomes, facts, freshness ----

    fn shot_of(v: u8) -> Shot {
        Shot {
            data_uri: "data:image/jpeg;base64,AA==".into(),
            thumb: image::GrayImage::from_pixel(96, 54, image::Luma([v])),
        }
    }

    fn step_on(brain: &Fake, s: &mut Session, event: &str, v: u8) -> Step {
        tauri::async_runtime::block_on(advance_on(brain, s, Some(event.into()), shot_of(v), false)).unwrap()
    }

    fn write() -> Result<Value, String> {
        Ok(call(
            "write",
            r#"{"element":"Name field","x":300,"y":200,"content":"MyDonut","instruction":"Tape MyDonut"}"#,
        ))
    }

    #[test]
    fn outcomes_are_judged_on_the_next_screen() {
        let mut s = linear(1);
        step_on(&Fake::new(vec![click()]), &mut s, "start", 100);
        step_on(&Fake::new(vec![click()]), &mut s, "clicked", 160); // screen moved
        step_on(&Fake::new(vec![write()]), &mut s, "clicked", 160); // nothing moved
        step_on(&Fake::new(vec![click()]), &mut s, "typed", 160); // typing: too small to see
        let outcomes: Vec<Outcome> = s.actions["m0"].iter().map(|a| a.outcome).collect();
        assert_eq!(outcomes, [Outcome::Changed, Outcome::NoEffect, Outcome::Unknown, Outcome::Proposed]);
    }

    #[test]
    fn repeating_a_dead_action_is_pointed_out() {
        let mut s = linear(1);
        step_on(&Fake::new(vec![click()]), &mut s, "start", 100);
        step_on(&Fake::new(vec![click()]), &mut s, "clicked", 100);
        let brain = Fake::new(vec![click()]);
        step_on(&brain, &mut s, "clicked again", 100);
        let body = &brain.bodies.lock().unwrap()[0];
        let tool = body["messages"].as_array().unwrap().iter().rev().find(|m| m["role"] == "tool").unwrap();
        let text = tool["content"].as_str().unwrap();
        assert!(text.starts_with("clicked again") && text.contains("2 times in a row"), "{text}");
    }

    #[test]
    fn typed_choices_reach_later_milestones() {
        let mut s = linear(2);
        step_on(&Fake::new(vec![write()]), &mut s, "start", 100);
        let brain = Fake::new(vec![answer(), click()]);
        step_on(&brain, &mut s, "typed", 100);
        assert_eq!(s.current.as_deref(), Some("m1"));
        let progress = s.progress_block();
        assert!(progress.contains(r#"type "MyDonut" in Name field"#), "{progress}");
        assert!(progress.contains("(seen: Visible on screen)"), "{progress}");
    }

    #[test]
    fn saved_tutorial_keeps_only_the_path_that_worked() {
        let mut s = linear(1);
        let rec = |path: &str, outcome| ActionRecord { path: path.into(), outcome, typed: None };
        s.actions.insert(
            "m0".into(),
            vec![
                rec("click Wrong menu", Outcome::NoEffect),
                rec("click Stale button", Outcome::Superseded),
                rec("click Add menu", Outcome::Changed),
                rec("type \"x\" in Name", Outcome::Unknown),
                rec("press cmd+s", Outcome::NoEffect),
            ],
        );
        let t = to_tutorial(&s);
        assert_eq!(t.milestones[0].hints, ["click Add menu", "type \"x\" in Name", "press cmd+s"]);
    }

    /// Captures play back in order.
    fn captures(values: Vec<u8>) -> impl Fn() -> std::future::Ready<Result<Shot, String>> {
        let queue = Mutex::new(VecDeque::from(values));
        move || std::future::ready(Ok(shot_of(queue.lock().unwrap().pop_front().expect("unscripted capture"))))
    }

    #[test]
    fn a_slow_step_on_a_moved_screen_is_recomputed() {
        let mut s = linear(1);
        let brain = Fake::new(vec![click(), Ok(call("click", r#"{"element":"OK button","x":500,"y":500}"#))]);
        let step = tauri::async_runtime::block_on(advance_with(
            &brain,
            &mut s,
            None,
            false,
            std::time::Duration::ZERO,
            captures(vec![100, 180]),
        ))
        .unwrap();
        assert_eq!(step.element, "OK button");
        assert_eq!(brain.requests(), 2);
        let outcomes: Vec<Outcome> = s.actions["m0"].iter().map(|a| a.outcome).collect();
        assert_eq!(outcomes, [Outcome::Superseded, Outcome::Proposed]);
        let msgs = brain.bodies.lock().unwrap()[1]["messages"].as_array().unwrap().clone();
        let tool = msgs.iter().rev().find(|m| m["role"] == "tool").unwrap();
        assert!(tool["content"].as_str().unwrap().starts_with("Not shown to the learner"));
        // The pointer is judged against the screen it was computed on.
        assert_eq!(s.before.as_ref().unwrap().thumb.get_pixel(0, 0).0[0], 180);
    }

    #[test]
    fn a_slow_step_on_a_still_screen_is_kept() {
        let mut s = linear(1);
        let brain = Fake::new(vec![click()]);
        let step = tauri::async_runtime::block_on(advance_with(
            &brain,
            &mut s,
            None,
            false,
            std::time::Duration::ZERO,
            captures(vec![100, 100]),
        ))
        .unwrap();
        assert_eq!(step.element, "Add menu");
        assert_eq!(brain.requests(), 1);
    }

    // ---- context window ----

    #[test]
    fn progress_is_a_window_around_the_current_milestone() {
        let mut s = linear(20);
        for _ in 0..10 {
            s.close_current(Status::Done, "ok");
            s.start_next_milestone();
        }
        let p = s.progress_block();
        assert!(p.contains("… 7 earlier milestones (7 done)"), "{p}");
        assert!(p.contains("→ m10"), "{p}");
        assert!(p.contains("· m13") && !p.contains("· m14"), "{p}");
        assert!(p.contains("… 6 more milestones after these"), "{p}");
        assert!(!p.contains("✓ m0 "), "{p}");
    }

    #[test]
    fn the_last_milestone_recalls_how_it_was_done() {
        let mut s = linear(3);
        step_on(&Fake::new(vec![click()]), &mut s, "start", 100);
        step_on(&Fake::new(vec![answer(), click()]), &mut s, "clicked", 170);
        let p = s.progress_block();
        assert!(p.contains("✓ m0 (seen: Visible on screen)\n  done via: click Add menu"), "{p}");
    }

    #[test]
    fn a_huge_search_result_folds_turns_early() {
        let mut s = linear(1);
        for _ in 0..3 {
            step_on(&Fake::new(vec![click()]), &mut s, "clicked", 100);
        }
        let huge = format!("docs {}", "x".repeat(60_000));
        let call = s.messages.iter().rev().find(|m| m["role"] == "assistant").unwrap()["tool_calls"][0]["id"].clone();
        s.messages.push(json!({ "role": "tool", "tool_call_id": call, "content": huge }));
        s.pending_call = None;
        let before = estimate_tokens(&s.messages);
        compact(&mut s.messages, CONTEXT_BUDGET);
        let obs = s.messages.iter().filter(|m| m["role"] == "user" && m["content"].is_array()).count();
        assert!(before > CONTEXT_BUDGET);
        // The huge result sits in the newest turn, which is never folded.
        assert_eq!(obs, MIN_TURNS);
        assert!(s.messages[2]["content"].as_str().unwrap().starts_with("Earlier steps"));
    }

    #[test]
    fn small_conversations_are_left_alone() {
        let mut s = linear(1);
        for _ in 0..3 {
            step_on(&Fake::new(vec![click()]), &mut s, "clicked", 100);
        }
        let n = s.messages.len();
        compact(&mut s.messages, CONTEXT_BUDGET);
        assert_eq!(s.messages.len(), n);
        assert!(estimate_tokens(&s.messages) < CONTEXT_BUDGET);
    }

    #[test]
    fn long_search_results_are_cut() {
        struct Verbose(Fake);
        impl Brain for Verbose {
            async fn chat(&self, body: &Value) -> Result<(Value, u128, Value), String> {
                self.0.chat(body).await
            }
            async fn search(&self, _app: &str, _query: &str) -> String {
                "é".repeat(10_000)
            }
        }
        let mut s = linear(1);
        let brain = Verbose(Fake::new(vec![Ok(call("search", r#"{"query":"torus"}"#)), click()]));
        tauri::async_runtime::block_on(advance_on(&brain, &mut s, None, shot(), false)).unwrap();
        let tool = s.messages.iter().find(|m| m["role"] == "tool").unwrap()["content"].as_str().unwrap().to_string();
        assert!(tool.len() <= MAX_SEARCH_CHARS + 20 && tool.ends_with("[result truncated]"));
    }
}
