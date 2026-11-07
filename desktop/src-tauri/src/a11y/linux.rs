use super::*;
use atspi::proxy::{
    accessible::AccessibleProxy, action::ActionProxy, component::ComponentProxy,
    editable_text::EditableTextProxy, selection::SelectionProxy, table::TableProxy,
    text::TextProxy, value::ValueProxy,
};
use atspi::zbus::fdo::PropertiesProxy;
use atspi::zbus::{self, proxy::CacheProperties};
use atspi::{AccessibilityConnection, CoordType, Interface, Role, State as NativeState, StateSet};
use futures_util::{stream, FutureExt, StreamExt};
use std::collections::HashSet;
use tokio::sync::OnceCell;

#[derive(Default)]
pub struct Sensor {
    connection: OnceCell<AccessibilityConnection>,
}

struct Observation {
    node: Option<Node>,
    valid_bounds: bool,
    children: Vec<Handle>,
    reasons: Vec<(Reason, String)>,
}

fn secure_field(role: Role, attributes: &std::collections::HashMap<String, String>) -> bool {
    role == Role::PasswordText
        || attributes.iter().any(|(key, value)| {
            matches!(key.as_str(), "text-input-type" | "type")
                && value.eq_ignore_ascii_case("password")
                || matches!(key.as_str(), "secure" | "protected")
                    && value.eq_ignore_ascii_case("true")
        })
}

fn handle(object: atspi::ObjectRefOwned) -> Result<Handle, Error> {
    let bus = object.name_as_str().ok_or(Error::StaleRef)?.to_owned();
    let path = object.path_as_str().to_owned();
    if path.ends_with("/null") {
        return Err(Error::StaleRef);
    }
    Ok(Handle { bus, path })
}

fn states(set: StateSet) -> Vec<String> {
    let mut result: Vec<_> = [
        (NativeState::Focused, "focused"),
        (NativeState::Selected, "selected"),
        (NativeState::Checked, "checked"),
        (NativeState::Enabled, "enabled"),
        (NativeState::Expanded, "expanded"),
        (NativeState::Editable, "editable"),
        (NativeState::Pressed, "pressed"),
        (NativeState::Busy, "busy"),
    ]
    .into_iter()
    .filter(|(s, _)| set.contains(*s))
    .map(|(_, s)| s.to_owned())
    .collect();
    if set.contains(NativeState::Showing) && set.contains(NativeState::Visible) {
        result.push("visible".into());
    }
    result
}

macro_rules! proxy {
    ($kind:ident, $conn:expr, $h:expr) => {
        $kind::builder($conn)
            .destination($h.bus.as_str())
            .map_err(|_| Error::StaleRef)?
            .path($h.path.as_str())
            .map_err(|_| Error::StaleRef)?
            .cache_properties(CacheProperties::No)
            .build()
            .await
            .map_err(|_| Error::StaleRef)?
    };
}

impl Sensor {
    async fn connection(&self) -> Result<&zbus::Connection, Error> {
        self.connection
            .get_or_try_init(|| async {
                AccessibilityConnection::new()
                    .await
                    .map_err(|_| Error::PermissionDenied)
            })
            .await
            .map(|c| c.connection())
    }
    async fn read(&self, h: &Handle, expand: bool) -> Result<Observation, Error> {
        let conn = self.connection().await?;
        let a = proxy!(AccessibleProxy, conn, h);
        let properties = proxy!(PropertiesProxy, conn, h);
        let state = a.get_state().shared();
        let role = a.get_role().shared();
        let showing = async {
            let (state, role) = tokio::join!(state.clone(), role.clone());
            let state = state.map_err(|_| Error::StaleRef)?;
            Ok::<_, Error>(
                !state.contains(NativeState::Defunct)
                    && ((state.contains(NativeState::Showing)
                        && state.contains(NativeState::Visible))
                        || role.ok() == Some(Role::Application)),
            )
        }
        .shared();
        let interfaces = async {
            if !showing.clone().await? {
                return Ok(None);
            }
            a.get_interfaces()
                .await
                .map(Some)
                .map_err(|_| Error::StaleRef)
        }
        .shared();
        let properties = async {
            if !showing.clone().await? {
                return Ok(None);
            }
            properties
                .get_all(
                    "org.a11y.atspi.Accessible"
                        .try_into()
                        .map_err(|_| Error::StaleRef)?,
                )
                .await
                .map(Some)
                .map_err(|_| Error::StaleRef)
        };
        let extents = async {
            if interfaces
                .clone()
                .await?
                .is_some_and(|interfaces| interfaces.contains(Interface::Component))
            {
                let component = proxy!(ComponentProxy, conn, h);
                component
                    .get_extents(CoordType::Screen)
                    .await
                    .map(Some)
                    .map_err(|_| Error::StaleRef)
            } else {
                Ok(None)
            }
        };
        let (set, role, properties, interfaces, extents) = tokio::join!(
            state.clone(),
            role.clone(),
            properties,
            interfaces.clone(),
            extents
        );
        let set = set.map_err(|_| Error::StaleRef)?;
        let role_name = role
            .as_ref()
            .map(|r| normalize_role(r.name()))
            .unwrap_or_else(|_| "unknown".into());
        if set.contains(NativeState::Defunct) {
            return Ok(Observation {
                node: None,
                valid_bounds: false,
                children: vec![],
                reasons: vec![(Reason::DefunctSkipped, role_name)],
            });
        }
        if !(set.contains(NativeState::Showing) && set.contains(NativeState::Visible))
            && role.as_ref().ok() != Some(&Role::Application)
        {
            return Ok(Observation {
                node: None,
                valid_bounds: false,
                children: vec![],
                reasons: vec![(Reason::InvisibleSkipped, role_name)],
            });
        }
        let role = role.map_err(|_| Error::StaleRef)?;
        let interfaces = interfaces?.ok_or(Error::StaleRef)?;
        let mut properties = properties?.ok_or(Error::StaleRef)?;
        let count: i32 = properties
            .remove("ChildCount")
            .ok_or(Error::StaleRef)?
            .try_into()
            .map_err(|_| Error::StaleRef)?;
        let count = count.max(0) as usize;
        let bounds =
            extents?.and_then(|(x, y, w, h)| crate::coordinates::Rect::atspi_screen(x, y, w, h));
        let attributes = if matches!(role, Role::Entry | Role::Text) {
            a.get_attributes().await.map_err(|_| Error::StaleRef)?
        } else {
            Default::default()
        };
        let secure = secure_field(role, &attributes);
        let valid = bounds.is_some();
        let bounds = bounds
            .map(|r| Bounds {
                x: r.x,
                y: r.y,
                w: r.width,
                h: r.height,
            })
            .unwrap_or(Bounds {
                x: 0.,
                y: 0.,
                w: 1.,
                h: 1.,
            });
        let mut node = Node {
            secure,
            reference: String::new(),
            role: role_name,
            name: if secure {
                String::new()
            } else {
                properties
                    .remove("Name")
                    .ok_or(Error::StaleRef)?
                    .try_into()
                    .map_err(|_| Error::StaleRef)?
            },
            value: None,
            states: states(set),
            bounds,
            parent_ref: None,
        };
        let value = async {
            if secure {
                Ok(None)
            } else if interfaces.contains(Interface::Text) {
                let text = proxy!(TextProxy, conn, h);
                text.get_text(0, -1)
                    .await
                    .map(Some)
                    .map_err(|_| Error::StaleRef)
            } else if interfaces.contains(Interface::Value) {
                let value = proxy!(ValueProxy, conn, h);
                value
                    .current_value()
                    .await
                    .map(|v| Some(v.to_string()))
                    .map_err(|_| Error::StaleRef)
            } else {
                Ok(None)
            }
        };
        let children = async {
            if secure || count == 0 {
                Ok((vec![], None))
            } else if !expand {
                Ok((vec![], Some(Reason::DepthLimit)))
            } else {
                self.children(h, &node, count).await
            }
        };
        let (value, children) = tokio::join!(value, children);
        node.value = value?;
        let mut reasons = Vec::new();
        let children = match children {
            Ok((children, reason)) => {
                if let Some(reason) = reason {
                    reasons.push((reason, node.role.clone()));
                }
                children
            }
            Err(_) => {
                reasons.push((Reason::ChildReadError, node.role.clone()));
                vec![]
            }
        };
        Ok(Observation {
            node: Some(node),
            valid_bounds: valid,
            children,
            reasons,
        })
    }
    async fn children(
        &self,
        h: &Handle,
        node: &Node,
        count: usize,
    ) -> Result<(Vec<Handle>, Option<Reason>), Error> {
        let conn = self.connection().await?;
        let a = proxy!(AccessibleProxy, conn, h);
        if count <= 4096 {
            let mut result = Vec::new();
            let objects = a.get_children().await.map_err(|_| Error::StaleRef)?;
            let mut reason = (objects.len() < count).then_some(Reason::ChildReadError);
            for object in objects.into_iter().take(2000) {
                match handle(object) {
                    Ok(h) => result.push(h),
                    Err(_) => reason = Some(Reason::ChildReadError),
                }
            }
            if count > 2000 {
                reason = Some(Reason::NodeCap);
            }
            return Ok((result, reason));
        }
        if node.role != "table" {
            return Ok((vec![], Some(Reason::LargeContainerSkipped)));
        }
        let component = proxy!(ComponentProxy, conn, h);
        let table = proxy!(TableProxy, conn, h);
        let b = node.bounds;
        let mut corners = Vec::new();
        for (x, y) in [(b.x + 1., b.y + 1.), (b.x + b.w - 2., b.y + b.h - 2.)] {
            let cell = handle(
                component
                    .get_accessible_at_point(x as i32, y as i32, CoordType::Screen)
                    .await
                    .map_err(|_| Error::StaleRef)?,
            )?;
            let cell_a = proxy!(AccessibleProxy, conn, &cell);
            let index = cell_a
                .get_index_in_parent()
                .await
                .map_err(|_| Error::StaleRef)?;
            let (row, col) = tokio::try_join!(
                table.get_row_at_index(index),
                table.get_column_at_index(index)
            )
            .map_err(|_| Error::StaleRef)?;
            if row < 0 || col < 0 {
                return Ok((vec![], Some(Reason::ChildReadError)));
            }
            corners.push((row, col));
        }
        let ((r0, c0), (r1, c1)) = (corners[0], corners[1]);
        if r1 < r0 || c1 < c0 {
            return Ok((vec![], Some(Reason::ChildReadError)));
        }
        let mut cells = Vec::new();
        let mut reason = None;
        'rows: for row in r0..=r1 {
            for col in c0..=c1 {
                if cells.len() == 2000 {
                    reason = Some(Reason::NodeCap);
                    break 'rows;
                }
                cells.push((row, col));
            }
        }
        let result = stream::iter(cells)
            .map(|(row, col)| {
                let table = &table;
                async move {
                    handle(
                        table
                            .get_accessible_at(row, col)
                            .await
                            .map_err(|_| Error::StaleRef)?,
                    )
                }
            })
            .buffered(64)
            .collect::<Vec<_>>()
            .await;
        let mut handles = Vec::new();
        for item in result {
            match item {
                Ok(h) => handles.push(h),
                Err(_) => reason = Some(Reason::ChildReadError),
            }
        }
        Ok((handles, reason))
    }
}

impl AccessibilitySensor for Sensor {
    fn apps(&self) -> Task<'_, Vec<App>> {
        Box::pin(async move {
            let conn = self
                .connection
                .get_or_try_init(|| async {
                    AccessibilityConnection::new()
                        .await
                        .map_err(|_| Error::PermissionDenied)
                })
                .await?;
            let registry = conn
                .root_accessible_on_registry()
                .await
                .map_err(|_| Error::AppNotFound)?;
            let mut apps = Vec::new();
            for object in registry
                .get_children()
                .await
                .map_err(|_| Error::AppNotFound)?
            {
                let h = handle(object)?;
                let a = proxy!(AccessibleProxy, conn.connection(), &h);
                let dbus = zbus::fdo::DBusProxy::new(conn.connection())
                    .await
                    .map_err(|_| Error::PermissionDenied)?;
                let pid = dbus
                    .get_connection_unix_process_id(
                        h.bus.as_str().try_into().map_err(|_| Error::StaleRef)?,
                    )
                    .await
                    .map_err(|_| Error::StaleRef)?;
                let executable = std::fs::read_link(format!("/proc/{pid}/exe"))
                    .ok()
                    .and_then(|p| p.file_name().map(|v| v.to_string_lossy().into_owned()))
                    .unwrap_or_default();
                let mut focused = a
                    .get_state()
                    .await
                    .map_err(|_| Error::StaleRef)?
                    .contains(NativeState::Active);
                for object in a.get_children().await.map_err(|_| Error::StaleRef)? {
                    let child = handle(object)?;
                    let frame = proxy!(AccessibleProxy, conn.connection(), &child);
                    focused |= frame
                        .get_state()
                        .await
                        .map_err(|_| Error::StaleRef)?
                        .contains(NativeState::Active);
                }
                apps.push(App {
                    name: a.name().await.map_err(|_| Error::StaleRef)?,
                    handle: h,
                    executable,
                    pid,
                    focused,
                });
            }
            Ok(apps)
        })
    }
    fn snapshot<'a>(&'a self, root: &'a Handle, depth: usize, deadline: Instant) -> Task<'a, Tree> {
        Box::pin(async move {
            let mut tree = Tree {
                nodes: vec![],
                complete: true,
                reasons: Default::default(),
            };
            let mut level: Vec<(Handle, Option<usize>)> = vec![(root.clone(), None)];
            let mut seen = HashSet::new();
            let mut depth_index = 0;
            while !level.is_empty() {
                if Instant::now() >= deadline || tree.nodes.len() >= 2000 {
                    tree.record(
                        if Instant::now() >= deadline {
                            Reason::Deadline
                        } else {
                            Reason::NodeCap
                        },
                        "unknown",
                    );
                    break;
                }
                level.retain(|(h, _)| seen.insert((h.bus.clone(), h.path.clone())));
                let mut reads = stream::iter(level)
                    .map(move |(h, parent)| async move {
                        let read = tokio::time::timeout_at(
                            deadline.into(),
                            self.read(&h, depth_index < depth),
                        )
                        .await;
                        (h, parent, read)
                    })
                    .buffer_unordered(64);
                let mut next = Vec::new();
                while let Some((h, parent, read)) = reads.next().await {
                    if tree.nodes.len() >= 2000 || Instant::now() >= deadline {
                        tree.record(
                            if Instant::now() >= deadline {
                                Reason::Deadline
                            } else {
                                Reason::NodeCap
                            },
                            "unknown",
                        );
                        break;
                    }
                    let observation = match read {
                        Ok(Ok(observation)) => observation,
                        Err(_) => {
                            tree.record(Reason::Deadline, "unknown");
                            break;
                        }
                        Ok(Err(_)) => {
                            let conn = self.connection().await?;
                            let accessible = proxy!(AccessibleProxy, conn, &h);
                            let role = accessible
                                .get_role()
                                .await
                                .ok()
                                .map(|r| normalize_role(r.name()))
                                .unwrap_or_else(|| "unknown".into());
                            let reason = match accessible.get_state().await {
                                Ok(set) if set.contains(NativeState::Defunct) => {
                                    Reason::DefunctSkipped
                                }
                                Ok(set)
                                    if !set.contains(NativeState::Showing)
                                        || !set.contains(NativeState::Visible) =>
                                {
                                    Reason::InvisibleSkipped
                                }
                                _ => Reason::ChildReadError,
                            };
                            tree.record(reason, &role);
                            continue;
                        }
                    };
                    for (reason, role) in observation.reasons {
                        tree.record(reason, &role);
                    }
                    let Some(mut node) = observation.node else {
                        continue;
                    };
                    let mut child_parent = parent;
                    if !observation.valid_bounds && parent.is_none() {
                        // Application roots have no component; their windows become roots.
                    } else if observation.valid_bounds || !observation.children.is_empty() {
                        if !observation.valid_bounds {
                            node.bounds = tree.nodes[parent.ok_or(Error::StaleRef)?].node.bounds;
                        }
                        child_parent = Some(tree.nodes.len());
                        tree.nodes.push(RawNode {
                            node,
                            handle: h,
                            parent,
                        });
                    }
                    for child in observation.children {
                        if next.len() >= 8192 {
                            tree.record(Reason::NodeCap, "unknown");
                            break;
                        }
                        next.push((child, child_parent));
                    }
                }
                level = next;
                depth_index += 1;
            }
            Ok(tree)
        })
    }
    fn refresh<'a>(&'a self, h: &'a Handle) -> Task<'a, Node> {
        Box::pin(async move {
            let observation = self.read(h, false).await?;
            if !observation.valid_bounds {
                return Err(Error::StaleRef);
            }
            observation.node.ok_or(Error::StaleRef)
        })
    }
    fn action<'a>(
        &'a self,
        h: &'a Handle,
        action: &'a str,
        value: Option<&'a str>,
        guard: &'a input::ActionGuard<'a>,
    ) -> Task<'a, ()> {
        Box::pin(async move {
            let conn = self.connection().await?;
            let a = proxy!(AccessibleProxy, conn, h);
            self.refresh(h).await?.allow_action(action)?;
            let interfaces = a.get_interfaces().await.map_err(|_| Error::StaleRef)?;
            let ok = match action {
                "focus" | "scroll_into_view" => {
                    let c = proxy!(ComponentProxy, conn, h);
                    guard.check().map_err(|_| Error::PermissionDenied)?;
                    if action == "focus" {
                        c.grab_focus().await
                    } else {
                        c.scroll_to(atspi::ScrollType::Anywhere).await
                    }
                }
                "set_value" if interfaces.contains(Interface::EditableText) => {
                    let e = proxy!(EditableTextProxy, conn, h);
                    guard.check().map_err(|_| Error::PermissionDenied)?;
                    e.set_text_contents(value.ok_or(Error::PermissionDenied)?)
                        .await
                }
                "set_value" if interfaces.contains(Interface::Value) => {
                    let v = proxy!(ValueProxy, conn, h);
                    let number = value
                        .and_then(|v| v.parse::<f64>().ok())
                        .filter(|v| v.is_finite())
                        .ok_or(Error::PermissionDenied)?;
                    guard.check().map_err(|_| Error::PermissionDenied)?;
                    v.set_current_value(number).await.map(|()| true)
                }
                "select" => {
                    let parent = handle(a.parent().await.map_err(|_| Error::StaleRef)?)?;
                    let selection = proxy!(SelectionProxy, conn, &parent);
                    let index = a.get_index_in_parent().await.map_err(|_| Error::StaleRef)?;
                    guard.check().map_err(|_| Error::PermissionDenied)?;
                    selection.select_child(index).await
                }
                "press" | "toggle" | "expand" | "collapse" => {
                    let actions = proxy!(ActionProxy, conn, h);
                    let names: &[&str] = match action {
                        "press" => &["click", "press", "activate"],
                        "toggle" => &["toggle", "click", "press"],
                        "expand" => &["expand", "open"],
                        _ => &["collapse", "close"],
                    };
                    let mut selected = None;
                    for i in 0..actions
                        .n_actions()
                        .await
                        .map_err(|_| Error::PermissionDenied)?
                        .min(64)
                    {
                        if names.contains(
                            &actions
                                .get_name(i)
                                .await
                                .map_err(|_| Error::PermissionDenied)?
                                .to_lowercase()
                                .as_str(),
                        ) {
                            selected = Some(i);
                            break;
                        }
                    }
                    let index = selected.ok_or(Error::PermissionDenied)?;
                    guard.check().map_err(|_| Error::PermissionDenied)?;
                    actions.do_action(index).await
                }
                _ => return Err(Error::PermissionDenied),
            }
            .map_err(|_| Error::PermissionDenied)?;
            if ok {
                Ok(())
            } else {
                Err(Error::PermissionDenied)
            }
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_states_require_showing_and_visible_and_map_contract_flags() {
        for set in [
            StateSet::empty(),
            NativeState::Showing.into(),
            NativeState::Visible.into(),
        ] {
            assert!(!states(set).iter().any(|s| s == "visible"));
        }
        let set = NativeState::Showing
            | NativeState::Visible
            | NativeState::Focused
            | NativeState::Selected
            | NativeState::Checked
            | NativeState::Enabled
            | NativeState::Expanded
            | NativeState::Editable
            | NativeState::Pressed
            | NativeState::Busy;
        assert_eq!(
            states(StateSet::new(set)),
            vec![
                "focused", "selected", "checked", "enabled", "expanded", "editable", "pressed",
                "busy", "visible"
            ]
        );
    }
    #[test]
    fn secure_role_and_attributes_are_recognized() {
        assert!(secure_field(Role::PasswordText, &Default::default()));
        for (key, value) in [
            ("text-input-type", "password"),
            ("type", "PASSWORD"),
            ("secure", "true"),
            ("protected", "TRUE"),
        ] {
            assert!(secure_field(
                Role::Entry,
                &[(key.into(), value.into())].into()
            ));
        }
        assert!(!secure_field(
            Role::Entry,
            &[("type".into(), "text".into())].into()
        ));
    }
}
