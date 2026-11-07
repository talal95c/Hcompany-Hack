//! Tutorial format: a graph of milestones (screen-verifiable sub-goals), not
//! a click script. Holo finds the clicks live; the graph says what to reach
//! and how to tell it is reached.
//!
//! Files live in `h-tutor/tutorials/*.json` (authored, generated from a goal,
//! or promoted from a recorded session).

use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::path::PathBuf;

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct App {
    pub name: String,
    /// macOS bundle id, used to find the installed app (and its icon).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub bundle_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub min_version: Option<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default, PartialEq)]
pub struct Milestone {
    pub id: String,
    /// Imperative sub-goal, e.g. "Add a torus".
    pub goal: String,
    /// Observable success criterion, judged by Holo on the screenshot.
    pub done_when: String,
    /// Known path (from the author or a recorded session): guidance, not a script.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub hints: Vec<String>,
    /// Concept worth explaining while doing it.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub teach: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub next: Vec<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub requires: Vec<String>,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub optional: bool,
    /// Second in the source video where this is shown (YouTube imports).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub video_at: Option<u32>,
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct Tutorial {
    pub id: String,
    #[serde(default = "one")]
    pub version: u32,
    pub title: String,
    #[serde(default)]
    pub app: App,
    pub goal: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub language: Option<String>,
    /// "authored" | "generated" | "recorded" | "youtube" | "company" (Rio platform)
    #[serde(default = "authored")]
    pub source: String,
    /// Where it came from (the YouTube video for imports).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_url: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub start: Option<String>,
    pub milestones: Vec<Milestone>,
}

fn one() -> u32 {
    1
}
fn authored() -> String {
    "authored".into()
}

/// What the scheduler can do next.
#[derive(Debug, PartialEq)]
pub enum Next<'a> {
    Ready(&'a Milestone),
    /// Every required milestone is finished.
    Complete,
    /// Required milestones remain but none of them can start (cycle, or a
    /// dependency that can never be reached).
    Blocked(Vec<String>),
}

#[derive(Serialize, Clone, Copy, PartialEq, Eq, Debug)]
#[serde(rename_all = "lowercase")]
pub enum Status {
    Todo,
    Current,
    Done,
    Skipped,
}

impl Tutorial {
    /// Checks ids and references so a bad file fails on load, not mid-session.
    pub fn validate(&self) -> Result<(), String> {
        if self.milestones.is_empty() {
            return Err(format!("{}: no milestones", self.id));
        }
        let ids: HashSet<&str> = self.milestones.iter().map(|m| m.id.as_str()).collect();
        if ids.len() != self.milestones.len() {
            return Err(format!("{}: duplicate milestone ids", self.id));
        }
        for m in &self.milestones {
            for r in m.next.iter().chain(&m.requires) {
                if !ids.contains(r.as_str()) {
                    return Err(format!("{}: milestone {} references unknown {r}", self.id, m.id));
                }
            }
        }
        if let Some(s) = &self.start
            && !ids.contains(s.as_str())
        {
            return Err(format!("{}: unknown start {s}", self.id));
        }
        // Run the scheduler itself on the graph: every required milestone
        // must be reachable, otherwise a session would stall on it.
        let mut finished = HashSet::new();
        loop {
            match self.next(&finished) {
                Next::Ready(m) => {
                    finished.insert(m.id.clone());
                }
                Next::Complete => return Ok(()),
                Next::Blocked(ids) => {
                    return Err(format!("{}: unreachable milestones {}", self.id, ids.join(", ")));
                }
            }
        }
    }

    pub fn milestone(&self, id: &str) -> Option<&Milestone> {
        self.milestones.iter().find(|m| m.id == id)
    }

    /// The milestone to work on next, given what is finished (done or
    /// skipped). A milestone is available when its `requires` are finished
    /// and either it is the start, or one milestone pointing to it with
    /// `next` is finished, or nothing points to it and the start is finished.
    /// File order breaks ties. When nothing is available, tells a finished
    /// tutorial (only optional milestones left) from a blocked one.
    pub fn next(&self, finished: &HashSet<String>) -> Next<'_> {
        if let Some(m) = self.ready_milestone(finished) {
            return Next::Ready(m);
        }
        let blocked: Vec<String> =
            self.milestones.iter().filter(|m| !m.optional && !finished.contains(&m.id)).map(|m| m.id.clone()).collect();
        if blocked.is_empty() { Next::Complete } else { Next::Blocked(blocked) }
    }

    fn ready_milestone(&self, finished: &HashSet<String>) -> Option<&Milestone> {
        let start = self.start.as_deref();
        let start_done = start.is_none_or(|s| finished.contains(s));
        self.milestones.iter().find(|m| {
            if finished.contains(&m.id) || !m.requires.iter().all(|r| finished.contains(r)) {
                return false;
            }
            if start == Some(m.id.as_str()) {
                return true;
            }
            let mut preds = self.milestones.iter().filter(|p| p.next.contains(&m.id)).peekable();
            if preds.peek().is_none() { start_done } else { preds.any(|p| finished.contains(&p.id)) }
        })
    }
}

/// Where tutorials are stored (dev: next to the project).
pub fn dir() -> PathBuf {
    let d = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../tutorials");
    let _ = std::fs::create_dir_all(&d);
    d
}

#[derive(Serialize, Deserialize, Clone)]
pub struct Summary {
    pub id: String,
    pub title: String,
    pub app: String,
    pub bundle_id: Option<String>,
    pub goal: String,
    pub milestones: usize,
    pub source: String,
}

pub fn list() -> Vec<Summary> {
    let mut out: Vec<Summary> = std::fs::read_dir(dir())
        .into_iter()
        .flatten()
        .flatten()
        .filter(|e| e.path().extension().is_some_and(|x| x == "json"))
        .filter_map(|e| {
            let t: Tutorial = serde_json::from_slice(&std::fs::read(e.path()).ok()?).ok()?;
            t.validate().ok()?;
            Some(Summary {
                id: t.id,
                title: t.title,
                app: t.app.name,
                bundle_id: t.app.bundle_id,
                goal: t.goal,
                milestones: t.milestones.len(),
                source: t.source,
            })
        })
        .collect();
    out.sort_by(|a, b| a.title.cmp(&b.title));
    out
}

pub fn load(id: &str) -> Result<Tutorial, String> {
    let path = dir().join(format!("{}.json", slug(id)));
    let t: Tutorial = serde_json::from_slice(&std::fs::read(&path).map_err(|e| format!("{id}: {e}"))?)
        .map_err(|e| format!("{id}: invalid tutorial ({e})"))?;
    t.validate()?;
    Ok(t)
}

pub fn save(t: &Tutorial) -> Result<PathBuf, String> {
    t.validate()?;
    let path = dir().join(format!("{}.json", slug(&t.id)));
    std::fs::write(&path, serde_json::to_vec_pretty(t).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    Ok(path)
}

pub fn slug(s: &str) -> String {
    let mut out = String::new();
    for c in s.to_lowercase().chars() {
        if c.is_ascii_alphanumeric() {
            out.push(c);
        } else if !out.ends_with('-') {
            out.push('-');
        }
    }
    out.trim_matches('-').chars().take(60).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn m(id: &str, next: &[&str], requires: &[&str], optional: bool) -> Milestone {
        Milestone {
            id: id.into(),
            goal: id.into(),
            done_when: id.into(),
            next: next.iter().map(|s| s.to_string()).collect(),
            requires: requires.iter().map(|s| s.to_string()).collect(),
            optional,
            ..Default::default()
        }
    }

    #[test]
    fn walks_the_graph() {
        let t = Tutorial {
            id: "t".into(),
            title: "t".into(),
            goal: "g".into(),
            start: Some("a".into()),
            milestones: vec![
                m("a", &["b"], &[], false),
                m("b", &["c", "d"], &[], false),
                m("c", &[], &[], true),
                m("d", &[], &["b"], false),
            ],
            ..Default::default()
        };
        t.validate().unwrap();
        let mut done = HashSet::new();
        assert_eq!(t.ready_milestone(&done).unwrap().id, "a");
        done.insert("a".to_string());
        assert_eq!(t.ready_milestone(&done).unwrap().id, "b");
        done.insert("b".to_string());
        assert_eq!(t.ready_milestone(&done).unwrap().id, "c");
        done.insert("c".to_string());
        assert_eq!(t.ready_milestone(&done).unwrap().id, "d");
        done.insert("d".to_string());
        assert_eq!(t.next(&done), Next::Complete);
    }

    #[test]
    fn mutual_requires_is_blocked_and_rejected() {
        let t = Tutorial {
            id: "t".into(),
            title: "t".into(),
            goal: "g".into(),
            start: Some("a".into()),
            milestones: vec![m("a", &[], &["b"], false), m("b", &[], &["a"], false)],
            ..Default::default()
        };
        assert_eq!(t.next(&HashSet::new()), Next::Blocked(vec!["a".into(), "b".into()]));
        assert!(t.validate().unwrap_err().contains("unreachable"));
    }

    #[test]
    fn only_optional_left_is_complete() {
        let t = Tutorial {
            id: "t".into(),
            title: "t".into(),
            goal: "g".into(),
            milestones: vec![m("a", &[], &[], false), m("b", &[], &["c"], true), m("c", &[], &["b"], true)],
            ..Default::default()
        };
        t.validate().unwrap();
        let done = HashSet::from(["a".to_string()]);
        assert_eq!(t.next(&done), Next::Complete);
    }

    #[test]
    fn shipped_tutorials_are_schedulable() {
        for e in std::fs::read_dir(dir()).unwrap().flatten() {
            if e.path().extension().is_some_and(|x| x == "json") {
                let t: Tutorial = serde_json::from_slice(&std::fs::read(e.path()).unwrap()).unwrap();
                t.validate().unwrap_or_else(|err| panic!("{}: {err}", e.path().display()));
            }
        }
    }

    #[test]
    fn linear_without_edges() {
        let t = Tutorial {
            id: "t".into(),
            title: "t".into(),
            goal: "g".into(),
            milestones: vec![m("a", &[], &[], false), m("b", &[], &[], false)],
            ..Default::default()
        };
        let mut done = HashSet::new();
        assert_eq!(t.ready_milestone(&done).unwrap().id, "a");
        done.insert("a".to_string());
        assert_eq!(t.ready_milestone(&done).unwrap().id, "b");
    }
}
