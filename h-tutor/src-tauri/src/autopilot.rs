use crate::{panel, skills};
use serde::{Deserialize, Serialize};
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
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
}

#[derive(Default)]
struct Controller {
    view: View,
    active: Option<String>,
    generation: u64,
}

impl Controller {
    fn accept(&mut self, skill: &skills::Skill, stop: &AtomicBool) -> Result<(), String> {
        if self.active.is_some() {
            return Err("Rio exécute déjà une tâche".into());
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
            label: "En attente du pilote".into(),
            ..View::default()
        };
        Ok(())
    }

    fn stop(&mut self, stop: &AtomicBool) -> Option<Done> {
        stop.store(true, Ordering::SeqCst);
        self.active.take().map(|skill_id| Done {
            skill_id,
            outcome: "stopped".into(),
            message: Some("Arrêté".into()),
        })
    }
}

static CONTROL: Mutex<Option<Controller>> = Mutex::new(None);
static STOP_REQUESTED: AtomicBool = AtomicBool::new(true);

/// Entry point for the block 3 driver: check before every action and after await.
pub fn stop_requested() -> bool {
    STOP_REQUESTED.load(Ordering::SeqCst)
}

#[derive(Clone, Serialize)]
struct Started {
    skill_id: String,
    title: String,
    total: usize,
}

#[derive(Deserialize)]
struct Progress {
    skill_id: String,
    index: usize,
    total: usize,
    label: String,
}

#[derive(Clone, Deserialize, Serialize)]
struct Done {
    skill_id: String,
    outcome: String,
    message: Option<String>,
}

fn publish(app: &AppHandle, view: &View) -> Result<(), String> {
    let window = app
        .get_webview_window("notch")
        .ok_or("Notch indisponible")?;
    if !matches!(view.phase, Phase::Hidden) {
        if !app.global_shortcut().is_registered("Escape") {
            app.global_shortcut()
                .register("Escape")
                .map_err(|e| e.to_string())?;
        }
        panel::show(&window, false, panel::LEVEL_OVERLAY);
        if let Some(monitor) = app.primary_monitor().map_err(|e| e.to_string())? {
            let scale = monitor.scale_factor();
            let origin = monitor.position().to_logical::<f64>(scale);
            let size = monitor.size().to_logical::<f64>(scale);
            window
                .set_position(tauri::LogicalPosition::new(
                    origin.x + (size.width - 460.0) / 2.0,
                    origin.y,
                ))
                .map_err(|e| e.to_string())?;
        }
    }
    app.emit_to("notch", "autopilot:view", view)
        .map_err(|e| e.to_string())
}

fn hide(app: &AppHandle, expected: Option<u64>) {
    let (view, generation) = {
        let mut guard = CONTROL.lock().unwrap();
        let control = guard.get_or_insert_with(Controller::default);
        if expected.is_some_and(|generation| generation != control.generation) {
            return;
        }
        control.generation += 1;
        control.view.phase = Phase::Hidden;
        (control.view.clone(), control.generation)
    };
    let _ = app.global_shortcut().unregister("Escape");
    let _ = publish(app, &view);
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(220));
        if let Some(window) = app.get_webview_window("notch") {
            let w = window.clone();
            let _ = window.run_on_main_thread(move || {
                let guard = CONTROL.lock().unwrap();
                if guard.as_ref().is_some_and(|c| c.generation == generation) {
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
        if expected.is_some_and(|generation| generation != control.generation) {
            return Ok(());
        }
        if !matches!(control.view.phase, Phase::Expanded) {
            return Ok(());
        }
        control.view.phase = Phase::Hidden;
        (control.view.skill_id.clone(), control.generation)
    };
    let result = skills::decline(&id);
    hide(app, Some(generation));
    result
}

pub fn propose(app: &AppHandle, proposal: skills::Proposal) {
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
            ..View::default()
        };
        (control.view.clone(), control.generation)
    };
    if let Err(error) = publish(app, &view) {
        eprintln!("Impossible d'afficher la notch : {error}");
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
    CONTROL
        .lock()
        .unwrap()
        .as_ref()
        .map(|c| c.view.clone())
        .unwrap_or_default()
}

#[tauri::command]
pub fn autopilot_decline(app: AppHandle) -> Result<(), String> {
    decline_current(&app, None)
}

#[tauri::command]
pub fn autopilot_accept(app: AppHandle, skill_id: String) -> Result<(), String> {
    let skill = skills::load(&skill_id)?;
    if !skill.runs.iter().any(|run| run.outcome == "completed") {
        return Err("Ce skill n'a pas encore réussi".into());
    }
    let state = app.state::<crate::AppState>();
    let session = state
        .session
        .try_lock()
        .map_err(|_| "Un tutoriel est en cours")?;
    if session.as_ref().is_some_and(|s| !s.finished) {
        return Err("Un tutoriel est en cours".into());
    }
    let view = {
        let mut guard = CONTROL.lock().unwrap();
        let control = guard.get_or_insert_with(Controller::default);
        control.accept(&skill, &STOP_REQUESTED)?;
        control.view.clone()
    };
    if let Err(error) = publish(&app, &view) {
        let _ = autopilot_stop(app.clone());
        return Err(error);
    }
    // Block 3 starts the driver here, passing the skill graph and stop_requested.
    app.emit(
        "autopilot:started",
        Started {
            skill_id: view.skill_id,
            title: view.title,
            total: view.total,
        },
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn autopilot_stop(app: AppHandle) -> Result<(), String> {
    let done = CONTROL
        .lock()
        .unwrap()
        .as_mut()
        .and_then(|c| c.stop(&STOP_REQUESTED));
    debug_assert!(stop_requested());
    if let Some(done) = done {
        finish(&app, &done);
        app.emit("autopilot:done", done)
            .map_err(|e| e.to_string())?;
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

fn finish(app: &AppHandle, done: &Done) {
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
        } else {
            done.message.clone().unwrap_or_else(|| {
                if done.outcome == "stopped" {
                    "Arrêté".into()
                } else {
                    "La tâche a échoué".into()
                }
            })
        });
        (control.view.clone(), control.generation)
    };
    let _ = publish(app, &view);
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(3));
        hide(&app, Some(generation));
    });
}

pub fn setup(app: &AppHandle) {
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
    let handle = app.clone();
    app.listen("autopilot:done", move |event| {
        if let Ok(done) = serde_json::from_str(event.payload()) {
            finish(&handle, &done);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn autopilot_accept_is_exclusive_and_stop_releases_lock() {
        let graph = crate::tutorial::Tutorial {
            id: "test".into(),
            ..Default::default()
        };
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
