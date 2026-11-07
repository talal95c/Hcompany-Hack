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
}

pub fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

fn dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../skills")
}

fn path(root: &Path, id: &str) -> Result<PathBuf, String> {
    if id.is_empty()
        || id == "."
        || id == ".."
        || !id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return Err("Identifiant de skill invalide".into());
    }
    Ok(root.join(id).join("skill.json"))
}

fn read(root: &Path, id: &str) -> Result<Skill, String> {
    let bytes = std::fs::read(path(root, id)?).map_err(|e| e.to_string())?;
    let skill: Skill = serde_json::from_slice(&bytes).map_err(|e| e.to_string())?;
    if skill.tutorial_id != id {
        return Err("Identifiant de skill incohérent".into());
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

fn record_at(root: &Path, graph: Tutorial, run: Run) -> Result<Skill, String> {
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

pub fn record_run(graph: Tutorial, run: Run) -> Result<Skill, String> {
    let _guard = STORE.lock().unwrap();
    record_at(&dir(), graph, run)
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
    skill.runs.iter().any(|r| r.outcome == "completed")
        && skill.muted_until.is_none_or(|until| now >= until)
}

fn app_key(app: &App) -> String {
    app.name.trim().to_lowercase()
}

fn ready(skill: &Skill, last: &HashMap<String, u64>, now: u64, cooldown: u64) -> bool {
    eligible(skill, now)
        && last
            .get(&app_key(&skill.app))
            .is_none_or(|t| now.saturating_sub(*t) >= cooldown)
}

fn emit(app: &AppHandle, skill: &Skill) -> Result<(), String> {
    app.emit(
        "autopilot:propose",
        Proposal {
            skill_id: skill.tutorial_id.clone(),
            title: skill.title.clone(),
            goal: skill.goal.clone(),
            app: skill.app.clone(),
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
        return Err("Ce skill n'a pas encore réussi".into());
    }
    let mut guard = PROPOSALS.lock().unwrap();
    emit(&app, &skill)?;
    guard
        .get_or_insert_with(HashMap::new)
        .insert(app_key(&skill.app), now());
    Ok(())
}

pub fn spawn(app: AppHandle) {
    std::thread::Builder::new()
        .name("skill-context".into())
        .spawn(move || {
            let cooldown = std::env::var("RIO_SKILLS_COOLDOWN_SECONDS")
                .ok()
                .and_then(|v| v.parse::<u64>().ok())
                .unwrap_or(30 * 60);
            loop {
                std::thread::sleep(Duration::from_secs(3));
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
                let Some(name) = windows
                    .iter()
                    .find(|w| w.is_focused().unwrap_or(false))
                    .and_then(|w| w.app_name().ok())
                else {
                    continue;
                };
                let Ok(skills) = list() else { continue };
                let mut guard = PROPOSALS.lock().unwrap();
                let last = guard.get_or_insert_with(HashMap::new);
                let time = now();
                if let Some(skill) = skills.iter().find(|s| {
                    !s.app.name.trim().is_empty()
                        && s.app.name.eq_ignore_ascii_case(&name)
                        && ready(s, last, time, cooldown)
                }) && emit(&app, skill).is_ok()
                {
                    last.insert(app_key(&skill.app), time);
                }
            }
        })
        .expect("spawn skill context watcher");
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tutorial::Milestone;

    fn graph() -> Tutorial {
        Tutorial {
            id: "example".into(),
            title: "Exemple".into(),
            goal: "Créer".into(),
            app: App {
                name: "Blender".into(),
                ..Default::default()
            },
            milestones: vec![Milestone {
                id: "first".into(),
                hints: vec!["Cliquer".into()],
                ..Default::default()
            }],
            ..Default::default()
        }
    }
    fn run(outcome: &str) -> Run {
        Run {
            date: 100,
            mode: Mode::Learner,
            outcome: outcome.into(),
            duration_s: 12,
            session_id: "session".into(),
        }
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
        assert_eq!(
            read(&root, "example").unwrap().graph.milestones[0]
                .hints
                .len(),
            2
        );
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
    }
}
