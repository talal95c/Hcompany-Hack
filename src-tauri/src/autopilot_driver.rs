use crate::{agent, autopilot, journal, skills};
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager};

#[derive(Clone, Copy)]
pub(crate) struct Limits {
    per_milestone: usize,
    total: usize,
    /// Consecutive Holo errors before giving up.
    failures: usize,
    /// Consecutive actions without visible progress before giving up. Kept
    /// apart from errors: with one shared limit of 3, the benchmark saw Rio
    /// stopped on its third try, the very click (File menu) that recovered
    /// from two dead clicks (est.).
    no_progress: usize,
    timeout: Duration,
}

impl Default for Limits {
    fn default() -> Self {
        Self { per_milestone: 20, total: 80, failures: 3, no_progress: 5, timeout: Duration::from_secs(300) }
    }
}

#[derive(Debug, PartialEq)]
pub(crate) enum Failure {
    Stopped,
    Failed(String),
}

pub(crate) trait Driver {
    fn stopped(&self) -> bool;
    fn replay(&mut self, step: agent::Step);
    fn progressed(&self) -> bool {
        true
    }
    async fn advance(&mut self) -> Result<agent::Step, String>;
    async fn execute(&mut self, step: &agent::Step) -> Result<(), String>;
    async fn pause(&self);
}

/// Whether Rio's last action shows progress. A whole-screen thumbnail cannot
/// see a few letters typed or erased in a field: the benchmark saw runs
/// stopped for "no progress" while Rio was typing its way out (Backspace,
/// a name in a dialog). Keyboard actions are not judged by the thumbnail;
/// repeating the same one is still caught by `same_action`.
pub(crate) fn progressed_after(
    after_action: bool,
    completed: bool,
    screen_moved: bool,
    last_kind: Option<&str>,
) -> bool {
    !after_action || completed || screen_moved || matches!(last_kind, Some("write" | "press_key"))
}

/// A select-all shortcut ("cmd+a", "ctrl+a"): the next write must not click
/// first, or the click drops the selection and the text is appended
/// ("UntitledJournal") instead of replacing it.
pub(crate) fn selects_all(keys: &str) -> bool {
    let parts: Vec<String> = keys.split('+').map(|k| k.trim().to_lowercase()).collect();
    parts.len() == 2 && matches!(parts[0].as_str(), "cmd" | "command" | "meta" | "ctrl" | "control") && parts[1] == "a"
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
    let mut stalls = 0;
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
            Ok(step) => {
                failures = 0;
                step
            }
            Err(error) => {
                failures += 1;
                journal::event("rio_holo_failure", serde_json::json!({ "consecutive": failures, "error": error }));
                if failures >= limits.failures {
                    return Err(Failure::Failed(format!("Could not verify success after several tries: {error}")));
                }
                driver.pause().await;
                continue;
            }
        };
        if step.kind == "done" && !step.unchanged {
            return Ok(total);
        }
        if step.unchanged || !driver.progressed() || previous.as_ref().is_some_and(|p| same_action(p, &step)) {
            stalls += 1;
            journal::event("rio_no_progress", serde_json::json!({ "consecutive": stalls }));
            if stalls >= limits.no_progress {
                return Err(Failure::Failed("The screen or the milestone does not move after Rio's actions".into()));
            }
        } else {
            stalls = 0;
        }
        if step.unchanged {
            driver.pause().await;
            continue;
        }
        if !matches!(step.kind.as_str(), "click" | "write" | "scroll" | "press_key") {
            return Err(Failure::Failed("Holo returned an unknown action".into()));
        }
        let milestone = step.milestone.as_ref().ok_or_else(|| Failure::Failed("Jalon Holo manquant".into()))?;
        let count = counts.entry(milestone.id.clone()).or_default();
        if *count >= limits.per_milestone {
            return Err(Failure::Failed("Action limit reached for this milestone".into()));
        }
        if total >= limits.total {
            return Err(Failure::Failed("Global action limit reached".into()));
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

pub(crate) async fn bounded<D: Driver>(driver: &mut D, limits: Limits) -> Result<usize, Failure> {
    tokio::time::timeout(limits.timeout, drive(driver, limits))
        .await
        .map_err(|_| Failure::Failed("The maximum run time was exceeded".into()))?
}

async fn after_script<D: Driver>(
    driver: &mut D,
    script_result: Result<(), crate::script::Failure>,
    run_mode: &mut skills::Mode,
) -> Result<usize, Failure> {
    if driver.stopped() {
        return Err(Failure::Stopped);
    }
    let reason = match script_result {
        Ok(()) => match driver.advance().await {
            Ok(step) if step.kind == "done" => {
                *run_mode = skills::Mode::Script;
                return Ok(0);
            }
            Ok(step) => {
                driver.replay(step);
                Some("Holo's check still asks for actions".into())
            }
            Err(error) => Some(format!("Holo's check failed: {error}")),
        },
        Err(crate::script::Failure::Stopped) => return Err(Failure::Stopped),
        Err(crate::script::Failure::NotEligible) => None,
        Err(error) => Some(error.to_string()),
    };
    if let Some(reason) = reason {
        journal::event("script_fallback", serde_json::json!({"reason": reason}));
    }
    journal::set_mode("rio");
    *run_mode = skills::Mode::Rio;
    bounded(driver, Limits::default()).await
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
    narrated_milestone: Option<String>,
    /// The last action Rio performed.
    last: Option<agent::Step>,
}

pub(crate) fn narrate_enabled(value: Option<&str>) -> bool {
    value != Some("0")
}

fn narration(step: &agent::Step, new_milestone: bool) -> String {
    let action = if !step.instruction.trim().is_empty() {
        step.instruction.clone()
    } else {
        match step.kind.as_str() {
            "click" => {
                format!("Je clique sur {}.", if step.element.trim().is_empty() { "la cible" } else { &step.element })
            }
            "write" => "Je saisis le texte dans le champ sélectionné.".into(),
            "press_key" => format!("J’utilise le raccourci {}.", step.keys),
            "scroll" => "Je fais défiler la vue pour atteindre la prochaine cible.".into(),
            _ => "Je vérifie l’étape en cours.".into(),
        }
    };
    let short = action.split_whitespace().take(24).collect::<Vec<_>>().join(" ");
    let short: String = short.chars().take(180).collect();
    if new_milestone { format!("Nouvelle étape : {short}") } else { short }
}

static SYNTHESIZING: AtomicBool = AtomicBool::new(false);

async fn wait_narration(
    speech: impl std::future::Future<Output = Result<(), String>>,
    stopped: impl std::future::Future<Output = ()>,
    limit: Duration,
) -> Result<(), String> {
    tokio::select! {
        biased;
        _ = stopped => Ok(()),
        result = tokio::time::timeout(limit, speech) => {
            result.unwrap_or_else(|_| Err("Délai vocal dépassé, poursuite sans voix".into()))
        }
    }
}

async fn narrate(app: &AppHandle, sentence: String, ticket: u64) {
    if SYNTHESIZING.compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst).is_err() {
        eprintln!("[narration] TTS occupée, poursuite sans voix");
        return;
    }
    crate::audio_out::stop();
    let handle = app.clone();
    let synthesis = tauri::async_runtime::spawn_blocking(move || {
        let result = handle.state::<crate::AppState>().tts.say(sentence, Some("fr".into()));
        SYNTHESIZING.store(false, Ordering::SeqCst);
        result
    });
    let deadline = Instant::now() + Duration::from_secs(6);
    let speech = async {
        let (pcm, rate) = synthesis.await.map_err(|e| e.to_string())??;
        if pcm.is_empty() || rate == 0 {
            return Err("TTS sans audio".to_string());
        }
        let duration = Duration::from_secs_f64(pcm.len() as f64 / rate as f64);
        tauri::async_runtime::spawn_blocking(move || {
            crate::audio_out::play_if(&pcm, rate, || {
                !autopilot::stop_requested()
                    && autopilot::narrating()
                    && autopilot::run_id() == ticket
                    && Instant::now() < deadline
            })
        })
        .await
        .map_err(|e| e.to_string())??;
        tokio::time::sleep(duration).await;
        Ok::<(), String>(())
    };
    let interrupted = wait_until(|| autopilot::stop_requested() || !autopilot::narrating());
    if let Err(error) = wait_narration(speech, interrupted, Duration::from_secs(6)).await {
        eprintln!("[narration] {error}");
    }
    crate::audio_out::stop();
}

impl Driver for LiveDriver<'_> {
    fn stopped(&self) -> bool {
        autopilot::stop_requested()
    }
    fn replay(&mut self, step: agent::Step) {
        self.pending = Some(step);
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
        let event = after_action.then(|| "Rio ran the action; check the result on this new screenshot".into());
        let step = agent::advance(self.holo, &mut self.session, event, false).await?;
        let moved = before
            .as_ref()
            .zip(self.session.before.as_ref())
            .is_none_or(|(before, after)| crate::capture::thumb_diff(before, &after.thumb) > 0.1);
        self.progressed = progressed_after(
            after_action,
            !step.completed.is_empty(),
            moved,
            self.last.as_ref().map(|s| s.kind.as_str()),
        );
        Ok(step)
    }

    async fn execute(&mut self, step: &agent::Step) -> Result<(), String> {
        let milestone = step.milestone.as_ref().ok_or("Jalon manquant")?;
        let enabled = autopilot::narrating();
        let sentence = enabled.then(|| narration(step, self.narrated_milestone.as_deref() != Some(&milestone.id)));
        let graph = &self.session.tutorial;
        let index = graph.milestones.iter().position(|m| m.id == milestone.id).ok_or("Jalon inconnu")? + 1;
        self.app
            .emit(
                "autopilot:progress",
                autopilot::Progress {
                    skill_id: graph.id.clone(),
                    index,
                    total: graph.milestones.len(),
                    label: milestone.goal.clone(),
                    message: sentence.clone(),
                },
            )
            .map_err(|e| e.to_string())?;
        if self.stopped() {
            return Err("Stop requested".into());
        }
        if let Some(sentence) = sentence {
            narrate(&self.app, sentence, self.ticket).await;
            self.narrated_milestone = Some(milestone.id.clone());
        }
        if self.stopped() {
            return Err("Stop requested".into());
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
        let click_first = !self.last.as_ref().is_some_and(|p| p.kind == "press_key" && selects_all(&p.keys));
        self.last = Some(step.clone());
        let step = step.clone();
        let ticket = self.ticket;
        tauri::async_runtime::spawn_blocking(move || {
            let _mask = autopilot::mask_capture()?;
            crate::act::perform(&app, &step, ticket, click_first)
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

async fn wait_until(done: impl Fn() -> bool) {
    while !done() {
        tokio::time::sleep(Duration::from_millis(30)).await;
    }
}

pub fn spawn(app: AppHandle, skill: skills::Skill, observed: bool) {
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
            narrated_milestone: None,
            last: None,
        };
        // Full-task scripts cannot resume part way through. The GUI driver
        // verifies each existing milestone on a fresh screen before acting.
        let candidate = if observed { None } else { crate::script::eligible(&skill) };
        let mut run_mode = if candidate.is_some() { skills::Mode::Script } else { skills::Mode::Rio };
        let result = if journal::current_dir().is_none() {
            Err(Failure::Failed("Could not open the journal; no action was run".into()))
        } else {
            let script_result = if let Some(ref artifact) = candidate {
                journal::set_mode("script");
                crate::script::run(artifact).await
            } else {
                Err(crate::script::Failure::NotEligible)
            };
            tokio::select! {
                biased;
                _ = wait_until(autopilot::stop_requested) => Err(Failure::Stopped),
                result = tokio::time::timeout(Limits::default().timeout, after_script(&mut driver, script_result, &mut run_mode)) => {
                    result.unwrap_or_else(|_| Err(Failure::Failed("The maximum run time was exceeded".into())))
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
        let message = if outcome == "failed" {
            Some(autopilot::failure_message(&autopilot::autopilot_view().label))
        } else {
            message
        };
        let done = autopilot::Done { skill_id: skill.tutorial_id, outcome: outcome.into(), message };
        autopilot::finish(&app, &done);
        let _ = app.emit("autopilot:done", done);
        autopilot::driver_released();
    });
}

#[cfg(test)]
mod tests {

    #[test]
    fn typing_is_not_judged_by_the_thumbnail() {
        // A click with no visible effect is no progress; typing cannot be seen at thumbnail scale.
        assert!(!super::progressed_after(true, false, false, Some("click")));
        assert!(super::progressed_after(true, false, false, Some("write")));
        assert!(super::progressed_after(true, false, false, Some("press_key")));
        assert!(super::progressed_after(true, true, false, Some("click")), "a milestone closed");
        assert!(super::progressed_after(false, false, false, None), "no action yet");
    }

    #[test]
    fn select_all_keeps_the_selection_for_the_next_write() {
        for k in ["cmd+a", "ctrl+a", "Command + A", "meta+a"] {
            assert!(super::selects_all(k), "{k}");
        }
        for k in ["a", "cmd+c", "cmd+shift+a", "enter"] {
            assert!(!super::selects_all(k), "{k}");
        }
    }
    use super::*;
    use std::collections::VecDeque;

    #[test]
    fn narration_is_default_on_short_and_marks_new_milestones() {
        assert!(narrate_enabled(None));
        assert!(narrate_enabled(Some("1")));
        assert!(!narrate_enabled(Some("0")));
        let mut step = agent::Step {
            kind: "click".into(),
            instruction: "J’ouvre le menu Format pour mettre le titre en gras.".into(),
            ..Default::default()
        };
        assert_eq!(narration(&step, false), step.instruction);
        assert!(narration(&step, true).starts_with("Nouvelle étape : J’ouvre"));
        step.instruction.clear();
        assert_eq!(narration(&step, false), "Je clique sur la cible.");
        step.kind = "write".into();
        step.text = "private input".into();
        assert_eq!(narration(&step, false), "Je saisis le texte dans le champ sélectionné.");
        step.instruction = "Très longue phrase ".repeat(100);
        assert!(narration(&step, false).chars().count() <= 180);
    }

    #[tokio::test]
    async fn narration_stops_without_waiting_and_bounds_unavailable_tts() {
        use std::future::{pending, ready};
        let limit = Duration::from_millis(5);
        assert_eq!(wait_narration(pending(), ready(()), limit).await, Ok(()));
        assert!(wait_narration(pending(), pending(), limit).await.unwrap_err().contains("Délai vocal"));
        assert_eq!(
            wait_narration(ready(Err("TTS indisponible".into())), pending(), limit).await,
            Err("TTS indisponible".into())
        );
        assert_eq!(wait_narration(ready(Ok(())), pending(), limit).await, Ok(()));
    }

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
        fn replay(&mut self, step: agent::Step) {
            self.steps.push_front(Ok(step));
        }
        fn progressed(&self) -> bool {
            !self.no_screen_change || self.executed == 0
        }
        async fn advance(&mut self) -> Result<agent::Step, String> {
            if self.pending {
                std::future::pending::<()>().await;
            }
            self.steps.pop_front().unwrap_or_else(|| Err("Holo indisponible".into()))
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
        Ok(agent::Step { kind: "done".into(), ..Default::default() })
    }

    #[tokio::test]
    async fn autopilot_negative_acceptance_checks_fail_instead_of_completing() {
        let mut fake = Fake {
            steps: [
                action(148.0, "create"),
                action(148.0, "create"),
                Err("Le texte exact attendu n'est pas visible ; création impossible".into()),
                Err("Le texte exact attendu n'est pas visible ; création impossible".into()),
                Err("Le texte exact attendu n'est pas visible ; création impossible".into()),
            ]
            .into(),
            ..Default::default()
        };
        assert!(matches!(drive(&mut fake, Limits::default()).await,
            Err(Failure::Failed(message)) if message.contains("impossible")));
        assert_eq!(fake.executed, 2);
    }

    #[tokio::test]
    async fn autopilot_script_verification_and_fallback_use_the_live_driver_route() {
        let mut mode = skills::Mode::Rio;
        let mut verified = Fake { steps: [done()].into(), ..Default::default() };
        assert_eq!(after_script(&mut verified, Ok(()), &mut mode).await, Ok(0));
        assert!(matches!(mode, skills::Mode::Script));
        for script_result in [Ok(()), Err(crate::script::Failure::Failed("Erreur factice".into()))] {
            let mut fake = Fake { steps: [action(100.0, "a"), done()].into(), ..Default::default() };
            assert_eq!(after_script(&mut fake, script_result, &mut mode).await, Ok(1));
            assert!(matches!(mode, skills::Mode::Rio));
            assert_eq!(fake.executed, 1);
        }
        let mut failed_check = Fake {
            steps: [Err("Capture indisponible".into()), action(100.0, "a"), done()].into(),
            ..Default::default()
        };
        assert_eq!(after_script(&mut failed_check, Ok(()), &mut mode).await, Ok(1));
        assert!(matches!(mode, skills::Mode::Rio));
        assert_eq!(
            after_script(&mut Fake::default(), Err(crate::script::Failure::Stopped), &mut mode).await,
            Err(Failure::Stopped)
        );
    }

    #[tokio::test]
    async fn autopilot_driver_success_only_after_done() {
        let mut fake = Fake { steps: [action(100.0, "a"), action(200.0, "b"), done()].into(), ..Default::default() };
        assert_eq!(bounded(&mut fake, Limits { per_milestone: 1, ..Default::default() }).await, Ok(2));
        assert_eq!(fake.executed, 2);
        let mut already_done = Fake { steps: [done()].into(), ..Default::default() };
        assert_eq!(bounded(&mut already_done, Limits::default()).await, Ok(0));
    }

    #[tokio::test]
    async fn autopilot_driver_stops_during_run() {
        let mut fake = Fake {
            steps: [action(100.0, "a"), action(200.0, "a"), done()].into(),
            stop_after: Some(1),
            ..Default::default()
        };
        assert_eq!(bounded(&mut fake, Limits::default()).await, Err(Failure::Stopped));
        assert_eq!(fake.executed, 1);
    }

    #[tokio::test]
    async fn autopilot_driver_caps_milestone_and_global_actions() {
        for (per_milestone, total, expected) in [(1, 20, "this milestone"), (20, 1, "Global")] {
            let mut fake =
                Fake { steps: [action(100.0, "a"), action(200.0, "a"), done()].into(), ..Default::default() };
            let result = bounded(&mut fake, Limits { per_milestone, total, ..Default::default() }).await;
            assert!(matches!(result, Err(Failure::Failed(message)) if message.contains(expected)));
            assert_eq!(fake.executed, 1);
        }
    }

    #[tokio::test]
    async fn autopilot_driver_fails_without_progress() {
        let mut fake = Fake {
            steps: [action(100.0, "a"), action(100.0, "a"), action(100.0, "a"), action(100.0, "a"), done()].into(),
            ..Default::default()
        };
        assert!(
            matches!(bounded(&mut fake, Limits { no_progress: 3, ..Default::default() }).await, Err(Failure::Failed(message)) if message.contains("does not move"))
        );
        let mut unchanged = action(200.0, "a").unwrap();
        unchanged.unchanged = true;
        let mut fake = Fake {
            steps: [action(100.0, "a"), Ok(unchanged.clone()), Ok(unchanged.clone()), Ok(unchanged), done()].into(),
            ..Default::default()
        };
        assert!(matches!(
            bounded(&mut fake, Limits { no_progress: 3, ..Default::default() }).await,
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
        let mut injection =
            Fake { steps: [action(100.0, "a"), done()].into(), execution_error: true, ..Default::default() };
        assert_eq!(
            bounded(&mut injection, Limits::default()).await,
            Err(Failure::Failed("Injection indisponible".into()))
        );
        let mut missing = action(100.0, "a").unwrap();
        missing.milestone = None;
        let mut fake = Fake { steps: [Ok(missing)].into(), ..Default::default() };
        assert!(
            matches!(bounded(&mut fake, Limits::default()).await, Err(Failure::Failed(message)) if message.contains("manquant"))
        );
        let mut unknown = Fake { steps: [Ok(agent::Step::default())].into(), ..Default::default() };
        assert!(
            matches!(bounded(&mut unknown, Limits::default()).await, Err(Failure::Failed(message)) if message.contains("unknown"))
        );
        let mut pending = Fake { pending: true, ..Default::default() };
        assert!(
            matches!(bounded(&mut pending, Limits { timeout: Duration::from_millis(1), ..Default::default() }).await, Err(Failure::Failed(message)) if message.contains("run time"))
        );
    }

    #[tokio::test]
    async fn autopilot_driver_unchanged_screen_counts_as_failure_with_different_actions() {
        let mut fake = Fake {
            steps: [action(100.0, "a"), action(200.0, "a"), action(300.0, "a"), action(400.0, "a"), done()].into(),
            no_screen_change: true,
            ..Default::default()
        };
        assert!(
            matches!(bounded(&mut fake, Limits { no_progress: 3, ..Default::default() }).await, Err(Failure::Failed(message)) if message.contains("does not move"))
        );
        assert_eq!(fake.executed, 3);
    }

    #[tokio::test]
    async fn three_dead_actions_no_longer_stop_a_run_that_recovers() {
        // Dead clicks, then the one that works: the default limit lets it through.
        let mut fake = Fake {
            steps: [action(100.0, "a"), action(200.0, "a"), action(300.0, "a"), action(400.0, "a"), done()].into(),
            no_screen_change: true,
            ..Default::default()
        };
        assert_eq!(bounded(&mut fake, Limits::default()).await, Ok(4));
    }
}
