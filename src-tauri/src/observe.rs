use crate::tutorial::{Milestone, Tutorial};
use std::collections::{HashMap, HashSet};

pub fn enabled(value: Option<&str>) -> bool {
    value == Some("1")
}

pub fn frontier<'a>(graph: &'a Tutorial, matched: &HashSet<String>) -> Vec<&'a Milestone> {
    let start = graph.start.as_deref().or_else(|| graph.milestones.first().map(|m| m.id.as_str()));
    graph
        .milestones
        .iter()
        .filter(|m| {
            !matched.contains(&m.id)
                && (start == Some(m.id.as_str())
                    || graph.milestones.iter().any(|p| matched.contains(&p.id) && p.next.contains(&m.id)))
                && m.requires.iter().all(|id| matched.contains(id))
        })
        .collect()
}

#[derive(Default)]
pub struct Progress {
    app: String,
    activity: u64,
    pub matched: HashMap<String, HashSet<String>>,
}

impl Progress {
    pub fn context(&mut self, app: &str, now: u64, changed: bool) -> bool {
        let reset = self.app != app || now.saturating_sub(self.activity) >= 300;
        if reset {
            self.matched.clear();
            self.app = app.into();
        }
        if reset || changed {
            self.activity = now;
        }
        reset
    }

    pub fn leader(&self, threshold: usize) -> Option<&str> {
        let max = self.matched.values().map(HashSet::len).max()?;
        if max < threshold.max(1) {
            return None;
        }
        let mut leaders = self.matched.iter().filter(|(_, ids)| ids.len() == max);
        let first = leaders.next()?;
        if leaders.next().is_some() { None } else { Some(first.0.as_str()) }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn opt_in_is_explicit() {
        for value in [None, Some("0"), Some("true"), Some("")] {
            assert!(!enabled(value));
        }
        assert!(enabled(Some("1")));
    }

    #[test]
    fn frontier_follows_edges_and_requires() {
        let graph = Tutorial {
            start: Some("a".into()),
            milestones: vec![
                Milestone { id: "a".into(), next: vec!["b".into(), "c".into()], ..Default::default() },
                Milestone { id: "b".into(), next: vec!["c".into()], ..Default::default() },
                Milestone { id: "c".into(), requires: vec!["b".into()], ..Default::default() },
            ],
            ..Default::default()
        };
        let ids = |set| frontier(&graph, &set).iter().map(|m| m.id.clone()).collect::<Vec<_>>();
        assert_eq!(ids(HashSet::new()), ["a"]);
        assert_eq!(ids(HashSet::from(["a".into()])), ["b"]);
        assert_eq!(ids(HashSet::from(["a".into(), "b".into()])), ["c"]);
        assert!(ids(HashSet::from(["a".into(), "b".into(), "c".into()])).is_empty());
        assert!(frontier(&Tutorial::default(), &HashSet::new()).is_empty());
    }

    #[test]
    fn threshold_ties_and_context_reset() {
        let mut progress = Progress::default();
        assert!(progress.context("blender", 10, false));
        progress.matched.insert("one".into(), HashSet::from(["a".into(), "b".into()]));
        assert_eq!(progress.leader(3), None);
        assert_eq!(progress.leader(2), Some("one"));
        progress.matched.insert("two".into(), HashSet::from(["a".into(), "b".into()]));
        assert_eq!(progress.leader(2), None);
        assert!(!progress.context("blender", 20, true));
        assert!(progress.context("calc", 21, false));
        assert!(progress.matched.is_empty());
        progress.matched.insert("one".into(), HashSet::from(["a".into()]));
        assert!(progress.context("calc", 321, false));
        assert!(progress.matched.is_empty());
    }
}
