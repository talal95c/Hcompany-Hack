//! Autopilot benchmark: Rio's own autopilot loop (`autopilot_driver::bounded`,
//! same limits as the app) runs a tutorial by itself in the headless browser,
//! and the result is graded by the scenario's JavaScript check.
//!
//! Only the hands and the screen are simulated: actions are performed in
//! Chrome with the same semantics as `act.rs` (a write is a click then the
//! text, no Enter), and the acceptance check reads the browser's screen.
//!
//! `SIM_SCENARIO=notebook-journal SIM_RUNS=2 \
//!  cargo test --lib sim::autopilot::tests::bench_autopilot -- --ignored --nocapture`

use super::browser::Browser;
use super::{Scenario, sim_dir};
use crate::agent::{self, Session, Step};
use crate::autopilot_driver::{Driver, Failure, Limits, bounded, progressed_after, selects_all};
use crate::capture::{Shot, shot_from_jpeg, thumb_diff};
use crate::holo::Holo;
use crate::journal;
use image::GrayImage;
use serde::Serialize;
use serde_json::Value;
use std::sync::{Arc, Mutex as StdMutex};
use std::time::Duration;
use tokio::sync::Mutex;

/// The browser screen Rio's acceptance check must read (instead of the desktop).
static SCREEN: StdMutex<Option<(String, GrayImage)>> = StdMutex::new(None);

/// The screen of the running benchmark, if any.
pub fn screen() -> Option<Shot> {
    SCREEN.lock().unwrap().as_ref().map(|(data_uri, thumb)| Shot { data_uri: data_uri.clone(), thumb: thumb.clone() })
}

async fn look(browser: &Mutex<Browser>) -> Result<Shot, String> {
    let jpeg = browser.lock().await.screenshot().await?;
    let shot = shot_from_jpeg(&jpeg)?;
    *SCREEN.lock().unwrap() = Some((shot.data_uri.clone(), shot.thumb.clone()));
    Ok(shot)
}

struct SimDriver<'a> {
    holo: &'a Holo,
    session: Session,
    browser: Arc<Mutex<Browser>>,
    after_action: bool,
    progressed: bool,
    pending: Option<Step>,
    actions: usize,
    last: Option<Step>,
}

impl Driver for SimDriver<'_> {
    fn stopped(&self) -> bool {
        false
    }
    fn replay(&mut self, step: Step) {
        self.pending = Some(step);
    }
    fn progressed(&self) -> bool {
        self.progressed
    }

    /// Same as the app's `LiveDriver::advance`, on the browser's screen.
    async fn advance(&mut self) -> Result<Step, String> {
        if let Some(step) = self.pending.take() {
            return Ok(step);
        }
        let after_action = std::mem::take(&mut self.after_action);
        let before = self.session.before.as_ref().map(|s| s.thumb.clone());
        let event = after_action.then(|| "Rio ran the action; check the result on this new screenshot".to_string());
        let browser = self.browser.clone();
        let capture = || {
            let browser = browser.clone();
            async move { look(&browser).await }
        };
        let step = agent::advance_with(self.holo, &mut self.session, event, false, agent::STALE_AFTER, capture).await?;
        let moved = before
            .as_ref()
            .zip(self.session.before.as_ref())
            .is_none_or(|(before, after)| thumb_diff(before, &after.thumb) > 0.1);
        self.progressed = progressed_after(
            after_action,
            !step.completed.is_empty(),
            moved,
            self.last.as_ref().map(|s| s.kind.as_str()),
        );
        Ok(step)
    }

    /// Same semantics as `act::perform`.
    async fn execute(&mut self, step: &Step) -> Result<(), String> {
        journal::event(
            "rio_action",
            serde_json::json!({ "kind": step.kind, "point": step.point, "keys": step.keys,
                                "direction": step.direction, "text_length": step.text.chars().count() }),
        );
        {
            let mut b = self.browser.lock().await;
            match step.kind.as_str() {
                "click" => {
                    let (x, y) = step.point.ok_or("Holo's action has no point")?;
                    b.click(x, y).await?;
                }
                "write" => {
                    let (x, y) = step.point.ok_or("Holo's action has no point")?;
                    if step.text.is_empty() || step.text.chars().count() > 512 || step.text.contains(['\n', '\r']) {
                        return Err("Empty, too long or multi-line text refused".into());
                    }
                    // As act.rs: no click right after a select-all.
                    if !self.last.as_ref().is_some_and(|p| p.kind == "press_key" && selects_all(&p.keys)) {
                        b.click(x, y).await?;
                    }
                    b.type_text(&step.text).await?;
                }
                "scroll" => {
                    let (x, y) = step.point.ok_or("Holo's action has no point")?;
                    b.scroll(x, y, &step.direction).await?;
                }
                "press_key" => b.press(&step.keys).await?,
                other => return Err(format!("Unsupported action {other}")),
            }
        }
        self.actions += 1;
        self.last = Some(step.clone());
        self.after_action = true;
        tokio::time::sleep(Duration::from_millis(650)).await;
        Ok(())
    }

    async fn pause(&self) {
        tokio::time::sleep(Duration::from_millis(1200)).await;
    }
}

#[derive(Serialize, Default, Debug)]
pub struct AutopilotReport {
    pub scenario: String,
    pub run: u64,
    /// The scenario's check passed: the task is really done.
    pub success: bool,
    /// The autopilot reported done ("Fait ✓").
    pub rio_done: bool,
    /// Rio said done but the check failed: the worst outcome.
    pub false_done: bool,
    /// Why the autopilot stopped, when it did not finish.
    pub failure: Option<String>,
    pub milestones_total: usize,
    pub milestones_done: usize,
    pub actions: usize,
    pub checks_passed: usize,
    pub checks_refused: usize,
    pub no_progress: usize,
    pub holo_requests: u64,
    pub prompt_tokens: u64,
    pub wall_s: f64,
    pub session: Option<String>,
}

pub async fn run(holo: &Holo, scenario: &Scenario, run: u64) -> AutopilotReport {
    let started = std::time::Instant::now();
    let mut report = AutopilotReport { scenario: scenario.id.clone(), run, ..Default::default() };
    if let Err(e) = drive(holo, scenario, &mut report).await {
        report.failure.get_or_insert(e);
        journal::end("sim-error");
    }
    *SCREEN.lock().unwrap() = None;
    report.wall_s = (started.elapsed().as_secs_f64() * 10.0).round() / 10.0;
    report
}

async fn drive(holo: &Holo, scenario: &Scenario, report: &mut AutopilotReport) -> Result<(), String> {
    let browser = Arc::new(Mutex::new(Browser::launch(&scenario.url()).await?));
    let tutorial = match &scenario.tutorial {
        Some(t) => t.clone(),
        None => crate::planner::plan(holo, &scenario.goal, &look(&browser).await?, None).await?,
    };
    let session = Session::new_rio(tutorial);
    let journal_dir = journal::current_dir();
    report.session = journal_dir.as_ref().map(|d| d.display().to_string());
    journal::event(
        "sim_start",
        serde_json::json!({ "scenario": scenario.id, "app": scenario.app, "persona": "rio-autopilot" }),
    );

    let mut driver = SimDriver {
        holo,
        session,
        browser: browser.clone(),
        after_action: false,
        progressed: true,
        pending: None,
        actions: 0,
        last: None,
    };
    // The app's own loop and limits.
    let outcome = bounded(&mut driver, Limits::default()).await;
    report.rio_done = outcome.is_ok();
    if let Err(f) = &outcome {
        report.failure = Some(match f {
            Failure::Stopped => "stopped".into(),
            Failure::Failed(e) => e.clone(),
        });
    }
    report.actions = driver.actions;
    let progress = driver.session.progress();
    report.milestones_total = progress.len();
    report.milestones_done = progress.iter().filter(|m| m.status == "done").count();
    report.success = browser.lock().await.eval(&scenario.success).await? == Value::Bool(true);
    report.false_done = report.rio_done && !report.success;
    if !driver.session.finished {
        journal::end("sim-stopped");
    }
    if let Some(dir) = journal_dir
        && let Ok(text) = std::fs::read_to_string(dir.join("events.jsonl"))
    {
        for e in text.lines().filter_map(|l| serde_json::from_str::<Value>(l).ok()) {
            let n = |v: &Value| v.as_u64().unwrap_or(0);
            match e["type"].as_str() {
                Some("step") => {
                    report.holo_requests += n(&e["requests"]);
                    report.prompt_tokens += n(&e["tokens"]["prompt"]);
                }
                Some("milestone_check") => report.holo_requests += 1,
                Some("milestone_check_failed") => report.checks_refused += 1,
                Some("milestone_done") => report.checks_passed += 1,
                Some("rio_no_progress") => report.no_progress += 1,
                _ => {}
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Rio's autopilot on the simulator scenarios (real Holo calls, costs tokens):
    /// `SIM_SCENARIO=notebook-journal SIM_RUNS=2 \
    ///  cargo test --lib sim::autopilot::tests::bench_autopilot -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn bench_autopilot() {
        let _ = dotenvy::from_path(concat!(env!("CARGO_MANIFEST_DIR"), "/../.env"));
        let scenarios = std::env::var("SIM_SCENARIO").unwrap_or_else(|_| "notebook-journal".into());
        let runs: u64 = std::env::var("SIM_RUNS").ok().and_then(|s| s.parse().ok()).unwrap_or(1);
        let holo = Holo::new();
        let mut reports = Vec::new();
        tauri::async_runtime::block_on(async {
            for id in scenarios.split(',').map(str::trim) {
                let scenario = Scenario::load(id).unwrap();
                for run in 1..=runs {
                    let r = super::run(&holo, &scenario, run).await;
                    println!(
                        "{:<20} autopilot run {run}: {}{} · milestones {}/{} · {} actions · checks {} ok / {} refused · \
                         {} no-progress · {} req · {:.0}s · {}",
                        r.scenario,
                        if r.success { "SUCCESS" } else { "FAIL" },
                        if r.false_done { " (FALSE DONE)" } else { "" },
                        r.milestones_done,
                        r.milestones_total,
                        r.actions,
                        r.checks_passed,
                        r.checks_refused,
                        r.no_progress,
                        r.holo_requests,
                        r.wall_s,
                        r.failure.as_deref().unwrap_or("-"),
                    );
                    reports.push(r);
                }
            }
        });
        let dir = sim_dir().join("results");
        std::fs::create_dir_all(&dir).unwrap();
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs();
        let path = dir.join(format!("{stamp}-autopilot.json"));
        std::fs::write(&path, serde_json::to_vec_pretty(&reports).unwrap()).unwrap();
        println!("report: {}", path.display());
    }
}
