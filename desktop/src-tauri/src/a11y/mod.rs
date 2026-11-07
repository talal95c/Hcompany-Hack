use crate::{input, State};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, VecDeque},
    fmt,
    future::Future,
    pin::Pin,
    sync::Mutex,
    time::{Duration, Instant},
};
#[cfg(test)]
mod tests;

#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "linux")]
use linux::Sensor;
#[cfg(target_os = "macos")]
mod macos;
#[cfg(any(test, target_os = "macos", target_os = "windows"))]
mod platform;
#[cfg(target_os = "macos")]
use macos::Sensor;
#[cfg(target_os = "windows")]
mod windows;
#[cfg(target_os = "windows")]
use windows::Sensor;
#[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
mod unsupported;
#[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
use unsupported::Sensor;

type Task<'a, T> = Pin<Box<dyn Future<Output = Result<T, Error>> + Send + 'a>>;

#[derive(Clone)]
pub struct Handle {
    pub bus: String,
    pub path: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Error {
    StaleRef,
    AmbiguousTarget,
    AppNotFound,
    PermissionDenied,
    Timeout,
    FocusLost,
}
impl Error {
    fn code(self) -> &'static str {
        match self {
            Self::StaleRef => "STALE_REF",
            Self::AmbiguousTarget => "AMBIGUOUS_TARGET",
            Self::AppNotFound => "APP_NOT_FOUND",
            Self::PermissionDenied | Self::FocusLost => "PERMISSION_DENIED",
            Self::Timeout => "TIMEOUT",
        }
    }
    fn message(self) -> &'static str {
        match self {
            Self::StaleRef => "Référence périmée.",
            Self::AmbiguousTarget => "Plusieurs cibles correspondent.",
            Self::AppNotFound => "Application introuvable.",
            Self::PermissionDenied => "Accès ou action non autorisé.",
            Self::Timeout => "Délai dépassé.",
            Self::FocusLost => "focus lost",
        }
    }
}

impl Error {
    fn guard(message: String) -> Self {
        if message == "focus lost" {
            Self::FocusLost
        } else {
            Self::PermissionDenied
        }
    }
}

#[derive(Debug, Clone, Copy, Serialize)]
pub struct Bounds {
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

#[derive(Clone, Serialize)]
pub struct Node {
    #[serde(skip)]
    pub secure: bool,
    #[serde(rename = "ref")]
    pub reference: String,
    pub role: String,
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub value: Option<String>,
    pub states: Vec<String>,
    pub bounds: Bounds,
    pub parent_ref: Option<String>,
}
impl fmt::Debug for Node {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Node")
            .field("ref", &self.reference)
            .field("role", &self.role)
            .field("value", &"[redacted]")
            .finish_non_exhaustive()
    }
}
impl Node {
    fn protect(&mut self) {
        if self.secure {
            self.value = None;
        }
    }
    fn allow_action(&self, action: &str) -> Result<(), Error> {
        if self.secure && action == "set_value" {
            Err(Error::PermissionDenied)
        } else {
            Ok(())
        }
    }
}

pub struct RawNode {
    pub node: Node,
    pub handle: Handle,
    pub parent: Option<usize>,
}
pub struct Tree {
    pub nodes: Vec<RawNode>,
    pub complete: bool,
    pub reasons: BTreeMap<(Reason, String), usize>,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Reason {
    DepthLimit,
    NodeCap,
    Deadline,
    ChildReadError,
    LargeContainerSkipped,
    InvisibleSkipped,
    DefunctSkipped,
}
impl Tree {
    fn record(&mut self, reason: Reason, role: &str) {
        *self.reasons.entry((reason, role.to_owned())).or_default() += 1;
        if !matches!(reason, Reason::InvisibleSkipped | Reason::DefunctSkipped) {
            self.complete = false;
        }
    }
}
pub struct App {
    pub app_id: String,
    pub handle: Handle,
    pub name: String,
    pub executable: String,
    pub pid: u32,
    pub focused: bool,
}

pub trait AccessibilitySensor: Send + Sync {
    fn apps(&self) -> Task<'_, Vec<App>>;
    fn snapshot<'a>(&'a self, root: &'a Handle, depth: usize, deadline: Instant) -> Task<'a, Tree>;
    fn refresh<'a>(&'a self, handle: &'a Handle) -> Task<'a, Node>;
    fn action<'a>(
        &'a self,
        handle: &'a Handle,
        action: &'a str,
        value: Option<&'a str>,
        guard: &'a input::ActionGuard<'a>,
    ) -> Task<'a, ()>;
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    request_id: String,
    op: String,
    app: String,
    root: Option<String>,
    query: Option<Query>,
    #[serde(rename = "ref")]
    reference: Option<String>,
    action: Option<String>,
    value: Option<String>,
    max_depth: Option<usize>,
    consent_token: Option<String>,
}
#[derive(Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct Query {
    role: Option<String>,
    name: Option<String>,
    path: Option<Vec<String>>,
    value: Option<String>,
    states: Option<Vec<String>>,
}

struct Snapshot {
    id: String,
    app: Handle,
    at: Instant,
    nodes: Vec<(Node, Handle)>,
    reasons: BTreeMap<(Reason, String), usize>,
}
#[derive(Default)]
struct Store {
    snapshots: VecDeque<Snapshot>,
    epoch: u64,
}
impl Store {
    fn prune(&mut self) {
        self.snapshots
            .retain(|s| s.at.elapsed() < Duration::from_secs(30));
        while self.snapshots.len() > 4 {
            self.snapshots.pop_front();
        }
    }
    fn insert(&mut self, app: Handle, tree: Tree) -> (String, Vec<Node>) {
        let id = uuid::Uuid::new_v4().to_string();
        let nodes: Vec<_> = tree
            .nodes
            .into_iter()
            .enumerate()
            .map(|(i, raw)| {
                let mut n = raw.node;
                n.protect();
                n.reference = format!("{id}:n{i}");
                n.parent_ref = raw.parent.map(|p| format!("{id}:n{p}"));
                (n, raw.handle)
            })
            .collect();
        let result = nodes.iter().map(|(n, _)| n.clone()).collect();
        self.snapshots.push_back(Snapshot {
            id: id.clone(),
            app,
            at: Instant::now(),
            nodes,
            reasons: tree.reasons,
        });
        self.prune();
        log::debug!(
            "a11y snapshot reasons={:?}",
            self.snapshots.back().map(|s| &s.reasons)
        );
        (id, result)
    }
    fn get(&mut self, reference: &str, app: &Handle) -> Result<(String, Node, Handle), Error> {
        self.prune();
        for s in &self.snapshots {
            if s.app.bus != app.bus || s.app.path != app.path {
                continue;
            }
            if let Some((n, h)) = s.nodes.iter().find(|(n, _)| n.reference == reference) {
                return Ok((s.id.clone(), n.clone(), h.clone()));
            }
        }
        Err(Error::StaleRef)
    }
}

pub fn normalize_role(role: &str) -> String {
    let role = role.to_lowercase().replace([' ', '-'], "_");
    match role.as_str() {
        "push_button" => "button",
        "checkbutton" | "checkbox" => "check_box",
        "entry" | "password_text" => "text",
        "tool_bar" => "toolbar",
        _ => &role,
    }
    .to_owned()
}

fn matches(nodes: &[Node], q: &Query) -> Vec<Node> {
    let mut candidates: Vec<_> = nodes
        .iter()
        .filter(|n| {
            if q.role.as_ref().is_some_and(|r| normalize_role(r) != n.role)
                || q.value
                    .as_ref()
                    .is_some_and(|v| n.value.as_ref() != Some(v))
                || q.states
                    .as_ref()
                    .is_some_and(|s| !s.iter().all(|v| n.states.contains(v)))
            {
                return false;
            }
            if let Some(path) = &q.path {
                let mut ancestors = Vec::new();
                let mut parent = n.parent_ref.as_ref();
                for _ in 0..nodes.len() {
                    let Some(p) = parent.and_then(|r| nodes.iter().find(|a| &a.reference == r))
                    else {
                        break;
                    };
                    ancestors.push(p);
                    parent = p.parent_ref.as_ref();
                }
                ancestors.reverse();
                let mut index = 0;
                for a in ancestors {
                    if let Some(part) = path.get(index) {
                        if a.name.eq_ignore_ascii_case(part)
                            || a.role == normalize_role(part)
                            || part.split_once(':').is_some_and(|(role, name)| {
                                a.role == normalize_role(role) && a.name.eq_ignore_ascii_case(name)
                            })
                        {
                            index += 1;
                        }
                    }
                }
                if index != path.len() {
                    return false;
                }
            }
            true
        })
        .cloned()
        .collect();
    if let Some(name) = &q.name {
        let name = name.to_lowercase();
        let exact = candidates.iter().any(|n| n.name.to_lowercase() == name);
        candidates.retain(|n| {
            if exact {
                n.name.to_lowercase() == name
            } else {
                n.name.to_lowercase().contains(&name)
            }
        });
    }
    candidates
}

pub struct Service {
    sensor: Box<dyn AccessibilitySensor>,
    store: Mutex<Store>,
}
impl Default for Service {
    fn default() -> Self {
        Self {
            sensor: Box::new(Sensor::default()),
            store: Mutex::new(Store::default()),
        }
    }
}
impl Service {
    pub async fn highlight_bounds(
        &self,
        reference: &str,
        snapshot: &str,
        requested_app: Option<&str>,
    ) -> Result<crate::coordinates::Rect, Error> {
        let (epoch, app) = {
            let mut store = self.store.lock().unwrap();
            store.prune();
            let retained = store
                .snapshots
                .iter()
                .find(|s| s.id == snapshot)
                .ok_or(Error::StaleRef)?;
            (store.epoch, retained.app.clone())
        };
        if let Some(requested) = requested_app {
            let actual = self.resolve_app(requested).await?;
            if actual.handle.bus != app.bus || actual.handle.path != app.path {
                return Err(Error::StaleRef);
            }
        }
        let handle = {
            let mut store = self.store.lock().unwrap();
            let (id, _, handle) = store.get(reference, &app)?;
            if id != snapshot {
                return Err(Error::StaleRef);
            }
            handle
        };
        let node = self.sensor.refresh(&handle).await?;
        let mut store = self.store.lock().unwrap();
        if store.epoch != epoch {
            return Err(Error::StaleRef);
        }
        store.get(reference, &app)?;
        Ok(crate::coordinates::Rect {
            x: node.bounds.x,
            y: node.bounds.y,
            width: node.bounds.w,
            height: node.bounds.h,
        })
    }
    pub async fn applications(&self) -> Result<Vec<App>, Error> {
        self.sensor.apps().await
    }
    pub fn clear(&self) {
        let mut store = self.store.lock().unwrap();
        store.snapshots.clear();
        store.epoch = store.epoch.wrapping_add(1);
    }
    pub async fn request(&self, state: &State, payload: Value) -> Value {
        self.run(Some(state), payload).await
    }
    async fn run(&self, state: Option<&State>, payload: Value) -> Value {
        let deadline = Instant::now() + Duration::from_secs(3);
        let request_id = payload["request_id"]
            .as_str()
            .unwrap_or("invalid")
            .to_owned();
        let result = async {
            let validating = Instant::now();
            crate::protocol::validate(
                &crate::protocol::envelope("a11y", "a11y.request", payload.clone(), None),
                "a11y",
            )
            .map_err(|_| Error::PermissionDenied)?;
            let r: Request =
                serde_json::from_value(payload).map_err(|_| Error::PermissionDenied)?;
            log::debug!(
                "a11y validation_ms={:.3}",
                validating.elapsed().as_secs_f64() * 1000.
            );
            self.execute(state, r, deadline).await
        };
        match tokio::time::timeout_at(deadline.into(), result).await {
            Ok(Ok(v)) => v,
            error => {
                let e = match error {
                    Ok(Err(e)) => e,
                    _ => Error::Timeout,
                };
                json!({"request_id":request_id,"snapshot_id":null,"complete":false,"nodes":[],"error":{"code":e.code(),"message":e.message()}})
            }
        }
    }
    #[cfg(test)]
    async fn resolve(&self, requested: &str) -> Result<Handle, Error> {
        Ok(self.resolve_app(requested).await?.handle)
    }
    async fn resolve_app(&self, requested: &str) -> Result<App, Error> {
        let apps = self.sensor.apps().await?;
        apps.into_iter()
            .find(|a| {
                if requested.eq_ignore_ascii_case("focused") {
                    a.focused && a.pid != std::process::id()
                } else {
                    a.app_id.eq_ignore_ascii_case(requested)
                        || a.name.eq_ignore_ascii_case(requested)
                        || a.executable.eq_ignore_ascii_case(requested)
                        || a.pid.to_string() == requested
                }
            })
            .ok_or(Error::AppNotFound)
    }
    async fn execute(
        &self,
        state: Option<&State>,
        r: Request,
        deadline: Instant,
    ) -> Result<Value, Error> {
        let epoch = self.store.lock().unwrap().epoch;
        let guard = if r.op == "action" {
            Some(
                input::guard(
                    state.ok_or(Error::PermissionDenied)?,
                    r.consent_token.as_deref().unwrap_or(""),
                )
                .map_err(Error::guard)?,
            )
        } else {
            None
        };
        let resolving = Instant::now();
        let resolved = self.resolve_app(&r.app).await?;
        log::debug!(
            "a11y resolve_ms={:.3}",
            resolving.elapsed().as_secs_f64() * 1000.
        );
        if let Some(guard) = &guard {
            guard.require_pid(resolved.pid).map_err(Error::guard)?;
        }
        let app = resolved.handle;
        if r.op == "get" || r.op == "action" {
            let (id, old, handle) = self
                .store
                .lock()
                .unwrap()
                .get(r.reference.as_deref().ok_or(Error::StaleRef)?, &app)?;
            let mut node = if r.op == "action" {
                self.act(
                    &handle,
                    r.action.as_deref().unwrap_or(""),
                    r.value.as_deref(),
                    guard.as_ref().ok_or(Error::PermissionDenied)?,
                )
                .await?
            } else {
                self.sensor.refresh(&handle).await?
            };
            node.protect();
            node.reference = old.reference;
            node.parent_ref = old.parent_ref;
            if self.store.lock().unwrap().epoch != epoch {
                return Err(Error::StaleRef);
            }
            return Ok(
                json!({"request_id":r.request_id,"snapshot_id":id,"complete":true,"nodes":[node]}),
            );
        }
        let root = if let Some(root) = r.root {
            self.store.lock().unwrap().get(&root, &app)?.2
        } else {
            app.clone()
        };
        let tree = self
            .sensor
            .snapshot(
                &root,
                r.max_depth.unwrap_or(32).clamp(1, 64),
                deadline - Duration::from_millis(100),
            )
            .await?;
        if tree.nodes.is_empty()
            && tree
                .reasons
                .keys()
                .any(|(reason, _)| *reason == Reason::Deadline)
        {
            return Err(Error::Timeout);
        }
        let complete = tree.complete;
        let (id, nodes) = {
            let mut store = self.store.lock().unwrap();
            if store.epoch != epoch {
                return Err(Error::StaleRef);
            }
            store.insert(app, tree)
        };
        let mut nodes = if r.op == "find" {
            matches(&nodes, r.query.as_ref().ok_or(Error::PermissionDenied)?)
        } else {
            nodes
        };
        if r.op == "find" && nodes.len() > 1 {
            nodes.truncate(10);
            let e = Error::AmbiguousTarget;
            return Ok(
                json!({"request_id":r.request_id,"snapshot_id":id,"complete":false,"nodes":nodes,"error":{"code":e.code(),"message":e.message()}}),
            );
        }
        Ok(json!({"request_id":r.request_id,"snapshot_id":id,"complete":complete,"nodes":nodes}))
    }

    async fn act<'a>(
        &'a self,
        handle: &'a Handle,
        action: &'a str,
        value: Option<&'a str>,
        guard: &'a input::ActionGuard<'a>,
    ) -> Result<Node, Error> {
        guard.check().map_err(Error::guard)?;
        self.sensor.refresh(handle).await?.allow_action(action)?;
        self.sensor.action(handle, action, value, guard).await?;
        let mut node = self.sensor.refresh(handle).await?;
        node.protect();
        Ok(node)
    }
}
