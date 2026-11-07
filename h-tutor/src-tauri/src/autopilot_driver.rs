use crate::{agent, autopilot, journal, skills};
use std::collections::HashMap;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};

#[derive(Clone, Copy)]
struct Limits {
    per_milestone: usize,
    total: usize,
    failures: usize,
    timeout: Duration,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            per_milestone: 20,
            total: 80,
            failures: 3,
            timeout: Duration::from_secs(300),
        }
    }
}

#[derive(Debug, PartialEq)]
enum Failure {
    Stopped,
    Failed(String),
}

trait Driver {
    fn stopped(&self) -> bool;
    fn progressed(&self) -> bool {
        true
    }
    async fn advance(&mut self) -> Result<agent::Step, String>;
    async fn execute(&mut self, step: &agent::Step) -> Result<(), String>;
    async fn pause(&self);
}

fn same_action(a: &agent::Step, b: &agent::Step) -> bool {
    a.milestone.as_ref().map(|m| &m.id) == b.milestone.as_ref().map(|m| &m.id)
        && a.kind == b.kind
        && a.point == b.point
        && a.text == b.text
        && a.keys == b.keys
        && a.direction == b.direction
}

async fn drive<D: Driver>(driver: &mut D, limits: Limits) -> Result<usize, Failure> {
    let mut total = 0;
    let mut counts = HashMap::<String, usize>::new();
    let mut failures = 0;
    let mut previous = None;
    loop {
        if driver.stopped() {
            return Err(Failure::Stopped);
        }
        let result = driver.advance().await;
        if driver.stopped() {
            return Err(Failure::Stopped);
        }
        let step = match result {
            Ok(step) => step,
            Err(_) => {
                failures += 1;
                journal::event(
                    "rio_holo_failure",
                    serde_json::json!({ "consecutive": failures }),
                );
                if failures >= limits.failures {
                    return Err(Failure::Failed(
                        "Holo ne répond pas correctement après plusieurs essais".into(),
                    ));
                }
                driver.pause().await;
                continue;
            }
        };
        if step.kind == "done" && !step.unchanged {
            return Ok(total);
        }
        if step.unchanged
            || !driver.progressed()
            || previous.as_ref().is_some_and(|p| same_action(p, &step))
        {
            failures += 1;
            journal::event(
                "rio_no_progress",
                serde_json::json!({ "consecutive": failures }),
            );
            if failures >= limits.failures {
                return Err(Failure::Failed(
                    "L'écran ou le jalon ne progresse pas après les actions de Rio".into(),
                ));
            }
        } else {
            failures = 0;
        }
        if step.unchanged {
            driver.pause().await;
            continue;
        }
        if !matches!(
            step.kind.as_str(),
            "click" | "write" | "scroll" | "press_key"
        ) {
            return Err(Failure::Failed("Holo a renvoyé une action inconnue".into()));
        }
        let milestone = step
            .milestone
            .as_ref()
            .ok_or_else(|| Failure::Failed("Jalon Holo manquant".into()))?;
        let count = counts.entry(milestone.id.clone()).or_default();
        if *count >= limits.per_milestone {
            return Err(Failure::Failed(
                "Limite d'actions atteinte pour ce jalon".into(),
            ));
        }
        if total >= limits.total {
            return Err(Failure::Failed("Limite globale d'actions atteinte".into()));
        }
        if driver.stopped() {
            return Err(Failure::Stopped);
        }
        driver.execute(&step).await.map_err(Failure::Failed)?;
        total += 1;
        *count += 1;
        previous = Some(step);
    }
}

async fn bounded<D: Driver>(driver: &mut D, limits: Limits) -> Result<usize, Failure> {
    tokio::time::timeout(limits.timeout, drive(driver, limits))
        .await
        .map_err(|_| Failure::Failed("Le délai maximal d'exécution est dépassé".into()))?
}

struct LiveDriver<'a> {
    app: AppHandle,
    holo: &'a crate::holo::Holo,
    session: agent::Session,
    after_action: bool,
    actions: usize,
    progressed: bool,
    ticket: u64,
    pending: Option<agent::Step>,
}

impl Driver for LiveDriver<'_> {
    fn stopped(&self) -> bool {
        autopilot::stop_requested()
    }
    fn progressed(&self) -> bool {
        self.progressed
    }

    async fn advance(&mut self) -> Result<agent::Step, String> {
        if let Some(step) = self.pending.take() {
            return Ok(step);
        }
        let after_action = std::mem::take(&mut self.after_action);
        let before = self.session.before.as_ref().map(|s| s.thumb.clone());
        let event = after_action.then(|| {
            "Rio a exécuté l'action ; vérifie le résultat sur cette nouvelle capture".into()
        });
        let step = agent::advance(self.holo, &mut self.session, event, false).await?;
        self.progressed = !after_action
            || !step.completed.is_empty()
            || before
                .as_ref()
                .zip(self.session.before.as_ref())
                .is_none_or(|(before, after)| {
                    crate::capture::thumb_diff(before, &after.thumb) > 0.1
                });
        Ok(step)
    }

    async fn execute(&mut self, step: &agent::Step) -> Result<(), String> {
        let milestone = step.milestone.as_ref().ok_or("Jalon manquant")?;
        let graph = &self.session.tutorial;
        let index = graph
            .milestones
            .iter()
            .position(|m| m.id == milestone.id)
            .ok_or("Jalon inconnu")?
            + 1;
        self.app
            .emit(
                "autopilot:progress",
                autopilot::Progress {
                    skill_id: graph.id.clone(),
                    index,
                    total: graph.milestones.len(),
                    label: milestone.goal.clone(),
                },
            )
            .map_err(|e| e.to_string())?;
        if self.stopped() {
            return Err("Arrêt demandé".into());
        }
        journal::event(
            "rio_action",
            serde_json::json!({
                "milestone": milestone.id, "kind": step.kind, "point": step.point,
                "keys": step.keys, "direction": step.direction, "text_length": step.text.chars().count(),
            }),
        );
        self.actions += 1;
        let app = self.app.clone();
        let step = step.clone();
        let ticket = self.ticket;
        tauri::async_runtime::spawn_blocking(move || {
            let _mask = autopilot::mask_capture()?;
            crate::act::perform(&app, &step, ticket)
        })
        .await
        .map_err(|e| e.to_string())??;
        self.after_action = true;
        tokio::time::sleep(Duration::from_millis(650)).await;
        Ok(())
    }

    async fn pause(&self) {
        tokio::time::sleep(Duration::from_millis(1200)).await;
    }
}

async fn wait_stop() {
    while !autopilot::stop_requested() {
        tokio::time::sleep(Duration::from_millis(30)).await;
    }
}

pub fn spawn(app: AppHandle, skill: skills::Skill) {
    let ticket = autopilot::run_id();
    tauri::async_runtime::spawn(async move {
        let state = app.state::<crate::AppState>();
        let _session_lock = state.session.lock().await;
        let mut driver = LiveDriver {
            app: app.clone(),
            holo: &state.holo,
            session: agent::Session::new_rio(skill.graph.clone()),
            after_action: false,
            actions: 0,
            progressed: true,
            ticket,
            pending: None,
        };
        let candidate = crate::script::eligible(&skill);
        let mut run_mode = skills::Mode::Rio;
        let result = if journal::current_dir().is_none() {
            Err(Failure::Failed(
                "Impossible d'ouvrir le journal ; aucune action exécutée".into(),
            ))
        } else {
            let script_result = if let Some(ref artifact) = candidate {
                journal::set_mode("script");
                crate::script::run(artifact).await
            } else {
                Err(crate::script::Failure::NotEligible)
            };
            match script_result {
                Ok(()) => {
                    run_mode = skills::Mode::Script;
                    match driver.advance().await {
                        Ok(step) if step.kind == "done" => Ok(0),
                        Ok(step) => {
                            journal::event(
                                "script_fallback",
                                serde_json::json!({"reason":"La vérification Holo demande encore des actions"}),
                            );
                            journal::set_mode("rio");
                            run_mode = skills::Mode::Rio;
                            driver.pending = Some(step);
                            bounded(&mut driver, Limits::default()).await
                        }
                        Err(_) => {
                            journal::event(
                                "script_fallback",
                                serde_json::json!({"reason":"vérification Holo échouée"}),
                            );
                            journal::set_mode("rio");
                            run_mode = skills::Mode::Rio;
                            bounded(&mut driver, Limits::default()).await
                        }
                    }
                }
                Err(error) => {
                    journal::event(
                        "script_fallback",
                        serde_json::json!({"reason": error.to_string()}),
                    );
                    journal::set_mode("rio");
                    tokio::select! { biased; _ = wait_stop() => Err(Failure::Stopped), result = bounded(&mut driver, Limits::default()) => result }
                }
            }
        };
        let (outcome, message) = if autopilot::stop_requested() {
            ("stopped", Some("Arrêté".into()))
        } else {
            match result {
                Ok(_) => ("completed", None),
                Err(Failure::Stopped) => ("stopped", Some("Arrêté".into())),
                Err(Failure::Failed(message)) => ("failed", Some(message)),
            }
        };
        autopilot::request_stop();
        crate::act::drain().await;
        journal::event(
            "rio_done",
            serde_json::json!({ "outcome": outcome, "actions": driver.actions, "message": message }),
        );
        if let Some(run) = journal::skill_run(run_mode, outcome)
            && let Err(error) = skills::record_run(agent::to_tutorial(&driver.session), run)
        {
            journal::event("skill_record_error", serde_json::json!({ "error": error }));
        }
        journal::end(outcome);
        let done = autopilot::Done {
            skill_id: skill.tutorial_id,
            outcome: outcome.into(),
            message,
        };
        autopilot::finish(&app, &done);
        let _ = app.emit("autopilot:done", done);
        autopilot::driver_released();
    });
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::VecDeque;

    #[derive(Default)]
    struct Fake {
        steps: VecDeque<Result<agent::Step, String>>,
        executed: usize,
        stop_after: Option<usize>,
        pending: bool,
        execution_error: bool,
        no_screen_change: bool,
    }

    impl Driver for Fake {
        fn stopped(&self) -> bool {
            self.stop_after.is_some_and(|n| self.executed >= n)
        }
        fn progressed(&self) -> bool {
            !self.no_screen_change || self.executed == 0
        }
        async fn advance(&mut self) -> Result<agent::Step, String> {
            if self.pending {
                std::future::pending::<()>().await;
            }
            self.steps
                .pop_front()
                .unwrap_or_else(|| Err("Holo indisponible".into()))
        }
        async fn execute(&mut self, _: &agent::Step) -> Result<(), String> {
            if self.execution_error {
                return Err("Injection indisponible".into());
            }
            self.executed += 1;
            Ok(())
        }
        async fn pause(&self) {}
    }

    fn action(point: f64, id: &str) -> Result<agent::Step, String> {
        Ok(agent::Step {
            kind: "click".into(),
            point: Some((point, 300.0)),
            milestone: Some(agent::MilestoneView {
                id: id.into(),
                goal: "Créer un dossier".into(),
                status: "current".into(),
                ..Default::default()
            }),
            ..Default::default()
        })
    }

    fn done() -> Result<agent::Step, String> {
        Ok(agent::Step {
            kind: "done".into(),
            ..Default::default()
        })
    }

    #[tokio::test]
    async fn autopilot_driver_success_only_after_done() {
        let mut fake = Fake {
            steps: [action(100.0, "a"), action(200.0, "b"), done()].into(),
            ..Default::default()
        };
        assert_eq!(
            bounded(
                &mut fake,
                Limits {
                    per_milestone: 1,
                    ..Default::default()
                }
            )
            .await,
            Ok(2)
        );
        assert_eq!(fake.executed, 2);
        let mut already_done = Fake {
            steps: [done()].into(),
            ..Default::default()
        };
        assert_eq!(bounded(&mut already_done, Limits::default()).await, Ok(0));
    }

    #[tokio::test]
    async fn autopilot_driver_stops_during_run() {
        let mut fake = Fake {
            steps: [action(100.0, "a"), action(200.0, "a"), done()].into(),
            stop_after: Some(1),
            ..Default::default()
        };
        assert_eq!(
            bounded(&mut fake, Limits::default()).await,
            Err(Failure::Stopped)
        );
        assert_eq!(fake.executed, 1);
    }

    #[tokio::test]
    async fn autopilot_driver_caps_milestone_and_global_actions() {
        for (per_milestone, total, expected) in [(1, 20, "ce jalon"), (20, 1, "globale")] {
            let mut fake = Fake {
                steps: [action(100.0, "a"), action(200.0, "a"), done()].into(),
                ..Default::default()
            };
            let result = bounded(
                &mut fake,
                Limits {
                    per_milestone,
                    total,
                    ..Default::default()
                },
            )
            .await;
            assert!(matches!(result, Err(Failure::Failed(message)) if message.contains(expected)));
            assert_eq!(fake.executed, 1);
        }
    }

    #[tokio::test]
    async fn autopilot_driver_fails_without_progress() {
        let mut fake = Fake {
            steps: [
                action(100.0, "a"),
                action(100.0, "a"),
                action(100.0, "a"),
                action(100.0, "a"),
                done(),
            ]
            .into(),
            ..Default::default()
        };
        assert!(
            matches!(bounded(&mut fake, Limits::default()).await, Err(Failure::Failed(message)) if message.contains("ne progresse pas"))
        );
        let mut unchanged = action(200.0, "a").unwrap();
        unchanged.unchanged = true;
        let mut fake = Fake {
            steps: [
                action(100.0, "a"),
                Ok(unchanged.clone()),
                Ok(unchanged.clone()),
                Ok(unchanged),
                done(),
            ]
            .into(),
            ..Default::default()
        };
        assert!(matches!(
            bounded(&mut fake, Limits::default()).await,
            Err(Failure::Failed(_))
        ));
        assert_eq!(fake.executed, 1);
    }

    #[tokio::test]
    async fn autopilot_driver_errors_empty_unknown_and_timeout() {
        let mut empty = Fake::default();
        assert!(
            matches!(bounded(&mut empty, Limits::default()).await, Err(Failure::Failed(message)) if message.contains("Holo"))
        );
        assert_eq!(empty.executed, 0);
        let mut recover = Fake {
            steps: [
                Err("Échec temporaire".into()),
                action(100.0, "a"),
                Err("Échec temporaire".into()),
                action(200.0, "a"),
                done(),
            ]
            .into(),
            ..Default::default()
        };
        assert_eq!(bounded(&mut recover, Limits::default()).await, Ok(2));
        let mut injection = Fake {
            steps: [action(100.0, "a"), done()].into(),
            execution_error: true,
            ..Default::default()
        };
        assert_eq!(
            bounded(&mut injection, Limits::default()).await,
            Err(Failure::Failed("Injection indisponible".into()))
        );
        let mut missing = action(100.0, "a").unwrap();
        missing.milestone = None;
        let mut fake = Fake {
            steps: [Ok(missing)].into(),
            ..Default::default()
        };
        assert!(
            matches!(bounded(&mut fake, Limits::default()).await, Err(Failure::Failed(message)) if message.contains("manquant"))
        );
        let mut unknown = Fake {
            steps: [Ok(agent::Step::default())].into(),
            ..Default::default()
        };
        assert!(
            matches!(bounded(&mut unknown, Limits::default()).await, Err(Failure::Failed(message)) if message.contains("inconnue"))
        );
        let mut pending = Fake {
            pending: true,
            ..Default::default()
        };
        assert!(
            matches!(bounded(&mut pending, Limits { timeout: Duration::from_millis(1), ..Default::default() }).await, Err(Failure::Failed(message)) if message.contains("délai"))
        );
    }

    #[tokio::test]
    async fn autopilot_driver_unchanged_screen_counts_as_failure_with_different_actions() {
        let mut fake = Fake {
            steps: [
                action(100.0, "a"),
                action(200.0, "a"),
                action(300.0, "a"),
                action(400.0, "a"),
                done(),
            ]
            .into(),
            no_screen_change: true,
            ..Default::default()
        };
        assert!(
            matches!(bounded(&mut fake, Limits::default()).await, Err(Failure::Failed(message)) if message.contains("ne progresse pas"))
        );
        assert_eq!(fake.executed, 3);
    }
}
