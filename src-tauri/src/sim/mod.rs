//! Learner simulator: runs the real tutor harness against a simulated
//! learner in a headless browser, and grades the result with code.
//!
//! One run = a scenario (app URL, goal, success check in JavaScript) × a
//! persona × a seed. The tutor is the production loop (`advance_with`,
//! `ask_in_loop`) with real Holo calls; only the screen (headless Chrome)
//! and the hands (a model playing the persona) are simulated. The report
//! says whether the goal was really reached, and how: steps, learner
//! errors, questions, reveals, model time and tokens.
//!
//! `cargo test --lib sim::tests::simulate -- --ignored --nocapture`
//! with `SIM_SCENARIO`, `SIM_PERSONA` (comma list), `SIM_SEEDS` (count).

pub mod autopilot;
pub mod browser;
pub mod learner;

use crate::agent::{self, Session, Step};
use crate::capture::{SCREEN_CHANGED, Shot, shot_from_jpeg, thumb_diff};
use crate::holo::Holo;
use crate::journal;
use crate::tutorial::Tutorial;
use base64::{Engine, engine::general_purpose::STANDARD};
use browser::Browser;
use learner::{Persona, Rng, View};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::Mutex;

/// Same tolerance as a real click on the target (`HIT_RADIUS` in lib.rs).
const HIT_PX: f64 = 48.0;

#[derive(Deserialize, Clone, Debug)]
pub struct Scenario {
    pub id: String,
    pub app: String,
    /// `http(s)://…`, or a path relative to `sim/`.
    pub url: String,
    pub goal: String,
    #[serde(default)]
    pub lang: Option<String>,
    #[serde(default = "default_steps")]
    pub max_steps: usize,
    /// JavaScript expression, true when the goal is really reached.
    pub success: String,
    /// A fixed milestone graph; planned by Holo from the goal when absent.
    #[serde(default)]
    pub tutorial: Option<Tutorial>,
}

fn default_steps() -> usize {
    30
}

pub fn sim_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../sim")
}

impl Scenario {
    pub fn load(id: &str) -> Result<Self, String> {
        let path = sim_dir().join("scenarios").join(format!("{id}.json"));
        let s = std::fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))?;
        serde_json::from_slice(&s).map_err(|e| format!("{id}: {e}"))
    }

    pub fn url(&self) -> String {
        if self.url.starts_with("http") {
            self.url.clone()
        } else {
            let path = sim_dir().join(&self.url);
            format!("file://{}", path.canonicalize().unwrap_or(path).display())
        }
    }
}

#[derive(Serialize, Default, Debug)]
pub struct Report {
    pub scenario: String,
    pub persona: String,
    pub seed: u64,
    /// The success check passed at the end: the goal is really reached.
    pub success: bool,
    /// The tutor declared the tutorial complete.
    pub tutor_done: bool,
    /// The tutor said "done" but the check failed: the learner was
    /// congratulated for something not done (the worst outcome).
    pub false_done: bool,
    pub milestones_total: usize,
    pub milestones_done: usize,
    pub tutor_steps: usize,
    pub learner_actions: usize,
    pub misclicks: usize,
    pub questions: usize,
    pub explanations_pointing: usize,
    pub tutor_questions: usize,
    pub hint_only_steps: usize,
    pub reveals: usize,
    pub stuck: usize,
    pub errors: Vec<String>,
    pub wall_s: f64,
    /// From the session journal.
    pub holo_requests: u64,
    pub holo_model_s: f64,
    pub invalid_responses: u64,
    pub retries: u64,
    pub prompt_tokens: u64,
    pub completion_tokens: u64,
    pub session: Option<String>,
}

async fn look(browser: &Mutex<Browser>) -> Result<Shot, String> {
    let jpeg = browser.lock().await.screenshot().await?;
    shot_from_jpeg(&jpeg)
}

/// The screenshot as the learner sees it: with the tutor's pointer drawn.
fn learner_view(shot: &Shot, pointer: Option<(f64, f64)>) -> Result<String, String> {
    let Some((x, y)) = pointer else { return Ok(shot.data_uri.clone()) };
    let bytes = STANDARD.decode(shot.data_uri.split_once(',').ok_or("bad data uri")?.1).map_err(|e| e.to_string())?;
    let mut img = image::load_from_memory(&bytes).map_err(|e| e.to_string())?.to_rgb8();
    journal::crosshair(&mut img, x, y);
    let mut out = std::io::Cursor::new(Vec::new());
    img.write_to(&mut out, image::ImageFormat::Jpeg).map_err(|e| e.to_string())?;
    Ok(format!("data:image/jpeg;base64,{}", STANDARD.encode(out.into_inner())))
}

fn hit(step: &Step, x: f64, y: f64) -> bool {
    step.point.is_some_and(|(tx, ty)| {
        let dx = (x - tx) / 1000.0 * browser::WIDTH;
        let dy = (y - ty) / 1000.0 * browser::HEIGHT;
        (dx * dx + dy * dy).sqrt() <= HIT_PX
    })
}

/// Sums what the session journal recorded about model use.
fn journal_stats(dir: &std::path::Path, report: &mut Report) {
    let Ok(text) = std::fs::read_to_string(dir.join("events.jsonl")) else { return };
    for e in text.lines().filter_map(|l| serde_json::from_str::<Value>(l).ok()) {
        let n = |v: &Value| v.as_u64().unwrap_or(0);
        match e["type"].as_str() {
            Some("step") => {
                report.holo_requests += n(&e["requests"]);
                report.holo_model_s += n(&e["model_ms"]) as f64 / 1000.0;
                report.prompt_tokens += n(&e["tokens"]["prompt"]);
                report.completion_tokens += n(&e["tokens"]["completion"]);
            }
            Some("explain") => {
                report.holo_requests += n(&e["requests"]);
                report.holo_model_s += n(&e["model_ms"]) as f64 / 1000.0;
            }
            Some("invalid_action") => report.invalid_responses += 1,
            Some("holo_retry") => report.retries += 1,
            _ => {}
        }
    }
}

/// One simulated session.
pub async fn run(holo: &Holo, scenario: &Scenario, persona: &Persona, seed: u64) -> Report {
    let started = std::time::Instant::now();
    let mut report = Report { scenario: scenario.id.clone(), persona: persona.id.into(), seed, ..Default::default() };
    if let Err(e) = drive(holo, scenario, persona, seed, &mut report).await {
        journal::event("sim_error", serde_json::json!({ "error": e }));
        // A run cut by an error still closes its journal.
        journal::end("sim-error");
        report.errors.push(e);
    }
    report.wall_s = (started.elapsed().as_secs_f64() * 10.0).round() / 10.0;
    report
}

async fn drive(
    holo: &Holo,
    scenario: &Scenario,
    persona: &Persona,
    seed: u64,
    report: &mut Report,
) -> Result<(), String> {
    let browser = Arc::new(Mutex::new(Browser::launch(&scenario.url()).await?));
    let capture = || {
        let browser = browser.clone();
        async move { look(&browser).await }
    };
    let lang = scenario.lang.as_deref();

    let tutorial = match &scenario.tutorial {
        Some(t) => t.clone(),
        None => crate::planner::plan(holo, &scenario.goal, &capture().await?, None).await?,
    };
    let mut session = Session::new(tutorial, lang);
    report.session = journal::current_dir().map(|d| d.display().to_string());
    let journal_dir = journal::current_dir();
    journal::event(
        "sim_start",
        serde_json::json!({ "scenario": scenario.id, "app": scenario.app, "persona": persona.id, "seed": seed }),
    );

    let mut rng = Rng::new(seed);
    let mut step = advance(holo, &mut session, None, &browser).await?;
    report.tutor_steps += 1;
    let mut notes: Vec<String> = Vec::new();
    let mut pointer_override: Option<(f64, f64)> = None;
    let mut revealed = false;
    let mut asked_on_step = false;

    for _ in 0..scenario.max_steps {
        if step.kind == "done" {
            break;
        }
        if step.hint_only && !revealed && !asked_on_step {
            report.hint_only_steps += 1;
        }
        let shot = capture().await?;
        let pointer = pointer_override.or(if step.hint_only && !revealed { None } else { step.point });
        let view = View { step: &step, pointer, notes: &notes };
        let decision = learner::decide(holo, persona, &view, &learner_view(&shot, pointer)?).await?;
        journal::event("sim_learner", serde_json::json!({ "decision": format!("{decision:?}") }));

        // Sometimes the learner first asks something (once per step).
        if step.kind != "ask_learner"
            && !asked_on_step
            && !decision.question.trim().is_empty()
            && rng.chance(persona.ask_rate)
        {
            asked_on_step = true;
            report.questions += 1;
            let reply = agent::ask_in_loop(holo, &mut session, decision.question.trim(), shot).await?;
            notes.push(format!(
                "You asked: \"{}\"; the tutor answered: \"{}\"",
                decision.question.trim(),
                reply.answer
            ));
            if reply.point.is_some() {
                report.explanations_pointing += 1;
                pointer_override = reply.point;
            }
            if reply.action == "next" {
                step = advance(
                    holo,
                    &mut session,
                    Some(format!("The learner said: “{}”.", decision.question.trim())),
                    &browser,
                )
                .await?;
                report.tutor_steps += 1;
                (pointer_override, revealed, asked_on_step) = (None, false, false);
            }
            continue;
        }

        let event = match (step.kind.as_str(), decision.kind.as_str()) {
            ("ask_learner", _) => {
                report.tutor_questions += 1;
                let reply = if decision.reply.trim().is_empty() { "Je ne sais pas." } else { decision.reply.trim() };
                notes.push(format!("The tutor asked you: \"{}\"; you answered: \"{reply}\"", step.instruction));
                format!("The learner answered: “{reply}”.")
            }
            (_, "stuck") if step.hint_only && !revealed => {
                // "Montre-moi": the pointer appears, no model call.
                report.reveals += 1;
                revealed = true;
                continue;
            }
            (_, "stuck") => {
                report.stuck += 1;
                "The learner says they cannot find it on the screen.".to_string()
            }
            _ => perform(&browser, &step, &decision, persona, &mut rng, &shot, report).await?,
        };
        step = advance(holo, &mut session, Some(event), &browser).await?;
        report.tutor_steps += 1;
        (pointer_override, revealed, asked_on_step) = (None, false, false);
    }

    report.tutor_done = step.kind == "done";
    let progress = session.progress();
    report.milestones_total = progress.len();
    report.milestones_done = progress.iter().filter(|m| m.status == "done").count();
    report.success = browser.lock().await.eval(&scenario.success).await? == Value::Bool(true);
    report.false_done = report.tutor_done && !report.success;
    if !session.finished {
        journal::end("sim-stopped");
    }
    if let Some(dir) = journal_dir {
        journal_stats(&dir, report);
    }
    Ok(())
}

/// The production tutor step, on the browser's screen.
async fn advance(
    holo: &Holo,
    session: &mut Session,
    event: Option<String>,
    browser: &Arc<Mutex<Browser>>,
) -> Result<Step, String> {
    let capture = || {
        let browser = browser.clone();
        async move { look(&browser).await }
    };
    agent::advance_with(holo, session, event, false, agent::STALE_AFTER, capture).await
}

/// Performs the learner's action in the browser and describes it the way
/// the real screen watcher would.
async fn perform(
    browser: &Mutex<Browser>,
    step: &Step,
    d: &learner::Decision,
    persona: &Persona,
    rng: &mut Rng,
    before: &Shot,
    report: &mut Report,
) -> Result<String, String> {
    report.learner_actions += 1;
    let (mut x, mut y) = (d.x.clamp(0.0, 1000.0), d.y.clamp(0.0, 1000.0));
    let pointing = matches!(d.action.as_str(), "click" | "type");
    if pointing && rng.chance(persona.misclick) {
        report.misclicks += 1;
        let (dx, dy) = rng.offset();
        (x, y) = ((x + dx).clamp(0.0, 1000.0), (y + dy).clamp(0.0, 1000.0));
    }
    let (mut hits, mut misses, mut clicks, mut keys, mut enter) = (0, 0, 0, 0, false);
    {
        let mut b = browser.lock().await;
        match d.action.as_str() {
            "click" => b.click(x, y).await?,
            "type" => {
                // The learner model sometimes puts the text in `keys`; a
                // diligent learner types what the tutor showed.
                let text = [d.text.as_str(), d.keys.as_str(), step.text.as_str()]
                    .into_iter()
                    .find(|t| !t.trim().is_empty())
                    .unwrap_or("");
                // Typing into the field that already has the focus (after
                // cmd+a, say) does not click first, like a real learner.
                if !b.focused_at(x, y).await? {
                    b.click(x, y).await?;
                }
                b.type_text(text).await?;
                keys = text.chars().count() as u32;
            }
            "key" if !d.keys.trim().is_empty() => {
                b.press(&d.keys).await?;
                keys = 1;
                enter = d.keys.to_lowercase().contains("enter") || d.keys.to_lowercase().contains("return");
            }
            "scroll" => b.scroll(x, y, &d.direction).await?,
            _ => {}
        }
        if pointing {
            match step.point {
                None => clicks = 1,
                Some(_) if hit(step, x, y) => hits = 1,
                Some(_) => misses = 1,
            }
        }
        b.settle().await;
    }
    let after = look(browser).await?;
    let changed = thumb_diff(&before.thumb, &after.thumb) > SCREEN_CHANGED;
    journal::event(
        "sim_action",
        serde_json::json!({ "action": d.action, "x": x, "y": y, "text": d.text, "keys": d.keys, "hit": hits > 0, "changed": changed }),
    );
    Ok(crate::watch::describe_event(hits, misses, clicks, keys, enter, changed))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scenarios_parse() {
        for e in std::fs::read_dir(sim_dir().join("scenarios")).unwrap().flatten() {
            let id = e.path().file_stem().unwrap().to_string_lossy().to_string();
            let s = Scenario::load(&id).unwrap();
            assert!(!s.goal.is_empty() && !s.success.is_empty(), "{id}");
            if !s.url.starts_with("http") {
                assert!(sim_dir().join(&s.url).exists(), "{id}: missing app {}", s.url);
            }
        }
    }

    #[test]
    fn hits_use_the_real_click_tolerance() {
        let step = Step { point: Some((500.0, 500.0)), ..Default::default() };
        assert!(hit(&step, 520.0, 510.0)); // ~29 px away
        assert!(!hit(&step, 560.0, 500.0)); // ~86 px away
    }

    /// The browser driver on the test app, without any model:
    /// `cargo test --lib sim::tests::browser_drives_the_notebook -- --ignored`
    #[test]
    #[ignore]
    fn browser_drives_the_notebook() {
        tauri::async_runtime::block_on(async {
            let s = Scenario::load("notebook-groceries").unwrap();
            let mut b = Browser::launch(&s.url()).await.unwrap();
            let first = b.screenshot().await.unwrap();
            assert!(shot_from_jpeg(&first).is_ok());
            assert_eq!(b.eval("app.notes.length").await.unwrap(), 1);
            // File menu at the top left, then "New note…".
            let file = b
                .eval("JSON.stringify(document.querySelector('.menu > button').getBoundingClientRect())")
                .await
                .unwrap();
            let r: Value = serde_json::from_str(file.as_str().unwrap()).unwrap();
            let norm = |px: f64, total: f64| px / total * 1000.0;
            b.click(
                norm(r["x"].as_f64().unwrap() + 10.0, browser::WIDTH),
                norm(r["y"].as_f64().unwrap() + 10.0, browser::HEIGHT),
            )
            .await
            .unwrap();
            b.press("cmd+n").await.unwrap();
            b.settle().await;
            assert_eq!(b.eval("document.getElementById('dialog').classList.contains('open')").await.unwrap(), true);
            b.type_text("Groceries").await.unwrap();
            b.press("enter").await.unwrap();
            b.settle().await;
            assert_eq!(b.eval("app.notes.map(n => n.name).join(',')").await.unwrap(), "Untitled,Groceries");
            b.press("cmd+i").await.unwrap();
            b.settle().await;
            b.type_text("Bread").await.unwrap();
            b.press("enter").await.unwrap();
            b.settle().await;
            assert_eq!(b.eval("app.notes[1].items[0].text").await.unwrap(), "Bread");
            assert_eq!(b.eval(&s.success).await.unwrap(), false, "not important yet");
            // Rename: the dialog is prefilled; select all, then type replaces it.
            b.eval("document.querySelector('[data-cmd=rename]').click()").await.unwrap();
            b.settle().await;
            assert!(b.focused_at(500.0, 490.0).await.unwrap(), "the dialog field has the focus");
            b.press("cmd+a").await.unwrap();
            b.type_text("Courses").await.unwrap();
            b.press("enter").await.unwrap();
            b.settle().await;
            assert_eq!(b.eval("app.notes[app.current].name").await.unwrap(), "Courses");
        });
    }

    /// Runs simulated sessions with real Holo calls (costs tokens):
    /// `SIM_SCENARIO=notebook-groceries SIM_PERSONA=novice,diligent SIM_SEEDS=1 \
    ///  cargo test --lib sim::tests::simulate -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn simulate() {
        let _ = dotenvy::from_path(concat!(env!("CARGO_MANIFEST_DIR"), "/../.env"));
        let scenario =
            Scenario::load(&std::env::var("SIM_SCENARIO").unwrap_or_else(|_| "notebook-groceries".into())).unwrap();
        let personas = std::env::var("SIM_PERSONA").unwrap_or_else(|_| "novice".into());
        let seeds: u64 = std::env::var("SIM_SEEDS").ok().and_then(|s| s.parse().ok()).unwrap_or(1);
        let holo = Holo::new();
        let mut reports = Vec::new();
        tauri::async_runtime::block_on(async {
            for id in personas.split(',').map(str::trim) {
                let persona = learner::persona(id).unwrap_or_else(|| panic!("unknown persona {id}"));
                for seed in 1..=seeds {
                    let r = run(&holo, &scenario, &persona, seed).await;
                    println!(
                        "{:<20} {:<10} seed {seed}: {}{} · milestones {}/{} · {} tutor steps · {} actions ({} misclicks) · \
                         {} questions · {} reveals · {:.0}s · {:?}",
                        r.scenario,
                        r.persona,
                        if r.success { "SUCCESS" } else { "FAIL" },
                        if r.false_done { " (FALSE DONE)" } else { "" },
                        r.milestones_done,
                        r.milestones_total,
                        r.tutor_steps,
                        r.learner_actions,
                        r.misclicks,
                        r.questions,
                        r.reveals,
                        r.wall_s,
                        r.errors,
                    );
                    reports.push(r);
                }
            }
        });
        let dir = sim_dir().join("results");
        std::fs::create_dir_all(&dir).unwrap();
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
        let path = dir.join(format!("{stamp}-{}.json", scenario.id));
        std::fs::write(&path, serde_json::to_vec_pretty(&reports).unwrap()).unwrap();
        println!("report: {}", path.display());
    }
}
