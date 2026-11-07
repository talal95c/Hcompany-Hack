use super::*;
use std::sync::Arc;
use tokio::sync::{mpsc, oneshot};

pub struct Change {
    pub source: Handle,
    pub reconcile: bool,
    pub focus: bool,
    pub scoped: bool,
}

#[derive(Clone)]
pub(super) struct Watch {
    pub id: String,
    pub app: Handle,
    pub refs: Vec<String>,
    pub request_id: String,
    pub scopes: Vec<String>,
    pub bindings: Vec<scoped::Binding>,
}

impl Service {
    pub(super) fn invalidate_collection(&self) {
        self.collection_epoch
            .fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        self.cached.lock().unwrap().clear();
    }
    pub fn cancel(&self, id: &str) {
        if let Some(task) = self.requests.lock().unwrap().remove(id) {
            task.abort();
        }
        let watched = self
            .watch
            .lock()
            .unwrap()
            .as_ref()
            .is_some_and(|w| w.request_id == id);
        if watched {
            self.stop_watch();
        }
    }

    pub fn track(&self, id: String, handle: futures_util::future::AbortHandle) {
        if let Some(previous) = self.requests.lock().unwrap().insert(id, handle) {
            previous.abort();
        }
    }

    pub fn finish(&self, id: &str) {
        self.requests.lock().unwrap().remove(id);
    }

    pub(super) fn stop_watch(&self) {
        if let Some(task) = self.event_task.lock().unwrap().take() {
            task.abort();
        }
        self.watch.lock().unwrap().take();
    }

    pub(super) fn change(&self, watch: &Watch, change: &Change) -> bool {
        if change.source.bus != watch.app.bus {
            return false;
        }
        if !watch.bindings.is_empty() {
            if watch.bindings.iter().any(|b| {
                std::iter::once(&b.handle)
                    .chain(b.ancestors.iter().map(|(_, h)| h))
                    .any(|h| h.bus == change.source.bus && h.path == change.source.path)
            }) {
                return true;
            }
            let store = self.store.lock().unwrap();
            return store.snapshots.iter().any(|s| {
                let Some((node, _)) = s
                    .nodes
                    .iter()
                    .find(|(_, h)| h.bus == change.source.bus && h.path == change.source.path)
                else {
                    return false;
                };
                let mut parent = node.parent_ref.as_deref();
                for _ in 0..s.nodes.len() {
                    let Some((node, handle)) =
                        parent.and_then(|r| s.nodes.iter().find(|(n, _)| n.reference == r))
                    else {
                        break;
                    };
                    if watch.bindings.iter().any(|b| {
                        b.ancestors
                            .last()
                            .is_some_and(|(_, h)| h.bus == handle.bus && h.path == handle.path)
                    }) {
                        return true;
                    }
                    parent = node.parent_ref.as_deref();
                }
                false
            });
        }
        if (change.reconcile && watch.scopes.is_empty()) || watch.refs.is_empty() {
            return true;
        }
        let references = if change.reconcile {
            &watch.scopes
        } else {
            &watch.refs
        };
        let store = self.store.lock().unwrap();
        // Ancestor events can summarize a change in a watched descendant.
        store
            .snapshots
            .iter()
            .filter(|s| s.app.bus == watch.app.bus)
            .any(|s| {
                s.nodes.iter().any(|(n, h)| {
                    if h.path != change.source.path {
                        return false;
                    }
                    let mut reference = Some(n.reference.as_str());
                    for _ in 0..s.nodes.len() {
                        let Some(r) = reference else {
                            break;
                        };
                        if references.iter().any(|watched| watched == r) {
                            return true;
                        }
                        reference = s
                            .nodes
                            .iter()
                            .find(|(n, _)| n.reference == r)
                            .and_then(|(n, _)| n.parent_ref.as_deref());
                    }
                    references.iter().any(|watched| {
                        let mut reference = Some(watched.as_str());
                        for _ in 0..s.nodes.len() {
                            let Some(r) = reference else {
                                break;
                            };
                            if r == n.reference {
                                return true;
                            }
                            reference = s
                                .nodes
                                .iter()
                                .find(|(n, _)| n.reference == r)
                                .and_then(|(n, _)| n.parent_ref.as_deref());
                        }
                        false
                    })
                })
            })
    }

    pub(super) fn watch_scopes(&self, refs: &[String], path: &[String]) -> Vec<String> {
        if path.is_empty() {
            return Vec::new();
        }
        let store = self.store.lock().unwrap();
        let scopes: Option<Vec<String>> = refs
            .iter()
            .map(|reference| {
                let snapshot = store
                    .snapshots
                    .iter()
                    .find(|s| s.nodes.iter().any(|(n, _)| &n.reference == reference))?;
                let mut ancestors = Vec::new();
                let mut reference = snapshot
                    .nodes
                    .iter()
                    .find(|(n, _)| &n.reference == reference)
                    .and_then(|(n, _)| n.parent_ref.as_deref());
                for _ in 0..snapshot.nodes.len() {
                    let Some((node, _)) = reference
                        .and_then(|r| snapshot.nodes.iter().find(|(n, _)| n.reference == r))
                    else {
                        break;
                    };
                    ancestors.push(node);
                    reference = node.parent_ref.as_deref();
                }
                ancestors.reverse();
                let mut index = 0;
                for node in ancestors {
                    if path
                        .get(index)
                        .is_some_and(|part| path_part_matches(node, part))
                    {
                        index += 1;
                        if index == path.len() {
                            return Some(node.reference.clone());
                        }
                    }
                }
                None
            })
            .collect();
        scopes.unwrap_or_default()
    }

    pub async fn start_events(state: Arc<State>) -> bool {
        if !state.a11y.sensor.supports_events() {
            return false;
        }
        let Some(watch) = state.a11y.watch.lock().unwrap().clone() else {
            return false;
        };
        let (ready, registered) = oneshot::channel();
        let owner = state.clone();
        let task = tokio::spawn(async move {
            let (tx, mut rx) = mpsc::channel(128);
            let subscription = owner.a11y.sensor.subscribe(tx, ready);
            tokio::pin!(subscription);
            let mut sequence = 0_u64;
            loop {
                tokio::select! {
                    _ = &mut subscription => {
                        let _ = owner.send("a11y.event", json!({"watch_id":watch.id,
                            "sequence":sequence + 1,"refs":[],"reconcile":true,"events_supported":false}), None);
                        break;
                    }
                    change = rx.recv() => {
                        let Some(change) = change else { break; };
                        let Some(watch) = owner.a11y.watch.lock().unwrap().clone().filter(|w| w.id == watch.id) else { break; };
                        if change.source.bus == watch.app.bus {
                            owner.a11y.invalidate_collection();
                        }
                        if change.focus {
                            crate::discovery::poll(&owner, &mut None).await;
                        }
                        let accepted = owner.a11y.change(&watch, &change);
                        if change.reconcile && std::env::var_os("RIO_A11Y_TRACE").is_some() {
                            let store = owner.a11y.store.lock().unwrap();
                            let role = store.snapshots.iter().flat_map(|s| &s.nodes)
                                .find(|(_, h)| h.bus == change.source.bus && h.path == change.source.path)
                                .map(|(n, _)| n.role.as_str()).unwrap_or("unmapped");
                            eprintln!("a11y structural accepted={accepted} role={role} source={}:{}", change.source.bus, change.source.path);
                        }
                        if !accepted { continue; }
                        let scoped = change.scoped && !watch.bindings.is_empty()
                            && watch.bindings.len() == watch.refs.len();
                        if change.reconcile {
                            let mut store = owner.a11y.store.lock().unwrap();
                            store.snapshots.clear();
                            store.epoch = store.epoch.wrapping_add(1);
                        }
                        if change.reconcile && !scoped {
                            if let Some(watch) = owner.a11y.watch.lock().unwrap().as_mut() { watch.bindings.clear(); }
                        }
                        sequence += 1;
                        let _ = owner.send("a11y.event", json!({"watch_id":watch.id,
                            "sequence":sequence,"refs":watch.refs,"reconcile":change.reconcile,
                            "events_supported":true,"scoped":scoped}), None);
                    }
                }
            }
        });
        *state.a11y.event_task.lock().unwrap() = Some(task.abort_handle());
        matches!(
            tokio::time::timeout(Duration::from_secs(1), registered).await,
            Ok(Ok(true))
        )
    }
}
