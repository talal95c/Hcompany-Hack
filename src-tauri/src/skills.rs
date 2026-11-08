use crate::tutorial::{App, Tutorial};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, Manager};

static STORE: Mutex<()> = Mutex::new(());
static PROPOSALS: Mutex<Option<HashMap<String, u64>>> = Mutex::new(None);
const MUTE_SECONDS: u64 = 24 * 60 * 60;

#[derive(Clone, Serialize, Deserialize, Debug)]
#[serde(rename_all = "lowercase")]
pub enum Mode {
    Learner,
    Rio,
    Script,
}

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Run {
    pub date: u64,
    pub mode: Mode,
    pub outcome: String,
    pub duration_s: u64,
    pub session_id: String,
}

#[derive(Clone, Serialize, Deserialize, Debug)]
pub struct Skill {
    pub tutorial_id: String,
    pub title: String,
    pub goal: String,
    pub app: App,
    pub graph: Tutorial,
    pub runs: Vec<Run>,
    pub compiled: Vec<serde_json::Value>,
    pub muted_until: Option<u64>,
    pub declines: u32,
}

#[derive(Clone, Serialize, Deserialize)]
pub struct Proposal {
    pub skill_id: String,
    pub title: String,
    pub goal: String,
    pub app: App,
    pub mode: String,
    #[serde(default)]
    pub done: usize,
    #[serde(default)]
    pub total: usize,
    #[serde(default)]
    pub matched: Vec<String>,
}

pub fn now() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_secs()
}

fn dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../skills")
}

fn path(root: &Path, id: &str) -> Result<PathBuf, String> {
    if id.is_empty()
        || id == "."
        || id == ".."
        || !id.chars().all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return Err("Identifiant de skill invalide".into());
    }
    Ok(root.join(id).join("skill.json"))
}

fn read(root: &Path, id: &str) -> Result<Skill, String> {
    let bytes = std::fs::read(path(root, id)?).map_err(|e| e.to_string())?;
    let skill: Skill = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    if skill.tutorial_id != id {
        return Err("Inconsistent skill id".into());
    }
    skill.graph.validate()?;
    Ok(skill)
}

fn write(root: &Path, skill: &Skill) -> Result<(), String> {
    let target = path(root, &skill.tutorial_id)?;
    let parent = target.parent().ok_or("Chemin de skill invalide")?;
    std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let temp = parent.join("skill.json.tmp");
    let result = (|| {
        let mut file = std::fs::File::create(&temp)?;
        file.write_all(&serde_json::to_vec_pretty(skill)?)?;
        file.sync_all()?;
        std::fs::rename(&temp, &target)
    })();
    if result.is_err() {
        let _ = std::fs::remove_file(temp);
    }
    result.map_err(|e: std::io::Error| e.to_string())
}

fn structural_fingerprint(graph: &Tutorial) -> String {
    let milestones: Vec<_> = graph
        .milestones
        .iter()
        .map(|m| {
            let mut next = m.next.clone();
            let mut requires = m.requires.clone();
            next.sort();
            requires.sort();
            serde_json::json!({
                "id": m.id, "goal": m.goal, "done_when": m.done_when,
                "next": next, "requires": requires, "optional": m.optional,
            })
        })
        .collect();
    crate::devin::hash(
        &serde_json::json!({
            "goal": graph.goal, "start": graph.start, "milestones": milestones,
        })
        .to_string(),
    )
}

fn record_at(root: &Path, mut graph: Tutorial, run: Run) -> Result<Skill, String> {
    graph.validate()?;
    let target = path(root, &graph.id)?;
    let mut skill = if target.exists() {
        read(root, &graph.id)?
    } else {
        Skill {
            tutorial_id: graph.id.clone(),
            title: graph.title.clone(),
            goal: graph.goal.clone(),
            app: graph.app.clone(),
            graph: graph.clone(),
            runs: Vec::new(),
            compiled: Vec::new(),
            muted_until: None,
            declines: 0,
        }
    };
    if run.outcome == "completed" {
        graph.version = if structural_fingerprint(&graph) == structural_fingerprint(&skill.graph) {
            skill.graph.version
        } else {
            skill.graph.version.checked_add(1).ok_or("Skill version exhausted")?
        };
        skill.title = graph.title.clone();
        skill.goal = graph.goal.clone();
        skill.app = graph.app.clone();
        skill.graph = graph;
        skill.declines = 0;
    }
    skill.runs.push(run);
    write(root, &skill)?;
    Ok(skill)
}

pub fn record_run(mut graph: Tutorial, run: Run) -> Result<Skill, String> {
    // Platform tutorials have ids like "rio:org:<uuid>": keep the skill's
    // folder name to safe characters.
    graph.id = safe_id(&graph.id);
    let succeeded = run.outcome == "completed";
    let skill = {
        let _guard = STORE.lock().unwrap();
        record_at(&dir(), graph, run)?
    };
    if succeeded {
        crate::devin::auto_compile(&skill);
    }
    Ok(skill)
}

pub fn save_compilation(id: &str, artifact: &crate::devin::Compiled) -> Result<(), String> {
    let _guard = STORE.lock().unwrap();
    let mut skill = read(&dir(), id)?;
    let value = serde_json::to_value(artifact).map_err(|_| "Compilation cannot be serialized")?;
    if let Some(old) = skill.compiled.iter_mut().find(|v| v["session_id"] == artifact.session_id) {
        *old = value;
    } else {
        skill.compiled.push(value);
    }
    write(&dir(), &skill)
}

fn safe_id(id: &str) -> String {
    id.chars().map(|c| if c.is_ascii_alphanumeric() || c == '-' || c == '_' { c } else { '_' }).collect()
}

pub fn load(id: &str) -> Result<Skill, String> {
    let _guard = STORE.lock().unwrap();
    read(&dir(), id)
}

pub fn list() -> Result<Vec<Skill>, String> {
    let _guard = STORE.lock().unwrap();
    let root = dir();
    if !root.exists() {
        return Ok(Vec::new());
    }
    let mut skills = Vec::new();
    for entry in std::fs::read_dir(&root).map_err(|e| e.to_string())? {
        let entry = entry.map_err(|e| e.to_string())?;
        if entry.file_type().map_err(|e| e.to_string())?.is_dir() {
            skills.push(read(&root, &entry.file_name().to_string_lossy())?);
        }
    }
    skills.sort_by(|a, b| a.tutorial_id.cmp(&b.tutorial_id));
    Ok(skills)
}

fn decline_at(skill: &mut Skill, now: u64) {
    skill.declines = skill.declines.saturating_add(1);
    if skill.declines >= 2 {
        skill.muted_until = Some(now.saturating_add(MUTE_SECONDS));
        skill.declines = 0;
    }
}

pub fn decline(id: &str) -> Result<(), String> {
    let _guard = STORE.lock().unwrap();
    let mut skill = read(&dir(), id)?;
    decline_at(&mut skill, now());
    write(&dir(), &skill)
}

fn eligible(skill: &Skill, now: u64) -> bool {
    skill.runs.iter().any(|r| r.outcome == "completed") && skill.muted_until.is_none_or(|until| now >= until)
}

fn app_key(app: &App) -> String {
    app.name.trim().to_lowercase()
}

fn ready(skill: &Skill, last: &HashMap<String, u64>, now: u64, cooldown: u64) -> bool {
    eligible(skill, now) && last.get(&app_key(&skill.app)).is_none_or(|t| now.saturating_sub(*t) >= cooldown)
}

fn emit(app: &AppHandle, skill: &Skill) -> Result<(), String> {
    app.emit(
        "autopilot:propose",
        Proposal {
            skill_id: skill.tutorial_id.clone(),
            title: skill.title.clone(),
            goal: skill.goal.clone(),
            app: skill.app.clone(),
            mode: crate::devin::mode(skill).into(),
            done: 0,
            total: skill.graph.milestones.len(),
            matched: Vec::new(),
        },
    )
    .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn skills_list() -> Result<Vec<Skill>, String> {
    list()
}

#[tauri::command]
pub fn skill_decline(skill_id: String) -> Result<(), String> {
    decline(&skill_id)
}

#[tauri::command]
pub fn skill_propose_now(app: AppHandle, skill_id: String) -> Result<(), String> {
    let skill = load(&skill_id)?;
    if !skill.runs.iter().any(|r| r.outcome == "completed") {
        return Err("This skill has not succeeded yet".into());
    }
    emit(&app, &skill)?;
    PROPOSALS.lock().unwrap().get_or_insert_with(HashMap::new).insert(app_key(&skill.app), now());
    Ok(())
}

pub fn spawn(app: AppHandle) {
    std::thread::Builder::new()
        .name("skill-context".into())
        .spawn(move || {
            if crate::observe::enabled(std::env::var("RIO_OBSERVE").ok().as_deref()) {
                observe(&app);
                return;
            }
            let cooldown = std::env::var("RIO_SKILLS_COOLDOWN_SECONDS")
                .ok()
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(30 * 60);
            loop {
                std::thread::sleep(Duration::from_secs(3));
                if crate::autopilot::is_running() {
                    continue;
                }
                let state = app.state::<crate::AppState>();
                let Ok(session) = state.session.try_lock() else {
                    continue;
                };
                if session.as_ref().is_some_and(|s| !s.finished) {
                    continue;
                }
                let Ok(windows) = xcap::Window::all() else {
                    continue;
                };
                let Some(name) =
                    windows.iter().find(|w| w.is_focused().unwrap_or(false)).and_then(|w| w.app_name().ok())
                else {
                    continue;
                };
                let Ok(skills) = list() else { continue };
                let time = now();
                let candidate = {
                    let mut guard = PROPOSALS.lock().unwrap();
                    let last = guard.get_or_insert_with(HashMap::new);
                    skills.iter().find(|s| {
                        !s.app.name.trim().is_empty()
                            && s.app.name.eq_ignore_ascii_case(&name)
                            && ready(s, last, time, cooldown)
                    })
                };
                if let Some(skill) = candidate
                    && emit(&app, skill).is_ok()
                {
                    PROPOSALS.lock().unwrap().get_or_insert_with(HashMap::new).insert(app_key(&skill.app), time);
                }
            }
        })
        .expect("spawn skill context watcher");
}

fn focused_app() -> Option<String> {
    xcap::Window::all().ok()?.iter().find(|w| w.is_focused().unwrap_or(false))?.app_name().ok()
}

fn observe(app: &AppHandle) {
    use crate::capture::{SCREEN_CHANGED, capture_thumb, thumb_diff};
    let threshold = std::env::var("RIO_OBSERVE_STEPS").ok().and_then(|v| v.parse::<usize>().ok()).unwrap_or(3).max(1);
    let cooldown =
        std::env::var("RIO_SKILLS_COOLDOWN_SECONDS").ok().and_then(|v| v.parse::<u64>().ok()).unwrap_or(30 * 60);
    let mut progress = crate::observe::Progress::default();
    let mut previous = None;
    let mut pending = false;
    let mut last_check = 0;
    let mut cursor = 0usize;
    loop {
        std::thread::sleep(Duration::from_secs(3));
        let state = app.state::<crate::AppState>();
        let tutorial_running = {
            let Ok(session) = state.session.try_lock() else { continue };
            session.as_ref().is_some_and(|s| !s.finished)
        };
        if crate::autopilot::is_running() || tutorial_running {
            progress = crate::observe::Progress::default();
            previous = None;
            pending = false;
            continue;
        }
        let name = focused_app().unwrap_or_default().to_lowercase();
        let time = now();
        if progress.context(&name, time, false) {
            previous = None;
            pending = false;
        }
        let Ok(skills) = list() else { continue };
        let candidates: Vec<_> = skills
            .iter()
            .filter(|s| !name.is_empty() && s.app.name.eq_ignore_ascii_case(&name) && eligible(s, time))
            .collect();
        progress.matched.retain(|id, _| candidates.iter().any(|s| &s.tutorial_id == id));
        if candidates.is_empty() {
            continue;
        }
        let Ok(thumb) = capture_thumb() else { continue };
        let difference = previous.as_ref().map(|p| thumb_diff(p, &thumb));
        previous = Some(thumb);
        if difference.is_some_and(|d| d >= SCREEN_CHANGED) {
            progress.context(&name, time, true);
            pending = true;
            continue;
        }
        if !pending || difference.is_none_or(|d| d > 0.35) || time.saturating_sub(last_check) < 6 {
            continue;
        }
        pending = false;
        let mut checks = Vec::new();
        for skill in &candidates {
            let matched = progress.matched.entry(skill.tutorial_id.clone()).or_default();
            for milestone in crate::observe::frontier(&skill.graph, matched) {
                checks.push((*skill, milestone));
            }
        }
        if checks.is_empty() {
            continue;
        }
        let (skill, milestone) = checks[cursor % checks.len()];
        cursor = cursor.wrapping_add(1);
        last_check = time;
        let generation = state.generation.current();
        let met = tauri::async_runtime::block_on(async {
            tokio::time::timeout(
                Duration::from_secs(15),
                crate::agent::observe_milestone(&state.holo, &milestone.done_when),
            )
            .await
            .is_ok_and(|r| r.is_ok())
        });
        let tutorial_running = {
            match state.session.try_lock() {
                Ok(session) => session.as_ref().is_some_and(|s| !s.finished),
                Err(_) => true,
            }
        };
        if tutorial_running
            || crate::autopilot::is_running()
            || !state.generation.is_current(generation)
            || focused_app().is_none_or(|n| !n.eq_ignore_ascii_case(&name))
        {
            progress = crate::observe::Progress::default();
            previous = None;
            continue;
        }
        if met {
            progress.matched.entry(skill.tutorial_id.clone()).or_default().insert(milestone.id.clone());
        }
        let Some(id) = progress.leader(threshold) else { continue };
        let Some(skill) = candidates.iter().find(|s| s.tutorial_id == id) else { continue };
        let mut guard = PROPOSALS.lock().unwrap();
        let last = guard.get_or_insert_with(HashMap::new);
        if !ready(skill, last, now(), cooldown) {
            continue;
        }
        let mut matched: Vec<_> = progress.matched[id].iter().cloned().collect();
        matched.sort();
        if app
            .emit(
                "autopilot:propose",
                Proposal {
                    skill_id: skill.tutorial_id.clone(),
                    title: skill.title.clone(),
                    goal: skill.goal.clone(),
                    app: skill.app.clone(),
                    mode: "rio".into(),
                    done: matched.len(),
                    total: skill.graph.milestones.len(),
                    matched,
                },
            )
            .is_ok()
        {
            last.insert(app_key(&skill.app), now());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tutorial::Milestone;

    #[test]
    fn textedit_demo_is_eligible_and_starts_at_first_milestone() {
        let skill: Skill = serde_json::from_str(include_str!("../../demo/textedit-courses/skill.json")).unwrap();
        skill.graph.validate().unwrap();
        assert_eq!(skill.app.name, "TextEdit");
        assert!(skill.app.name.eq_ignore_ascii_case("TextEdit"));
        assert!(eligible(&skill, 0));
        assert_eq!(skill.runs.len(), 1);
        assert_eq!(skill.runs[0].outcome, "completed");
        assert!(skill.compiled.is_empty());
        assert_eq!(skill.graph.milestones.len(), 6);
        let mut matched = std::collections::HashSet::new();
        for milestone in &skill.graph.milestones {
            let frontier = crate::observe::frontier(&skill.graph, &matched);
            assert_eq!(frontier.len(), 1);
            assert_eq!(frontier[0].id, milestone.id);
            matched.insert(milestone.id.clone());
        }
        assert!(crate::observe::frontier(&skill.graph, &matched).is_empty());
    }

    #[test]
    fn excel_demo_is_eligible_and_starts_at_first_milestone() {
        let skill: Skill = serde_json::from_str(include_str!("../../demo/excel-courses/skill.json")).unwrap();
        skill.graph.validate().unwrap();
        assert_eq!(skill.app.name, "Microsoft Excel");
        assert_eq!(skill.graph.app.name, skill.app.name);
        assert!(eligible(&skill, 0));
        assert_eq!(skill.runs.len(), 1);
        assert_eq!(skill.runs[0].outcome, "completed");
        assert!(skill.compiled.is_empty());
        assert_eq!(skill.graph.milestones.len(), 7);
        let mut matched = std::collections::HashSet::new();
        for milestone in &skill.graph.milestones {
            let frontier = crate::observe::frontier(&skill.graph, &matched);
            assert_eq!(frontier.len(), 1);
            assert_eq!(frontier[0].id, milestone.id);
            matched.insert(milestone.id.clone());
        }
        assert!(crate::observe::frontier(&skill.graph, &matched).is_empty());
        let formula = &skill.graph.milestone("m5").unwrap().done_when;
        for alternative in ["6,5", "6.5", "=SUM(B2:B4)", "=SOMME(B2:B4)"] {
            assert!(formula.contains(alternative));
        }
    }

    fn graph() -> Tutorial {
        Tutorial {
            id: "example".into(),
            title: "Exemple".into(),
            goal: "Créer".into(),
            app: App { name: "Blender".into(), ..Default::default() },
            milestones: vec![Milestone { id: "first".into(), hints: vec!["Cliquer".into()], ..Default::default() }],
            ..Default::default()
        }
    }
    fn run(outcome: &str) -> Run {
        Run { date: 100, mode: Mode::Learner, outcome: outcome.into(), duration_s: 12, session_id: "session".into() }
    }
    #[test]
    fn skills_record_creates_updates_and_replaces_atomically() {
        let root = dir().join(format!("test-{}", std::process::id()));
        let first = record_at(&root, graph(), run("completed")).unwrap();
        assert_eq!(first.runs.len(), 1);
        let target = path(&root, "example").unwrap();
        let old_file = std::fs::File::open(&target).unwrap();
        let mut updated = graph();
        updated.milestones[0].hints.push("Écrire".into());
        let second = record_at(&root, updated, run("completed")).unwrap();
        assert_eq!(second.runs.len(), 2);
        assert_eq!(read(&root, "example").unwrap().graph.milestones[0].hints.len(), 2);
        let old: Skill = serde_json::from_reader(old_file).unwrap();
        assert_eq!(old.runs.len(), 1);
        assert!(!target.with_extension("json.tmp").exists());
        assert!(second.compiled.is_empty());
        std::fs::write(&target, b"invalid").unwrap();
        assert!(record_at(&root, graph(), run("completed")).is_err());
        assert_eq!(std::fs::read(&target).unwrap(), b"invalid");
        std::fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn skills_clock_controls_cooldown_and_two_declines() {
        let mut skill = Skill {
            tutorial_id: "example".into(),
            title: "Exemple".into(),
            goal: "Créer".into(),
            app: graph().app,
            graph: graph(),
            runs: Vec::new(),
            compiled: Vec::new(),
            muted_until: None,
            declines: 0,
        };
        let mut last = HashMap::new();
        assert!(!ready(&skill, &last, 100, 1800));
        skill.runs.push(run("error"));
        assert!(!ready(&skill, &last, 100, 1800));
        skill.runs.push(run("completed"));
        assert!(ready(&skill, &last, 100, 1800));
        last.insert(app_key(&skill.app), 100);
        assert!(!ready(&skill, &last, 1899, 1800));
        assert!(ready(&skill, &last, 1900, 1800));
        decline_at(&mut skill, 1900);
        assert!(ready(&skill, &last, 1900, 1800));
        decline_at(&mut skill, 1901);
        assert!(!ready(&skill, &last, 1901 + MUTE_SECONDS - 1, 1800));
        assert!(ready(&skill, &last, 1901 + MUTE_SECONDS, 1800));
        assert!(path(Path::new("."), "../escape").is_err());
        assert_eq!(safe_id("rio:org:5f2a-9c"), "rio_org_5f2a-9c");
    }

    #[test]
    fn skills_structural_version_preserves_script_across_runs() {
        let root = dir().join(format!("test-structure-{}", std::process::id()));
        let mut first = record_at(&root, graph(), run("completed")).unwrap();
        let script = "echo exemple";
        first.compiled.push(serde_json::json!({
            "graph_version": first.graph.version, "session_id": "test", "url": "",
            "status": "completed", "date": 100, "sha256": crate::devin::hash(script),
            "target_os": std::env::consts::OS, "acus_consumed": 0,
            "language": "bash", "script": script, "params": [],
            "test_command": "bash script", "tested": true,
            "test_platform": std::env::consts::OS, "test_evidence": "Exemple vérifié", "notes": ""
        }));
        write(&root, &first).unwrap();
        let empty = Tutorial { milestones: Vec::new(), ..first.graph.clone() };
        assert!(record_at(&root, empty, run("completed")).is_err());
        assert!(crate::devin::selected(&read(&root, "example").unwrap()).is_some());
        for i in 1..=2 {
            let mut replay = first.graph.clone();
            replay.version += i;
            replay.milestones[0].hints = vec![format!("Autre hint {i}")];
            replay.language = Some("fr".into());
            replay.source = "recorded".into();
            replay.milestones[0].teach = Some("Explication".into());
            let saved = record_at(&root, replay, run("completed")).unwrap();
            assert_eq!(saved.graph.version, first.graph.version);
            assert!(crate::devin::selected(&saved).is_some());
        }
        let mut changed = first.graph.clone();
        changed.milestones[0].done_when = "Nouvelle preuve obligatoire".into();
        let saved = record_at(&root, changed, run("completed")).unwrap();
        assert_eq!(saved.graph.version, first.graph.version + 1);
        assert!(crate::devin::selected(&saved).is_none());
        let unchanged = record_at(&root, saved.graph.clone(), run("failed")).unwrap();
        assert_eq!(unchanged.graph.version, saved.graph.version);
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn skills_structure_covers_goals_edges_and_empty_graph_metadata() {
        let original = graph();
        for changed in [
            Tutorial { goal: "Autre but".into(), ..original.clone() },
            Tutorial { start: Some("first".into()), ..original.clone() },
            Tutorial {
                milestones: vec![Milestone { goal: "Autre étape".into(), ..original.milestones[0].clone() }],
                ..original.clone()
            },
            Tutorial {
                milestones: vec![Milestone { next: vec!["first".into()], ..original.milestones[0].clone() }],
                ..original.clone()
            },
            Tutorial { milestones: Vec::new(), ..original.clone() },
        ] {
            assert_ne!(structural_fingerprint(&original), structural_fingerprint(&changed));
        }
        let mut metadata = original.clone();
        metadata.title = "Autre titre".into();
        metadata.milestones[0].video_at = Some(30);
        assert_eq!(structural_fingerprint(&original), structural_fingerprint(&metadata));
    }
}
