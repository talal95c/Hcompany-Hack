use crate::{panel, skills};
use serde::{Deserialize, Serialize};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::Duration;
use tauri::{AppHandle, Emitter, Listener, Manager};
use tauri_plugin_global_shortcut::GlobalShortcutExt;

#[derive(Clone, Default, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Phase {
    #[default]
    Hidden,
    Expanded,
    Compact,
}

#[derive(Clone, Default, Serialize)]
pub struct View {
    pub phase: Phase,
    pub skill_id: String,
    pub title: String,
    pub goal: String,
    pub index: usize,
    pub total: usize,
    pub label: String,
    pub outcome: Option<String>,
    pub message: Option<String>,
    pub mode: String,
}

#[derive(Default)]
struct Controller {
    view: View,
    active: Option<String>,
    generation: u64,
    declining: bool,
}

impl Controller {
    fn accept(&mut self, skill: &skills::Skill, stop: &AtomicBool) -> Result<(), String> {
        if self.active.is_some() || self.declining {
            return Err("Rio is already running a task".into());
        }
        stop.store(false, Ordering::SeqCst);
        self.active = Some(skill.tutorial_id.clone());
        self.generation += 1;
        self.view = View {
            phase: Phase::Compact,
            skill_id: skill.tutorial_id.clone(),
            title: skill.title.clone(),
            goal: skill.goal.clone(),
            total: skill.graph.milestones.len(),
            label: "Watching the screen".into(),
            mode: crate::devin::mode(skill).into(),
            ..View::default()
        };
        Ok(())
    }

    fn stop(&mut self, stop: &AtomicBool) -> Option<Done> {
        stop.store(true, Ordering::SeqCst);
        self.active.take().map(|skill_id| Done { skill_id, outcome: "stopped".into(), message: Some("Stopped".into()) })
    }

    fn begin_decline(&mut self, expected: Option<u64>) -> Option<(String, u64)> {
        if self.declining
            || expected.is_some_and(|generation| generation != self.generation)
            || !matches!(self.view.phase, Phase::Expanded)
        {
            return None;
        }
        self.declining = true;
        Some((self.view.skill_id.clone(), self.generation))
    }
}

pub(crate) fn dispatch_shortcut(action: impl FnOnce() + Send + 'static) {
    std::thread::spawn(action);
}

static CONTROL: Mutex<Option<Controller>> = Mutex::new(None);
static STOP_REQUESTED: AtomicBool = AtomicBool::new(true);
static RUNNING: AtomicBool = AtomicBool::new(false);
static CAPTURING: AtomicBool = AtomicBool::new(false);
static APP: OnceLock<AppHandle> = OnceLock::new();
static VISIBILITY_LOCK: Mutex<()> = Mutex::new(());
static RUN_ID: AtomicU64 = AtomicU64::new(0);
static IGNORE_CURSOR: AtomicBool = AtomicBool::new(false);
static SURFACE: Mutex<Surface> = Mutex::new(Surface { x: 192.0, y: 8.0, width: 136.0, height: 32.0, radius: 16.0 });

#[derive(Clone, Copy, Deserialize)]
pub struct Surface {
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    radius: f64,
}

impl Surface {
    fn valid(&self) -> bool {
        [self.x, self.y, self.width, self.height, self.radius].iter().all(|v| v.is_finite())
            && self.x >= 0.0
            && self.y >= 0.0
            && self.width > 0.0
            && self.height > 0.0
            && self.x + self.width <= 520.0
            && self.y + self.height <= 240.0
            && self.radius >= 0.0
    }

    fn contains(&self, x: f64, y: f64) -> bool {
        if x < self.x || y < self.y || x > self.x + self.width || y > self.y + self.height {
            return false;
        }
        let radius = self.radius.min(self.width / 2.0).min(self.height / 2.0);
        let cx = x.clamp(self.x + radius, self.x + self.width - radius);
        let cy = y.clamp(self.y + radius, self.y + self.height - radius);
        (x - cx).hypot(y - cy) <= radius
    }
}

#[tauri::command]
pub fn notch_surface(window: tauri::WebviewWindow, surface: Surface) -> Result<(), String> {
    if window.label() != "notch" || !surface.valid() {
        return Err("Surface de notch invalide".into());
    }
    *SURFACE.lock().unwrap() = surface;
    Ok(())
}

pub fn stop_requested() -> bool {
    STOP_REQUESTED.load(Ordering::SeqCst)
}

pub(crate) fn request_stop() {
    STOP_REQUESTED.store(true, Ordering::SeqCst);
}

pub fn is_running() -> bool {
    RUNNING.load(Ordering::SeqCst)
}

pub(crate) fn run_id() -> u64 {
    RUN_ID.load(Ordering::SeqCst)
}

pub(crate) fn driver_released() {
    RUNNING.store(false, Ordering::SeqCst);
}

#[derive(Clone, Serialize)]
struct Started {
    skill_id: String,
    title: String,
    total: usize,
}

#[derive(Clone, Deserialize, Serialize)]
pub(crate) struct Progress {
    pub skill_id: String,
    pub index: usize,
    pub total: usize,
    pub label: String,
}

#[derive(Clone, Deserialize, Serialize)]
pub(crate) struct Done {
    pub skill_id: String,
    pub outcome: String,
    pub message: Option<String>,
}

fn publish(app: &AppHandle, view: &View) -> Result<(), String> {
    let window = app.get_webview_window("notch").ok_or("Notch indisponible")?;
    if !matches!(view.phase, Phase::Hidden) {
        if !app.global_shortcut().is_registered("Escape") {
            app.global_shortcut().register("Escape").map_err(|e| e.to_string())?;
        }
        let notch = window.clone();
        app.run_on_main_thread(move || {
            if !CAPTURING.load(Ordering::SeqCst) && !matches!(autopilot_view().phase, Phase::Hidden) {
                panel::show(&notch, false, panel::LEVEL_OVERLAY);
            }
        })
        .map_err(|e| e.to_string())?;
        if let Some(monitor) = app.primary_monitor().map_err(|e| e.to_string())? {
            let scale = monitor.scale_factor();
            let origin = monitor.position().to_logical::<f64>(scale);
            let size = monitor.size().to_logical::<f64>(scale);
            window
                .set_position(tauri::LogicalPosition::new(origin.x + (size.width - 520.0) / 2.0, origin.y))
                .map_err(|e| e.to_string())?;
        }
    }
    app.emit_to("notch", "autopilot:view", view).map_err(|e| e.to_string())
}

fn hide(app: &AppHandle, expected: Option<u64>) {
    let (view, generation) = {
        let mut guard = CONTROL.lock().unwrap();
        let control = guard.get_or_insert_with(Controller::default);
        if expected.is_some_and(|generation| generation != control.generation) {
            return;
        }
        control.generation += 1;
        control.declining = false;
        control.view.phase = Phase::Hidden;
        (control.view.clone(), control.generation)
    };
    let _ = app.global_shortcut().unregister("Escape");
    let _ = publish(app, &view);
    if let Some(window) = app.get_webview_window("notch")
        && window.is_visible().unwrap_or(false)
    {
        let _ = window.set_ignore_cursor_events(true);
        IGNORE_CURSOR.store(true, Ordering::SeqCst);
    }
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(650));
        if let Some(window) = app.get_webview_window("notch") {
            let w = window.clone();
            let _ = window.run_on_main_thread(move || {
                let current = CONTROL.lock().unwrap().as_ref().is_some_and(|c| c.generation == generation);
                if current {
                    let _ = w.hide();
                }
            });
        }
    });
}

fn decline_current(app: &AppHandle, expected: Option<u64>) -> Result<(), String> {
    let (id, generation) = {
        let mut guard = CONTROL.lock().unwrap();
        let Some(control) = guard.as_mut() else {
            return Ok(());
        };
        let Some(decline) = control.begin_decline(expected) else { return Ok(()) };
        decline
    };
    let result = skills::decline(&id);
    hide(app, Some(generation));
    result
}

pub fn propose(app: &AppHandle, proposal: skills::Proposal) {
    if is_running() {
        return;
    }
    let (view, generation) = {
        let mut guard = CONTROL.lock().unwrap();
        let control = guard.get_or_insert_with(Controller::default);
        if control.active.is_some() || !matches!(control.view.phase, Phase::Hidden) {
            return;
        }
        control.generation += 1;
        control.view = View {
            phase: Phase::Expanded,
            skill_id: proposal.skill_id,
            title: proposal.title,
            goal: proposal.goal,
            mode: proposal.mode,
            ..View::default()
        };
        (control.view.clone(), control.generation)
    };
    if let Err(error) = publish(app, &view) {
        eprintln!("Could not show the notch: {error}");
        hide(app, Some(generation));
        return;
    }
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(15));
        let _ = decline_current(&app, Some(generation));
    });
}

#[tauri::command]
pub fn autopilot_view() -> View {
    CONTROL.lock().unwrap().as_ref().map(|c| c.view.clone()).unwrap_or_default()
}

#[tauri::command]
pub fn autopilot_decline(app: AppHandle) -> Result<(), String> {
    decline_current(&app, None)
}

#[tauri::command]
pub fn autopilot_accept(app: AppHandle, skill_id: String) -> Result<(), String> {
    if is_running() {
        return Err("Rio is already finishing a task".into());
    }
    let skill = skills::load(&skill_id)?;
    if skill.graph.milestones.is_empty() {
        return Err("This skill has no milestones".into());
    }
    skill.graph.validate().map_err(|e| format!("Graphe de skill invalide : {e}"))?;
    if !skill.runs.iter().any(|run| run.outcome == "completed") {
        return Err("This skill has not succeeded yet".into());
    }
    let state = app.state::<crate::AppState>();
    let session = state.session.try_lock().map_err(|_| "A tutorial is in progress")?;
    if session.as_ref().is_some_and(|s| !s.finished) {
        return Err("A tutorial is in progress".into());
    }
    if is_running() {
        return Err("Rio is already finishing a task".into());
    }
    let view = {
        let mut guard = CONTROL.lock().unwrap();
        let control = guard.get_or_insert_with(Controller::default);
        control.accept(&skill, &STOP_REQUESTED)?;
        RUN_ID.fetch_add(1, Ordering::SeqCst);
        RUNNING.store(true, Ordering::SeqCst);
        control.view.clone()
    };
    if let Err(error) = publish(&app, &view) {
        let _ = autopilot_stop(app.clone());
        driver_released();
        return Err(error);
    }
    if let Err(error) =
        app.emit("autopilot:started", Started { skill_id: view.skill_id, title: view.title, total: view.total })
    {
        let _ = autopilot_stop(app.clone());
        driver_released();
        return Err(error.to_string());
    }
    crate::watch::disarm();
    crate::set_overlay_visible(&app, false);
    drop(session);
    crate::autopilot_driver::spawn(app.clone(), skill);
    Ok(())
}

#[tauri::command]
pub fn autopilot_stop(app: AppHandle) -> Result<(), String> {
    let done = CONTROL.lock().unwrap().as_mut().and_then(|c| c.stop(&STOP_REQUESTED));
    debug_assert!(stop_requested());
    if let Some(done) = done {
        finish(&app, &done);
        app.emit("autopilot:done", done).map_err(|e| e.to_string())?;
    }
    Ok(())
}

pub fn escape(app: &AppHandle) {
    if matches!(autopilot_view().phase, Phase::Expanded) {
        let _ = decline_current(app, None);
    } else {
        let _ = autopilot_stop(app.clone());
    }
}

pub(crate) fn failure_message(label: &str) -> String {
    let label = label.split_whitespace().collect::<Vec<_>>().join(" ");
    let short: String = label.chars().take(32).collect();
    let short = if label.chars().count() > 32 {
        short.rsplit_once(' ').map_or(short.as_str(), |(words, _)| words)
    } else {
        &short
    };
    if short.is_empty() { "Step blocked".into() } else { format!("Step blocked: {short}") }
}

fn result_duration(outcome: &str) -> Duration {
    Duration::from_secs(if outcome == "failed" { 6 } else { 3 })
}

pub(crate) fn finish(app: &AppHandle, done: &Done) {
    if !matches!(done.outcome.as_str(), "completed" | "failed" | "stopped") {
        return;
    }
    let (view, generation) = {
        let mut guard = CONTROL.lock().unwrap();
        let Some(control) = guard.as_mut() else {
            return;
        };
        if control.view.skill_id != done.skill_id
            || control.view.outcome.is_some()
            || !matches!(control.view.phase, Phase::Compact)
        {
            return;
        }
        control.active = None;
        STOP_REQUESTED.store(true, Ordering::SeqCst);
        control.generation += 1;
        control.view.outcome = Some(done.outcome.clone());
        control.view.message = Some(if done.outcome == "completed" {
            "Fait ✓".into()
        } else if done.outcome == "failed" {
            failure_message(&control.view.label)
        } else {
            done.message
                .clone()
                .unwrap_or_else(|| if done.outcome == "stopped" { "Stopped".into() } else { "The task failed".into() })
        });
        (control.view.clone(), control.generation)
    };
    let _ = publish(app, &view);
    let duration = result_duration(&done.outcome);
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(duration);
        hide(&app, Some(generation));
    });
}

pub fn setup(app: &AppHandle) {
    let _ = APP.set(app.clone());
    let pointer_app = app.clone();
    tauri::async_runtime::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_millis(32)).await;
            if matches!(autopilot_view().phase, Phase::Hidden) || CAPTURING.load(Ordering::SeqCst) {
                continue;
            }
            let handle = pointer_app.clone();
            let _ = pointer_app.run_on_main_thread(move || {
                let Some(window) = handle.get_webview_window("notch") else {
                    return;
                };
                if matches!(autopilot_view().phase, Phase::Hidden)
                    || CAPTURING.load(Ordering::SeqCst)
                    || !window.is_visible().unwrap_or(false)
                {
                    return;
                }
                if let (Ok(cursor), Ok(origin), Ok(scale)) =
                    (window.cursor_position(), window.inner_position(), window.scale_factor())
                {
                    let inside = SURFACE
                        .lock()
                        .unwrap()
                        .contains((cursor.x - f64::from(origin.x)) / scale, (cursor.y - f64::from(origin.y)) / scale);
                    let ignore = !inside;
                    if IGNORE_CURSOR.swap(ignore, Ordering::SeqCst) != ignore {
                        let _ = window.set_ignore_cursor_events(ignore);
                    }
                }
            });
        }
    });
    let handle = app.clone();
    app.listen("autopilot:propose", move |event| {
        if let Ok(proposal) = serde_json::from_str(event.payload()) {
            propose(&handle, proposal);
        }
    });
    let handle = app.clone();
    app.listen("autopilot:progress", move |event| {
        let Ok(progress) = serde_json::from_str::<Progress>(event.payload()) else {
            return;
        };
        let view = {
            let mut guard = CONTROL.lock().unwrap();
            let Some(control) = guard.as_mut() else {
                return;
            };
            if control.active.as_deref() != Some(&progress.skill_id)
                || progress.total == 0
                || progress.index > progress.total
            {
                return;
            }
            control.view.index = progress.index;
            control.view.total = progress.total;
            control.view.label = progress.label;
            control.view.clone()
        };
        let _ = publish(&handle, &view);
    });
}

pub struct CaptureMask {
    app: AppHandle,
    _lock: std::sync::MutexGuard<'static, ()>,
}

pub fn mask_capture() -> Result<Option<CaptureMask>, String> {
    if !is_running() {
        return Ok(None);
    }
    let lock = VISIBILITY_LOCK.lock().map_err(|_| "Hiding lock unavailable")?;
    let app = APP.get().ok_or("Protection des captures indisponible")?.clone();
    CAPTURING.store(true, Ordering::SeqCst);
    let guard = CaptureMask { app: app.clone(), _lock: lock };
    let (send, receive) = std::sync::mpsc::sync_channel(1);
    let handle = app.clone();
    app.run_on_main_thread(move || {
        let result = (|| {
            for label in ["main", "overlay", "notch"] {
                if let Some(window) = handle.get_webview_window(label) {
                    window.hide().map_err(|e| format!("Could not hide Rio: {e}"))?;
                }
            }
            Ok::<_, String>(())
        })();
        let _ = send.send(result);
    })
    .map_err(|e| e.to_string())?;
    receive.recv_timeout(Duration::from_secs(2)).map_err(|_| "Hiding Rio's windows timed out")??;
    std::thread::sleep(Duration::from_millis(120));
    Ok(Some(guard))
}

impl Drop for CaptureMask {
    fn drop(&mut self) {
        CAPTURING.store(false, Ordering::SeqCst);
        let app = self.app.clone();
        let handle = app.clone();
        let _ = app.run_on_main_thread(move || {
            if !CAPTURING.load(Ordering::SeqCst) {
                let view = autopilot_view();
                if !matches!(view.phase, Phase::Hidden) {
                    let _ = publish(&handle, &view);
                }
            }
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn autopilot_failure_messages_are_short_and_failures_stay_longer() {
        assert_eq!(failure_message("Créer le projet"), "Step blocked: Créer le projet");
        assert_eq!(failure_message("  \n "), "Step blocked");
        assert_eq!(failure_message("Créer   le\nprojet"), "Step blocked: Créer le projet");
        let long = failure_message("Créer le projet avec un bouton désactivé et un service indisponible");
        assert_eq!(long, "Step blocked: Créer le projet avec un bouton");
        assert!(!long.contains('…'));
        assert_eq!(failure_message(&"é".repeat(80)).chars().count(), "Step blocked: ".chars().count() + 32);
        assert_eq!(result_duration("failed"), Duration::from_secs(6));
        assert_eq!(result_duration("completed"), Duration::from_secs(3));
        assert_eq!(result_duration("stopped"), Duration::from_secs(3));
    }

    #[test]
    fn autopilot_decline_is_idempotent_across_timeout_and_escape() {
        let mut controller = Controller {
            view: View { phase: Phase::Expanded, skill_id: "test".into(), ..Default::default() },
            generation: 7,
            ..Default::default()
        };
        assert!(controller.begin_decline(Some(6)).is_none());
        assert_eq!(controller.begin_decline(Some(7)), Some(("test".into(), 7)));
        assert!(controller.begin_decline(None).is_none());
        assert!(controller.begin_decline(Some(7)).is_none());
        assert!(matches!(controller.view.phase, Phase::Expanded));
        controller.declining = false;
        controller.view.phase = Phase::Hidden;
        controller.generation += 1;
        assert!(controller.begin_decline(None).is_none());
        controller.view.phase = Phase::Expanded;
        assert!(controller.begin_decline(Some(7)).is_none());
        assert!(controller.begin_decline(Some(8)).is_some());
    }

    #[test]
    fn autopilot_shortcut_callback_returns_before_unregister_waits_for_its_event_thread() {
        let (request, requests) = std::sync::mpsc::channel();
        let (reply, replies) = std::sync::mpsc::channel();
        let (done, completion) = std::sync::mpsc::channel();
        let event_thread = std::thread::spawn(move || {
            dispatch_shortcut(move || {
                request.send(()).unwrap();
                replies.recv_timeout(Duration::from_secs(2)).unwrap();
                done.send(()).unwrap();
            });
            requests.recv_timeout(Duration::from_secs(2)).unwrap();
            reply.send(()).unwrap();
        });
        completion.recv_timeout(Duration::from_secs(3)).unwrap();
        event_thread.join().unwrap();
    }

    #[test]
    fn autopilot_surface_leaves_transparent_margins_and_corners_click_through() {
        let surface = Surface { x: 20.0, y: 8.0, width: 480.0, height: 180.0, radius: 20.0 };
        assert!(surface.valid());
        assert!(surface.contains(260.0, 90.0));
        assert!(!surface.contains(10.0, 90.0));
        assert!(!surface.contains(20.0, 8.0));
        assert!(!surface.contains(260.0, 200.0));
        assert!(!Surface { width: 0.0, ..surface }.valid());
        assert!(!Surface { x: f64::NAN, ..surface }.valid());
        assert!(!Surface { width: 600.0, ..surface }.valid());
    }

    #[test]
    fn autopilot_accept_is_exclusive_and_stop_releases_lock() {
        let graph = crate::tutorial::Tutorial { id: "test".into(), ..Default::default() };
        let skill = skills::Skill {
            tutorial_id: graph.id.clone(),
            title: "Créer un dossier".into(),
            goal: "Créer".into(),
            app: graph.app.clone(),
            graph,
            runs: Vec::new(),
            compiled: Vec::new(),
            muted_until: None,
            declines: 0,
        };
        let mut controller = Controller::default();
        let stop = AtomicBool::new(true);
        assert!(controller.stop(&stop).is_none());
        controller.accept(&skill, &stop).unwrap();
        assert!(!stop.load(Ordering::SeqCst));
        assert!(matches!(controller.view.phase, Phase::Compact));
        assert!(controller.accept(&skill, &stop).is_err());
        assert_eq!(controller.stop(&stop).unwrap().outcome, "stopped");
        assert!(stop.load(Ordering::SeqCst));
        assert!(controller.active.is_none());
        controller.accept(&skill, &stop).unwrap();
        assert!(!stop.load(Ordering::SeqCst));
    }
}
