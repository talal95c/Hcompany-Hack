use super::*;
use std::collections::HashMap;
use std::sync::{mpsc, OnceLock};

type Job<C> = Box<dyn FnOnce(&mut Result<C, Error>) + Send>;
pub struct Worker<C> {
    sender: OnceLock<mpsc::SyncSender<Job<C>>>,
}
impl<C> Default for Worker<C> {
    fn default() -> Self {
        Self {
            sender: OnceLock::new(),
        }
    }
}
impl<C: 'static> Worker<C> {
    pub async fn call<R: Send + 'static>(
        &self,
        init: fn() -> Result<C, Error>,
        work: impl FnOnce(&mut C) -> Result<R, Error> + Send + 'static,
    ) -> Result<R, Error> {
        let sender = self.sender.get_or_init(|| {
            let (tx, rx) = mpsc::sync_channel::<Job<C>>(16);
            tokio::task::spawn_blocking(move || {
                let mut context = init();
                while let Ok(job) = rx.recv() {
                    job(&mut context);
                }
            });
            tx
        });
        let (tx, rx) = tokio::sync::oneshot::channel();
        sender
            .try_send(Box::new(move |context| {
                if tx.is_closed() {
                    return;
                }
                let result = match context {
                    Ok(context) => work(context),
                    Err(error) => Err(*error),
                };
                let _ = tx.send(result);
            }))
            .map_err(|_| Error::PermissionDenied)?;
        rx.await.map_err(|_| Error::PermissionDenied)?
    }
    #[cfg(any(target_os = "macos", target_os = "windows"))]
    pub async fn action(
        &self,
        init: fn() -> Result<C, Error>,
        guard: &input::ActionGuard<'_>,
        work: impl FnOnce(&mut C, input::Authorization) -> Result<(), Error> + Send + 'static,
    ) -> Result<(), Error> {
        let authorization = guard.authorization().map_err(Error::guard)?;
        let lease = Cancellation(std::sync::Arc::new(std::sync::atomic::AtomicBool::new(
            false,
        )));
        let cancelled = lease.0.clone();
        let check: input::Authorization =
            std::sync::Arc::new(move || authorize(&cancelled, || authorization()));
        let result = self
            .call(init, move |context| {
                check().map_err(Error::guard)?;
                work(context, check)
            })
            .await;
        drop(lease);
        result
    }
}
fn authorize(
    cancelled: &std::sync::atomic::AtomicBool,
    check: impl FnOnce() -> Result<(), String>,
) -> Result<(), String> {
    if cancelled.load(std::sync::atomic::Ordering::SeqCst) {
        return Err("stopped".into());
    }
    check()?;
    if cancelled.load(std::sync::atomic::Ordering::SeqCst) {
        return Err("stopped".into());
    }
    Ok(())
}
#[cfg(any(test, target_os = "macos", target_os = "windows"))]
struct Cancellation(std::sync::Arc<std::sync::atomic::AtomicBool>);
impl Drop for Cancellation {
    fn drop(&mut self) {
        self.0.store(true, std::sync::atomic::Ordering::SeqCst);
    }
}

pub struct Registry<T> {
    entries: HashMap<String, (u32, Instant, T)>,
}
impl<T> Default for Registry<T> {
    fn default() -> Self {
        Self {
            entries: HashMap::new(),
        }
    }
}
impl<T: Clone> Registry<T> {
    pub fn insert(&mut self, pid: u32, value: T) -> Handle {
        self.entries
            .retain(|_, (_, at, _)| at.elapsed() < Duration::from_secs(35));
        if self.entries.len() >= 10000 {
            if let Some(key) = self
                .entries
                .iter()
                .min_by_key(|(_, (_, at, _))| *at)
                .map(|(key, _)| key.clone())
            {
                self.entries.remove(&key);
            }
        }
        let path = uuid::Uuid::new_v4().to_string();
        self.entries
            .insert(path.clone(), (pid, Instant::now(), value));
        Handle {
            bus: pid.to_string(),
            path,
        }
    }
    pub fn get(&self, handle: &Handle) -> Result<T, Error> {
        self.entries
            .get(&handle.path)
            .filter(|(pid, at, _)| {
                handle.bus == pid.to_string() && at.elapsed() < Duration::from_secs(35)
            })
            .map(|(_, _, value)| value.clone())
            .ok_or(Error::StaleRef)
    }
}

pub struct Observation {
    pub node: Node,
    pub children: Vec<Handle>,
    pub visible: bool,
    pub reasons: Vec<Reason>,
}
pub fn walk(
    root: Handle,
    depth: usize,
    deadline: Instant,
    mut read: impl FnMut(&Handle, bool, Instant) -> Result<Observation, Error>,
) -> Result<Tree, Error> {
    let mut tree = Tree {
        nodes: vec![],
        complete: true,
        reasons: BTreeMap::new(),
    };
    let mut queue: VecDeque<(Handle, Option<usize>, usize)> = VecDeque::from([(root, None, 0)]);
    while let Some((handle, parent, level)) = queue.pop_front() {
        if Instant::now() >= deadline {
            tree.record(Reason::Deadline, "unknown");
            break;
        }
        if tree.nodes.len() >= 2000 {
            tree.record(Reason::NodeCap, "unknown");
            break;
        }
        let observation = match read(&handle, level < depth, deadline) {
            Ok(value) => value,
            Err(Error::Timeout) => {
                tree.record(Reason::Deadline, "unknown");
                break;
            }
            Err(Error::StaleRef) => {
                tree.record(Reason::DefunctSkipped, "unknown");
                continue;
            }
            Err(error) => {
                if level == 0 {
                    return Err(error);
                }
                tree.record(Reason::ChildReadError, "unknown");
                continue;
            }
        };
        let Observation {
            mut node,
            children,
            visible,
            reasons,
        } = observation;
        for reason in reasons {
            tree.record(reason, &node.role);
        }
        if !visible {
            tree.record(Reason::InvisibleSkipped, &node.role);
            continue;
        }
        let mut next_parent = parent;
        if !valid_bounds(node.bounds) {
            if children.is_empty() {
                continue;
            }
            if let Some(parent) = parent {
                node.bounds = tree.nodes[parent].node.bounds;
            } else {
                for child in children {
                    queue.push_back((child, None, level + 1));
                }
                continue;
            }
        }
        if valid_bounds(node.bounds) {
            node.protect();
            next_parent = Some(tree.nodes.len());
            tree.nodes.push(RawNode {
                node,
                handle,
                parent,
            });
        }
        for child in children {
            if queue.len() >= 8192 {
                tree.record(Reason::NodeCap, "unknown");
                break;
            }
            queue.push_back((child, next_parent, level + 1));
        }
    }
    Ok(tree)
}
pub fn valid_bounds(bounds: Bounds) -> bool {
    crate::coordinates::Rect {
        x: bounds.x,
        y: bounds.y,
        width: bounds.w,
        height: bounds.h,
    }
    .valid()
}

#[cfg(any(test, target_os = "macos"))]
pub fn ax_role(role: &str, subrole: &str) -> &'static str {
    match (role, subrole) {
        (_, "AXSecureTextField") | ("AXSecureTextField", _) => "text",
        (_, "AXToggleButton") => "toggle_button",
        ("AXButton", _) => "button",
        ("AXCheckBox", _) => "check_box",
        ("AXRadioButton", _) => "radio_button",
        ("AXTextField" | "AXTextArea" | "AXStaticText", _) => "text",
        ("AXTable", _) => "table",
        ("AXCell", _) => "table_cell",
        ("AXRow", _) => "row",
        ("AXColumn", _) => "column",
        ("AXOutline", _) => "tree",
        ("AXWindow", _) => "frame",
        ("AXToolbar", _) => "toolbar",
        ("AXMenu", _) => "menu",
        ("AXMenuBar", _) => "menu_bar",
        ("AXMenuItem", _) => "menu_item",
        ("AXComboBox", _) => "combo_box",
        ("AXPopUpButton", _) => "combo_box",
        ("AXScrollArea", _) => "scroll_pane",
        ("AXScrollBar", _) => "scroll_bar",
        ("AXSlider", _) => "slider",
        ("AXLink", _) => "link",
        ("AXImage", _) => "image",
        ("AXTabGroup", _) => "tab_list",
        ("AXApplication", _) => "application",
        ("AXGroup", _) => "panel",
        _ => "unknown",
    }
}
#[cfg(any(test, target_os = "windows"))]
pub fn uia_end(code: i32) -> bool {
    matches!(code, 0 | 1 | 5)
}

#[cfg(any(test, target_os = "windows"))]
pub fn uia_role(control: i32, toggle: bool) -> &'static str {
    match control {
        50000 if toggle => "toggle_button",
        50000 => "button",
        50002 => "check_box",
        50003 => "combo_box",
        50004 | 50020 => "text",
        50005 => "link",
        50006 => "image",
        50007 => "list_item",
        50029 => "table_cell",
        50008 => "list",
        50009 => "menu",
        50010 => "menu_bar",
        50011 => "menu_item",
        50012 => "progress_bar",
        50013 => "radio_button",
        50014 => "scroll_bar",
        50015 => "slider",
        50016 => "spin_button",
        50018 => "tab_list",
        50019 => "tab",
        50021 => "toolbar",
        50023 => "tree",
        50024 => "tree_item",
        50028 | 50036 => "table",
        50026 | 50033 => "panel",
        50030 => "text",
        50032 => "frame",
        50034 => "header",
        50035 => "column_header",
        50038 => "separator",
        _ => "unknown",
    }
}
pub fn secure_field(role: &str, subrole: &str, password: bool) -> bool {
    password || role == "AXSecureTextField" || subrole == "AXSecureTextField"
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn traversal_flattens_application_roots_redacts_and_counts_truncation() {
        let root = Handle {
            bus: "42".into(),
            path: "app".into(),
        };
        let read = |handle: &Handle, children: bool, _: Instant| {
            Ok(Observation {
                node: Node {
                    reference: String::new(),
                    role: "text".into(),
                    name: String::new(),
                    value: Some("private fixture".into()),
                    secure: true,
                    states: vec![],
                    bounds: Bounds {
                        x: 0.,
                        y: 0.,
                        w: if handle.path == "app" { 0. } else { 10. },
                        h: 10.,
                    },
                    parent_ref: None,
                },
                visible: true,
                children: if handle.path == "app" && children {
                    vec![Handle {
                        bus: "42".into(),
                        path: "child".into(),
                    }]
                } else {
                    vec![]
                },
                reasons: if !children && handle.path == "app" {
                    vec![Reason::DepthLimit]
                } else {
                    vec![]
                },
            })
        };
        let tree = walk(
            root.clone(),
            2,
            Instant::now() + Duration::from_secs(1),
            read,
        )
        .unwrap();
        assert!(tree.complete);
        assert_eq!(tree.nodes.len(), 1);
        assert!(tree.nodes[0].node.value.is_none());
        assert!(tree.nodes[0].parent.is_none());
        assert!(valid_bounds(tree.nodes[0].node.bounds));
        assert!(
            !walk(
                root.clone(),
                0,
                Instant::now() + Duration::from_secs(1),
                read
            )
            .unwrap()
            .complete
        );
        assert!(
            !walk(root.clone(), 2, Instant::now(), read)
                .unwrap()
                .complete
        );
        assert!(walk(
            root,
            2,
            Instant::now() + Duration::from_secs(1),
            |_, _, _| Err(Error::PermissionDenied)
        )
        .is_err());
    }
    #[test]
    fn mappings_and_secure_rules() {
        assert!(uia_end(0));
        assert!(uia_end(5));
        assert!(!uia_end(0x80040201u32 as i32));
        assert_eq!(ax_role("AXButton", ""), "button");
        assert_eq!(ax_role("AXTextField", "AXSecureTextField"), "text");
        assert_eq!(ax_role("AXTable", ""), "table");
        assert_eq!(ax_role("FutureRole", ""), "unknown");
        assert_eq!(uia_role(50000, true), "toggle_button");
        assert_eq!(uia_role(50000, false), "button");
        assert_eq!(uia_role(50036, false), "table");
        assert_eq!(uia_role(-1, false), "unknown");
        assert!(secure_field("AXTextField", "AXSecureTextField", false));
        assert!(secure_field("", "", true));
        assert!(!secure_field("AXTextField", "", false));
    }
    #[tokio::test]
    async fn worker_owns_native_objects_on_one_thread_and_preserves_typed_errors() {
        let worker = Worker::default();
        fn init() -> Result<std::thread::ThreadId, Error> {
            Ok(std::thread::current().id())
        }
        let first = worker.call(init, |id| Ok(*id)).await.unwrap();
        let second = worker.call(init, |id| Ok(*id)).await.unwrap();
        assert_eq!(first, second);
        assert!(matches!(
            worker.call(init, |_| Err::<(), _>(Error::StaleRef)).await,
            Err(Error::StaleRef)
        ));
    }
    #[test]
    fn registry_scopes_expires_and_cancellation_is_fail_closed() {
        let mut registry = Registry::default();
        let mut handle = registry.insert(42, 7);
        assert_eq!(registry.get(&handle).unwrap(), 7);
        handle.bus = "43".into();
        assert!(registry.get(&handle).is_err());
        handle.bus = "42".into();
        registry.entries.get_mut(&handle.path).unwrap().1 =
            Instant::now() - Duration::from_secs(36);
        assert!(registry.get(&handle).is_err());
        let flag = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
        assert!(authorize(&flag, || {
            flag.store(true, std::sync::atomic::Ordering::SeqCst);
            Ok(())
        })
        .is_err());
        drop(Cancellation(flag.clone()));
        assert!(flag.load(std::sync::atomic::Ordering::SeqCst));
    }
}
