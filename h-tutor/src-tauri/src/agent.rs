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

use crate::capture::{capture_primary, thumb_diff, Shot};
use crate::holo::{self, Holo};
use crate::journal;
use crate::tutorial::{Milestone, Status, Tutorial};
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::{HashMap, HashSet};

const MAX_IMAGES: usize = 3;
/// Milestones that can be closed in one `advance` (already done on screen).
const MAX_CHAIN: usize = 4;

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

fn tools() -> Value {
    let el = json!({ "type": "string", "description": "Detailed description of the target UI element" });
    let x = json!({ "type": "integer", "description": "X coordinate as integer in [0, 1000]" });
    let y = json!({ "type": "integer", "description": "Y coordinate as integer in [0, 1000]" });
    json!([
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
        crate::search::tool(),
        { "type": "function", "function": {
            "name": "answer",
            "description": "Call when the latest screenshot shows the current task's success criterion is met.",
            "parameters": { "type": "object",
                "properties": { "content": { "type": "string",
                    "description": "What on the screenshot proves the task is done (one short English sentence)" } },
                "required": ["content"] }
        }}
    ])
}

#[derive(Serialize, Clone, Default)]
pub struct MilestoneView {
    pub id: String,
    pub goal: String,
    pub status: String,
    pub optional: bool,
    /// The source video at the moment that shows this milestone (YouTube imports).
    pub video_url: Option<String>,
}

/// What the learner should do now, as shown in the bar.
#[derive(Serialize, Clone, Default)]
pub struct Step {
    /// click | write | scroll | press_key | done
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

pub struct Session {
    pub tutorial: Tutorial,
    lang: Option<String>,
    status: HashMap<String, Status>,
    current: Option<String>,
    /// Conversation for the current milestone only.
    messages: Vec<Value>,
    pending_call: Option<String>,
    /// Actions given per milestone ("click: Add menu in the top bar"), used to
    /// turn this run into a tutorial with a known path.
    pub actions: HashMap<String, Vec<String>>,
    pub evidence: HashMap<String, String>,
    pub step: Step,
    /// Screen when the current step was given (for "did anything change?").
    pub before: Option<Shot>,
    pub finished: bool,
}

impl Session {
    pub fn new(tutorial: Tutorial, lang: Option<&str>) -> Self {
        let status = tutorial.milestones.iter().map(|m| (m.id.clone(), Status::Todo)).collect();
        journal::begin(&tutorial, lang);
        let mut s = Self {
            tutorial,
            lang: lang.map(String::from),
            status,
            current: None,
            messages: Vec::new(),
            pending_call: None,
            actions: HashMap::new(),
            evidence: HashMap::new(),
            step: Step::default(),
            before: None,
            finished: false,
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
    /// for it. Returns false when the tutorial is complete.
    fn start_next_milestone(&mut self) -> bool {
        let Some(m) = self.tutorial.next_milestone(&self.finished_set()).cloned() else {
            self.current = None;
            self.finished = true;
            return false;
        };
        self.status.insert(m.id.clone(), Status::Current);
        self.current = Some(m.id.clone());
        self.pending_call = None;

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
        true
    }

    fn close_current(&mut self, status: Status, evidence: &str) -> Option<String> {
        let id = self.current.take()?;
        self.status.insert(id.clone(), status);
        self.evidence.insert(id.clone(), evidence.to_string());
        let kind = if status == Status::Skipped { "milestone_skipped" } else { "milestone_done" };
        journal::event(kind, json!({ "milestone": id, "evidence": evidence }));
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
        if let Some(l) = lang.filter(|l| language_name(l).is_some()) {
            if self.lang.as_deref() != Some(l) {
                journal::event("language", json!({ "from": self.lang, "to": l }));
                self.lang = Some(l.to_string());
            }
        }
    }

    fn progress_block(&self) -> String {
        let lang = self.lang.as_deref().and_then(language_name).unwrap_or("English");
        let tu = if lang == "French" { ", using \"tu\"" } else { "" };
        let mut out = format!(
            "<progress>\nLearner language: {lang}. Write every instruction in {lang}{tu}.\nTutorial goal: {}\n",
            self.tutorial.goal
        );
        for m in &self.tutorial.milestones {
            let (mark, extra) = match self.status.get(&m.id) {
                Some(Status::Done) => ("✓", String::new()),
                Some(Status::Skipped) => ("–", " (skipped)".to_string()),
                Some(Status::Current) => (
                    "→",
                    format!(
                        " (current; done when: {}){}",
                        m.done_when,
                        if m.hints.is_empty() { String::new() } else { format!("\n  known path: {}", m.hints.join("; ")) }
                    ),
                ),
                _ => ("·", if m.optional { " (optional)".to_string() } else { String::new() }),
            };
            out += &format!("{mark} {}{extra}\n", m.goal);
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

/// Advances the session: reports what the learner did (`event`), sends the
/// new screenshot, and asks Holo for the next action. Milestones Holo
/// declares done are closed and the next one starts on the same screenshot.
pub async fn advance(
    holo: &Holo,
    session: &mut Session,
    event: Option<String>,
    only_if_changed: bool,
) -> Result<Step, String> {
    let shot = tauri::async_runtime::spawn_blocking(capture_primary)
        .await
        .map_err(|e| e.to_string())??;

    if only_if_changed {
        if let Some(before) = &session.before {
            if thumb_diff(&before.thumb, &shot.thumb) < 0.6 {
                return Ok(Step { unchanged: true, ..session.step.clone() });
            }
        }
    }
    if let Some(ev) = &event {
        journal::event("learner", json!({ "milestone": session.current, "event": ev }));
    }
    let shot_path = journal::shot(&shot.data_uri);

    let mut event = event;
    let mut completed = Vec::new();
    for _ in 0..=MAX_CHAIN {
        if session.finished {
            break;
        }
        match ask_holo(holo, session, event.take(), &shot, shot_path.as_deref()).await? {
            Turn::Action(mut step) => {
                step.completed = completed;
                session.step = step.clone();
                session.before = Some(shot);
                return Ok(step);
            }
            Turn::MilestoneDone(id) => {
                completed.push(id);
                session.start_next_milestone();
            }
        }
    }

    // Tutorial complete.
    session.finished = true;
    journal::event("tutorial_done", json!({}));
    journal::end("completed");
    let step = Step {
        kind: "done".into(),
        instruction: String::new(),
        completed,
        progress: session.progress(),
        ..Default::default()
    };
    session.step = step.clone();
    session.before = Some(shot);
    Ok(step)
}

enum Turn {
    Action(Step),
    MilestoneDone(String),
}

/// One Holo turn on the current milestone's conversation.
async fn ask_holo(
    holo: &Holo,
    session: &mut Session,
    event: Option<String>,
    shot: &Shot,
    shot_path: Option<&str>,
) -> Result<Turn, String> {
    if let (Some(id), Some(ev)) = (session.pending_call.take(), event) {
        session.messages.push(json!({ "role": "tool", "tool_call_id": id, "content": ev }));
    }
    session.messages.push(json!({ "role": "user", "content": [
        { "type": "text", "text": session.progress_block() },
        { "type": "text", "text": "<observation>\n" },
        { "type": "image_url", "image_url": { "url": shot.data_uri } },
        { "type": "text", "text": "\n</observation>" }
    ]}));
    session.trim_images();

    let model = holo::smart_model();
    // Searches run inside the step: Holo asks, we fetch, Holo continues on
    // the same screenshot, until it picks an action for the learner.
    const MAX_SEARCHES: usize = 2;
    let mut searches = 0;
    let mut rounds = 0;
    let (call, msg, ms, usage) = loop {
        rounds += 1;
        if rounds > MAX_SEARCHES + 2 {
            return Err("Holo a continué à chercher sans choisir d'action".into());
        }
        let mut body = json!({
            "model": model,
            "messages": session.messages,
            "tools": tools(),
            "tool_choice": "required",
            "temperature": 0.8,
            "reasoning_effort": std::env::var("HOLO_REASONING").unwrap_or_else(|_| "low".into()),
            // A runaway reasoning trace must not stall the step: a cut answer
            // (no tool call) is simply asked again below.
            "max_tokens": 3072,
        });

        // A step without a tool call is not a stop: ask again (bounded). An
        // `answer` that explains the procedure instead of finishing is refused once.
        let mut msg = Value::Null;
        let mut ms = 0;
        let mut usage = Value::Null;
        let mut refused = false;
        for _ in 0..3 {
            // Streamed: the bar shows Holo's reasoning while it decides.
            let (m, t, u) = holo.chat_stream(&body, &crate::emit_thinking).await?;
            ms += t;
            msg = m;
            usage = u;
            let Some(first) = msg["tool_calls"].as_array().and_then(|c| c.first()).cloned() else { continue };
            let text: String = first["function"]["arguments"]
                .as_str()
                .and_then(|a| serde_json::from_str::<Value>(a).ok())
                .and_then(|a| a["content"].as_str().map(String::from))
                .unwrap_or_default();
            if first["function"]["name"] == "answer" && !refused && (text.len() > 240 || text.contains('\n')) {
                refused = true;
                let msgs = body["messages"].as_array_mut().expect("messages");
                msgs.push(json!({ "role": "assistant", "content": "", "tool_calls": [first.clone()] }));
                msgs.push(json!({ "role": "tool", "tool_call_id": first["id"], "content":
                    "Refused: do not explain the procedure. If the success criterion is met on the screenshot, \
                     call answer with one short sentence of evidence; otherwise give the single next action." }));
                continue;
            }
            break;
        }
        let call = msg["tool_calls"]
            .as_array()
            .and_then(|c| c.first())
            .cloned()
            .ok_or("Holo n'a pas choisi d'action")?;

        // Keep only the parsed action in history, never the reasoning.
        session.messages.push(json!({
            "role": "assistant",
            "content": msg["content"].as_str().unwrap_or(""),
            "tool_calls": [call.clone()],
        }));

        if call["function"]["name"] == "search" {
            let args: Value = call["function"]["arguments"]
                .as_str()
                .and_then(|a| serde_json::from_str(a).ok())
                .unwrap_or(json!({}));
            let app_name = args["app_name"].as_str().unwrap_or(&session.tutorial.app.name).to_string();
            let query = args["query"].as_str().unwrap_or("").to_string();
            let result = if searches < MAX_SEARCHES && !query.is_empty() {
                searches += 1;
                crate::emit_status(&format!("Recherche dans la documentation de {app_name} : {query}"));
                crate::search::run(holo, &app_name, &query).await.text
            } else {
                "Search limit reached for this step: act on what is visible on screen.".to_string()
            };
            session.messages.push(json!({ "role": "tool", "tool_call_id": call["id"], "content": result }));
            continue;
        }
        break (call, msg, ms, usage);
    };
    session.pending_call = call["id"].as_str().map(String::from);

    let name = call["function"]["name"].as_str().unwrap_or("").to_string();
    let args: Value = call["function"]["arguments"]
        .as_str()
        .and_then(|a| serde_json::from_str(a).ok())
        .unwrap_or(json!({}));
    let s = |k: &str| args[k].as_str().unwrap_or("").to_string();
    let point = match (args["x"].as_f64(), args["y"].as_f64()) {
        (Some(x), Some(y)) => Some((x.clamp(0.0, 1000.0), y.clamp(0.0, 1000.0))),
        _ => None,
    };
    let reasoning = msg["reasoning"].as_str().or(msg["reasoning_content"].as_str()).unwrap_or("");
    let milestone_id = session.current.clone().unwrap_or_default();

    journal::event(
        "step",
        json!({
            "milestone": milestone_id, "model": model, "latency_ms": ms, "shot": shot_path,
            "tokens": {
                "prompt": usage["prompt_tokens"],
                "cached": usage["prompt_tokens_details"]["cached_tokens"],
                "reasoning": usage["completion_tokens_details"]["reasoning_tokens"],
                "completion": usage["completion_tokens"],
            },
            "finish_reason": msg["finish_reason"],
            "action": { "name": name, "args": args }, "reasoning": reasoning,
        }),
    );

    if name == "answer" {
        let id = session.close_current(Status::Done, &s("content")).unwrap_or_default();
        return Ok(Turn::MilestoneDone(id));
    }

    let mut instruction = s("instruction");
    if instruction.is_empty() {
        instruction = match name.as_str() {
            "write" => format!("Type \"{}\" in {}", s("content"), s("element")),
            "press_key" => format!("Press {}", s("keys")),
            "scroll" => format!("Scroll {}", s("direction")),
            _ => format!("Click {}", s("element")),
        };
    }
    // The known path for this milestone, as it actually happened.
    let path = match name.as_str() {
        "write" => format!("type \"{}\" in {}", s("content"), s("element")),
        "press_key" => format!("press {}", s("keys")),
        "scroll" => format!("scroll {}", s("direction")),
        _ => format!("click {}", s("element")),
    };
    session.actions.entry(milestone_id.clone()).or_default().push(path);

    if let (Some(rel), Some((x, y))) = (shot_path, point) {
        journal::mark(rel, &shot.data_uri, x, y);
    }
    let current = session.current_milestone().cloned();
    Ok(Turn::Action(Step {
        kind: name,
        instruction,
        element: s("element"),
        point,
        text: s("content"),
        keys: s("keys"),
        unchanged: false,
        milestone: current.as_ref().map(|m| view(&session.tutorial, m, "current")),
        progress: session.progress(),
        completed: Vec::new(),
        teach: current.and_then(|m| m.teach),
    }))
}

/// Turns this run into a reusable tutorial: same milestones, with the path
/// actually taken as hints. Returns the saved tutorial's id.
pub fn to_tutorial(session: &Session) -> Tutorial {
    let mut t = session.tutorial.clone();
    for m in &mut t.milestones {
        if let Some(path) = session.actions.get(&m.id).filter(|p| !p.is_empty()) {
            m.hints = path.clone();
        }
    }
    if t.source == "generated" {
        t.source = "recorded".into();
    }
    t.version += 1;
    t.language = session.lang.clone().or(t.language);
    t
}
