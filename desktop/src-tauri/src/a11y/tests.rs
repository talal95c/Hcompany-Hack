use super::*;
use std::sync::{
    atomic::{AtomicBool, AtomicUsize, Ordering},
    Arc,
};
use tokio::sync::Notify;

#[derive(Clone, Copy)]
enum Scenario {
    Normal,
    Empty,
    Ambiguous,
    Incomplete,
    NativeFailure,
    Defunct,
    Timeout,
    PausedSnapshot,
    PausedRefresh,
    Secure,
}
#[derive(Default)]
struct Control {
    started: Notify,
    resume: Notify,
    actions: AtomicUsize,
}
struct Mock {
    scenario: Scenario,
    control: Arc<Control>,
}
impl AccessibilitySensor for Mock {
    fn apps(&self) -> Task<'_, Vec<App>> {
        Box::pin(async {
            Ok(vec![App {
                handle: app(),
                name: "Editor".into(),
                executable: "editor-bin".into(),
                pid: 42,
                focused: true,
            }])
        })
    }
    fn snapshot<'a>(&'a self, _: &'a Handle, _: usize, _: Instant) -> Task<'a, Tree> {
        Box::pin(async move {
            if matches!(self.scenario, Scenario::Timeout) {
                return std::future::pending().await;
            }
            if matches!(self.scenario, Scenario::PausedSnapshot) {
                self.control.started.notify_one();
                self.control.resume.notified().await;
            }
            if matches!(self.scenario, Scenario::NativeFailure) {
                return Err(Error::PermissionDenied);
            }
            let mut result = tree();
            match self.scenario {
                Scenario::Empty => result.nodes.clear(),
                Scenario::Ambiguous => {
                    result.nodes = (0..12)
                        .map(|_| RawNode {
                            node: node("Save"),
                            handle: app(),
                            parent: None,
                        })
                        .collect();
                }
                Scenario::Incomplete => result.record(Reason::NodeCap, "button"),
                Scenario::Secure => result.nodes[0].node.secure = true,
                _ => {}
            }
            Ok(result)
        })
    }
    fn refresh<'a>(&'a self, _: &'a Handle) -> Task<'a, Node> {
        Box::pin(async move {
            if matches!(self.scenario, Scenario::Defunct) {
                return Err(Error::StaleRef);
            }
            if matches!(self.scenario, Scenario::PausedRefresh) {
                self.control.started.notify_one();
                self.control.resume.notified().await;
            }
            Ok(Node {
                secure: matches!(self.scenario, Scenario::Secure),
                value: Some("fresh-value".into()),
                ..node("Save")
            })
        })
    }
    fn action<'a>(
        &'a self,
        _: &'a Handle,
        action: &'a str,
        _: Option<&'a str>,
        guard: &'a input::ActionGuard<'a>,
    ) -> Task<'a, ()> {
        Box::pin(async move {
            guard.check().map_err(|_| Error::PermissionDenied)?;
            if action == "unsupported" {
                return Err(Error::PermissionDenied);
            }
            self.control.actions.fetch_add(1, Ordering::SeqCst);
            Ok(())
        })
    }
}
fn service(scenario: Scenario) -> (Arc<Service>, Arc<Control>) {
    let control = Arc::new(Control::default());
    (
        Arc::new(Service {
            sensor: Box::new(Mock {
                scenario,
                control: control.clone(),
            }),
            store: Mutex::new(Store::default()),
        }),
        control,
    )
}
fn snapshot_request() -> Value {
    json!({"request_id":"q","app":"editor","op":"snapshot"})
}
fn validate_result(result: &Value) {
    let packet = crate::protocol::envelope("s", "a11y.result", result.clone(), Some("request"));
    assert!(crate::protocol::validate(&packet, "s").is_ok());
    assert!(result.get("reasons").is_none());
}

struct ConsentContext {
    consent: Mutex<Option<input::Consent>>,
    stopped: AtomicBool,
    connected: AtomicBool,
    lock: tokio::sync::Mutex<()>,
}
impl Default for ConsentContext {
    fn default() -> Self {
        Self {
            consent: Mutex::new(Some(input::Consent {
                token: "token".into(),
                until: Instant::now() + Duration::from_secs(60),
            })),
            stopped: AtomicBool::new(false),
            connected: AtomicBool::new(true),
            lock: tokio::sync::Mutex::new(()),
        }
    }
}
impl ConsentContext {
    fn guard(&self) -> Result<input::ActionGuard<'_>, String> {
        input::guard_parts(
            &self.consent,
            &self.stopped,
            &self.connected,
            &self.lock,
            "token",
        )
    }
}

#[tokio::test]
async fn mock_operations_empty_ambiguous_incomplete_and_live_get() {
    for (scenario, expected, count) in [
        (Scenario::Empty, None, 0),
        (Scenario::Ambiguous, Some("AMBIGUOUS_TARGET"), 10),
        (Scenario::Incomplete, None, 1),
    ] {
        let (service, _) = service(scenario);
        let result = service
            .run(
                None,
                json!({"request_id":"q","app":"editor","op":"find","query":{"name":"Save"}}),
            )
            .await;
        validate_result(&result);
        assert_eq!(result["nodes"].as_array().unwrap().len(), count);
        assert_eq!(result["error"]["code"].as_str(), expected);
        assert_eq!(result["complete"], matches!(scenario, Scenario::Empty));
    }
    let (service, _) = service(Scenario::Normal);
    for app in ["EDITOR", "editor-BIN", "42", "focused"] {
        assert!(service.resolve(app).await.is_ok());
    }
    let result = service.run(None, snapshot_request()).await;
    let reference = result["nodes"][0]["ref"].as_str().unwrap();
    let get = service
        .run(
            None,
            json!({"request_id":"q","app":"editor","op":"get","ref":reference}),
        )
        .await;
    validate_result(&get);
    assert_eq!(get["snapshot_id"], result["snapshot_id"]);
    assert_eq!(get["nodes"][0]["value"], "fresh-value");
    let root = service
        .run(
            None,
            json!({"request_id":"q","app":"editor","op":"snapshot","root":reference}),
        )
        .await;
    validate_result(&root);
    assert_ne!(root["snapshot_id"], result["snapshot_id"]);
    let empty = service
        .run(
            None,
            json!({"request_id":"q","app":"editor","op":"find","query":{"name":"missing"}}),
        )
        .await;
    assert_eq!(empty["complete"], true);
    assert!(empty["nodes"].as_array().unwrap().is_empty());
}

#[tokio::test]
async fn mock_native_failures_are_typed_and_schema_valid() {
    let (normal, _) = service(Scenario::Normal);
    let missing = normal
        .run(
            None,
            json!({"request_id":"q","app":"missing","op":"snapshot"}),
        )
        .await;
    assert_eq!(missing["error"]["code"], "APP_NOT_FOUND");
    validate_result(&missing);
    let (failure, _) = service(Scenario::NativeFailure);
    let result = failure.run(None, snapshot_request()).await;
    assert_eq!(result["error"]["code"], "PERMISSION_DENIED");
    validate_result(&result);
    let (defunct, _) = service(Scenario::Defunct);
    let snapshot = defunct.run(None, snapshot_request()).await;
    let result = defunct
        .run(
            None,
            json!({"request_id":"q","app":"editor","op":"get","ref":snapshot["nodes"][0]["ref"]}),
        )
        .await;
    assert_eq!(result["error"]["code"], "STALE_REF");
    validate_result(&result);
    let context = ConsentContext::default();
    let guard = context.guard().unwrap();
    assert!(matches!(
        normal.act(&app(), "unsupported", None, &guard).await,
        Err(Error::PermissionDenied)
    ));
}

#[tokio::test]
async fn mock_timeout_cancels_without_storing_refs() {
    let (service, _) = service(Scenario::Timeout);
    let result = service.run(None, snapshot_request()).await;
    assert_eq!(result["error"]["code"], "TIMEOUT");
    validate_result(&result);
    assert!(service.store.lock().unwrap().snapshots.is_empty());
}

#[tokio::test]
async fn mock_reconnect_epoch_rejects_inflight_snapshot_and_get() {
    for scenario in [Scenario::PausedSnapshot, Scenario::PausedRefresh] {
        let (service, control) = service(scenario);
        let (_, nodes) = service.store.lock().unwrap().insert(app(), tree());
        let payload = if matches!(scenario, Scenario::PausedSnapshot) {
            snapshot_request()
        } else {
            json!({"request_id":"q","app":"editor","op":"get","ref":nodes[0].reference})
        };
        let request = service.run(None, payload);
        let disconnect = async {
            control.started.notified().await;
            service.clear();
            control.resume.notify_one();
        };
        let (result, ()) = tokio::time::timeout(Duration::from_secs(2), async {
            tokio::join!(request, disconnect)
        })
        .await
        .unwrap();
        assert_eq!(result["error"]["code"], "STALE_REF");
        validate_result(&result);
        assert!(service.store.lock().unwrap().snapshots.is_empty());
        let result = service
            .run(
                None,
                json!({"request_id":"q","app":"editor","op":"get","ref":nodes[0].reference}),
            )
            .await;
        assert_eq!(result["error"]["code"], "STALE_REF");
    }
}

#[tokio::test]
async fn mock_secure_values_are_suppressed_and_set_value_never_dispatches() {
    let (service, control) = service(Scenario::Secure);
    let snapshot = service.run(None, snapshot_request()).await;
    validate_result(&snapshot);
    assert!(snapshot["nodes"][0].get("value").is_none());
    let result = service
        .run(
            None,
            json!({"request_id":"q","app":"editor","op":"get","ref":snapshot["nodes"][0]["ref"]}),
        )
        .await;
    assert!(result["nodes"][0].get("value").is_none());
    validate_result(&result);
    let context = ConsentContext::default();
    let guard = context.guard().unwrap();
    assert!(matches!(
        service
            .act(&app(), "set_value", Some("dummy"), &guard)
            .await,
        Err(Error::PermissionDenied)
    ));
    assert_eq!(control.actions.load(Ordering::SeqCst), 0);
    let result = service.act(&app(), "focus", None, &guard).await.unwrap();
    assert!(result.value.is_none());
    assert_eq!(control.actions.load(Ordering::SeqCst), 1);
}

#[tokio::test]
async fn mock_action_guards_recheck_stop_consent_and_busy_lock() {
    let (service, control) = service(Scenario::Normal);
    let context = ConsentContext::default();
    let guard = context.guard().unwrap();
    assert!(context.guard().is_err());
    context.stopped.store(true, Ordering::SeqCst);
    assert!(matches!(
        service.act(&app(), "press", None, &guard).await,
        Err(Error::PermissionDenied)
    ));
    context.stopped.store(false, Ordering::SeqCst);
    context.consent.lock().unwrap().as_mut().unwrap().until =
        Instant::now() - Duration::from_secs(1);
    assert!(guard.check().is_err());
    drop(guard);
    assert!(context.guard().is_err());
    *context.consent.lock().unwrap() = None;
    assert!(context.guard().is_err());
    assert_eq!(control.actions.load(Ordering::SeqCst), 0);
    let denied = service.run(None,json!({"request_id":"q","op":"action","app":"editor","ref":"unknown:n0","action":"press","consent_token":"missing"})).await;
    assert_eq!(denied["error"]["code"], "PERMISSION_DENIED");
    validate_result(&denied);
    let context = ConsentContext::default();
    let guard = context.guard().unwrap();
    let result = service.act(&app(), "press", None, &guard).await.unwrap();
    assert_eq!(result.value.as_deref(), Some("fresh-value"));
    assert_eq!(control.actions.load(Ordering::SeqCst), 1);
}

fn node(name: &str) -> Node {
    Node {
        secure: false,
        reference: name.into(),
        role: "button".into(),
        name: name.into(),
        value: Some("private-value".into()),
        states: vec!["enabled".into()],
        bounds: Bounds {
            x: 1.,
            y: 2.,
            w: 30.,
            h: 20.,
        },
        parent_ref: None,
    }
}
fn app() -> Handle {
    Handle {
        bus: "test".into(),
        path: "/app".into(),
    }
}
fn tree() -> Tree {
    Tree {
        reasons: Default::default(),
        nodes: vec![RawNode {
            node: node("Save"),
            handle: app(),
            parent: None,
        }],
        complete: true,
    }
}

#[test]
fn queries_exact_contains_states_value_and_path() {
    let parent = Node {
        role: "toolbar".into(),
        ..node("Tools")
    };
    let exact = Node {
        parent_ref: Some("Tools".into()),
        ..node("Save")
    };
    let other = Node {
        parent_ref: Some("Tools".into()),
        ..node("Save As")
    };
    let nodes = vec![parent, exact, other];
    let q = Query {
        name: Some("sAvE".into()),
        ..Default::default()
    };
    assert_eq!(matches(&nodes, &q).len(), 1);
    let q = Query {
        name: Some("sav".into()),
        ..Default::default()
    };
    assert_eq!(matches(&nodes, &q).len(), 2);
    let mut q = Query {
        role: Some("push button".into()),
        path: Some(vec!["toolbar".into()]),
        states: Some(vec!["enabled".into()]),
        value: Some("private-value".into()),
        ..Default::default()
    };
    assert_eq!(matches(&nodes, &q).len(), 2);
    q.states = Some(vec!["focused".into()]);
    assert!(matches(&nodes, &q).is_empty());
    q.states = None;
    q.path = Some(vec!["missing".into()]);
    assert!(matches(&nodes, &q).is_empty());
    q.path = None;
    q.value = Some("different".into());
    assert!(matches(&nodes, &q).is_empty());
}

#[test]
fn query_path_is_an_ordered_ancestor_subsequence() {
    let nodes = vec![
        Node {
            role: "frame".into(),
            ..node("Window")
        },
        Node {
            role: "toolbar".into(),
            parent_ref: Some("Window".into()),
            ..node("Tools")
        },
        Node {
            role: "panel".into(),
            parent_ref: Some("Tools".into()),
            ..node("Group")
        },
        Node {
            parent_ref: Some("Group".into()),
            ..node("Save")
        },
    ];
    let mut query = Query {
        name: Some("Save".into()),
        path: Some(vec!["FRAME".into(), "tools".into()]),
        ..Default::default()
    };
    assert_eq!(matches(&nodes, &query).len(), 1);
    query.path = Some(vec!["toolbar".into(), "frame".into()]);
    assert!(matches(&nodes, &query).is_empty());
}

#[test]
fn store_expires_evicts_and_scopes_opaque_refs() {
    let mut store = Store::default();
    let (id, nodes) = store.insert(app(), tree());
    let reference = &nodes[0].reference;
    assert_eq!(reference, &format!("{id}:n0"));
    assert!(store.get(reference, &app()).is_ok());
    assert!(store.get("n0", &app()).is_err());
    assert!(store
        .get(
            reference,
            &Handle {
                bus: "other".into(),
                path: "/app".into()
            }
        )
        .is_err());
    for _ in 0..4 {
        store.insert(app(), tree());
    }
    assert!(matches!(store.get(reference, &app()), Err(Error::StaleRef)));
    let (_, nodes) = store.insert(app(), tree());
    store.snapshots.back_mut().unwrap().at = Instant::now() - Duration::from_secs(31);
    assert!(store.get(&nodes[0].reference, &app()).is_err());
}

#[test]
fn debug_redacts_and_results_validate() {
    let n = node("Save");
    assert!(!format!("{n:?}").contains("private-value"));
    assert!(format!("{n:?}").contains("[redacted]"));
    for (nodes, error) in [
        (vec![n], None),
        (vec![], None),
        (vec![], Some(Error::StaleRef)),
        (vec![node("candidate")], Some(Error::AmbiguousTarget)),
    ] {
        let mut payload = json!({"request_id":"q","snapshot_id":"snapshot","complete":error.is_none(),"nodes":nodes});
        if let Some(e) = error {
            payload["error"] = json!({"code":e.code(),"message":e.message()});
        }
        let packet = crate::protocol::envelope("s", "a11y.result", payload, Some("request"));
        assert!(crate::protocol::validate(&packet, "s").is_ok());
    }
    assert_eq!(normalize_role("push button"), "button");
    assert_eq!(normalize_role("table cell"), "table_cell");
    assert_eq!(normalize_role("tool bar"), "toolbar");
    assert_eq!(normalize_role("check box"), "check_box");
}

#[test]
fn request_parsing_and_operation_validation() {
    let payload = json!({"request_id":"q","op":"snapshot","app":"editor"});
    let packet = |p| crate::protocol::envelope("s", "a11y.request", p, None);
    assert!(serde_json::from_value::<Request>(payload.clone()).is_ok());
    assert!(crate::protocol::validate(&packet(payload.clone()), "s").is_ok());
    for invalid in [
        json!({"op":"snapshot","app":"editor"}),
        json!({"request_id":"q","op":"snapshot","app":""}),
        json!({"request_id":"q","op":"unknown","app":"editor"}),
        json!({"request_id":"q","op":"get","app":"editor"}),
        json!({"request_id":"q","op":"find","app":"editor","query":{}}),
        json!({"request_id":"q","op":"snapshot","app":"editor","max_depth":65}),
        json!({"request_id":"q","op":"snapshot","app":"editor","consent_token":"x"}),
        json!({"request_id":"q","op":"action","app":"editor","ref":"s:n0","action":"set_value","consent_token":"x"}),
    ] {
        assert!(crate::protocol::validate(&packet(invalid), "s").is_err());
    }
}

#[test]
fn truncation_reasons_count_only_potentially_visible_omissions() {
    let mut tree = tree();
    for reason in [Reason::InvisibleSkipped, Reason::DefunctSkipped] {
        tree.record(reason, "panel");
        tree.record(reason, "panel");
        assert_eq!(tree.reasons[&(reason, "panel".into())], 2);
        assert!(tree.complete);
    }
    for reason in [
        Reason::DepthLimit,
        Reason::NodeCap,
        Reason::Deadline,
        Reason::ChildReadError,
        Reason::LargeContainerSkipped,
    ] {
        tree.complete = true;
        tree.record(reason, "table");
        assert!(!tree.complete);
        assert_eq!(tree.reasons[&(reason, "table".into())], 1);
    }
}

#[cfg(target_os = "linux")]
#[tokio::test]
#[ignore = "requires isolated X11 and AT-SPI application bus"]
async fn live_accessibility() {
    let service = Service::default();
    let app_name = std::env::var("HCOMPANY_A11Y_APP").unwrap_or_else(|_| "soffice".into());
    let call = |mut payload: Value| async {
        payload["max_depth"] = json!(32);
        service.run(None, payload).await
    };
    let mut timings = Vec::new();
    for _ in 0..5 {
        let started = Instant::now();
        let result = call(json!({"request_id":"snapshot","op":"snapshot","app":app_name})).await;
        let ms = started.elapsed().as_secs_f64() * 1000.;
        println!(
            "snapshot_reasons={:?}",
            service
                .store
                .lock()
                .unwrap()
                .snapshots
                .back()
                .map(|s| &s.reasons)
        );
        timings.push(ms);
        println!(
            "snapshot_ms={ms:.3} complete={} nodes={}",
            result["complete"],
            result["nodes"].as_array().unwrap().len()
        );
        assert_eq!(result["complete"], true);
        let packet = crate::protocol::envelope("s", "a11y.result", result, None);
        assert!(crate::protocol::validate(&packet, "s").is_ok());
    }
    timings.sort_by(f64::total_cmp);
    println!("snapshot_p50_ms={:.3}", timings[2]);
    println!(
        "snapshot_p95_ms={:.3} method=nearest_rank samples=5",
        timings[4]
    );
    let result = call(json!({"request_id":"find","op":"find","app":app_name,"query":{"role":"table_cell","name":"A1"}})).await;
    assert!(result.get("error").is_none());
    assert_eq!(result["nodes"].as_array().unwrap().len(), 1);
    let reference = result["nodes"][0]["ref"].as_str().unwrap();
    let get = call(json!({"request_id":"get","op":"get","app":app_name,"ref":reference})).await;
    assert_eq!(get["snapshot_id"], result["snapshot_id"]);
    let bold = call(json!({"request_id":"toolbar","op":"find","app":app_name,"query":{"role":"toggle_button","name":"Bold","path":["toolbar"]}})).await;
    assert!(bold.get("error").is_none());
    assert_eq!(bold["nodes"].as_array().unwrap().len(), 1);
    let snapshot = call(json!({"request_id":"frame","op":"snapshot","app":app_name})).await;
    let frame = snapshot["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .find(|n| n["role"] == "frame")
        .unwrap();
    for n in [&get["nodes"][0], &bold["nodes"][0]] {
        let f = &frame["bounds"];
        let b = &n["bounds"];
        for (axis, size) in [("x", "w"), ("y", "h")] {
            assert!(b[axis].as_f64().unwrap() >= f[axis].as_f64().unwrap());
            assert!(
                b[axis].as_f64().unwrap() + b[size].as_f64().unwrap()
                    <= f[axis].as_f64().unwrap() + f[size].as_f64().unwrap()
            );
        }
    }
    println!("find cell + toolbar toggle + get: bounds inside frame");
}
