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
use std::{collections::HashSet, future::Future};
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

async fn call<T, E>(future: impl Future<Output = Result<T, E>>) -> Result<T, Error> {
    tokio::time::timeout(Duration::from_millis(500), future)
        .await
        .map_err(|_| Error::Timeout)?
        .map_err(|_| Error::StaleRef)
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
        call(
            $kind::builder($conn)
                .destination($h.bus.as_str())
                .map_err(|_| Error::StaleRef)?
                .path($h.path.as_str())
                .map_err(|_| Error::StaleRef)?
                .cache_properties(CacheProperties::No)
                .build(),
        )
        .await?
    };
}

impl Sensor {
    async fn scoped_children(
        &self,
        parent: &Handle,
        budget: usize,
    ) -> Result<(Vec<RawNode>, usize), Error> {
        let conn = self.connection().await?;
        let accessible = proxy!(AccessibleProxy, conn, parent);
        let count = call(accessible.child_count()).await?;
        if count < 0 || count as usize > budget {
            return Err(Error::StaleRef);
        }
        let children = call(accessible.get_children()).await?;
        if children.len() != count as usize {
            return Err(Error::StaleRef);
        }
        let children = children
            .into_iter()
            .map(handle)
            .collect::<Result<Vec<_>, _>>()?;
        let results = stream::iter(children)
            .map(|h| async move {
                let accessible = proxy!(AccessibleProxy, conn, &h);
                let (observation, actual_parent) =
                    tokio::try_join!(self.read(&h, false), call(accessible.parent()))?;
                let actual_parent = handle(actual_parent)?;
                if actual_parent.bus != parent.bus
                    || actual_parent.path != parent.path
                    || observation.reasons.iter().any(|(r, _)| {
                        !matches!(
                            r,
                            Reason::DepthLimit | Reason::InvisibleSkipped | Reason::DefunctSkipped
                        )
                    })
                    || (observation.node.is_some() && !observation.valid_bounds)
                {
                    return Err(Error::StaleRef);
                }
                Ok(observation.node.map(|node| RawNode {
                    node,
                    handle: h,
                    parent: None,
                }))
            })
            .buffered(16)
            .collect::<Vec<Result<Option<RawNode>, Error>>>()
            .await;
        let mut nodes = Vec::new();
        for result in results {
            if let Some(node) = result? {
                nodes.push(node);
            }
        }
        Ok((nodes, count as usize))
    }
    async fn connection(&self) -> Result<&zbus::Connection, Error> {
        self.connection
            .get_or_try_init(|| async {
                call(AccessibilityConnection::new()).await.map_err(|e| {
                    if e == Error::Timeout {
                        e
                    } else {
                        Error::PermissionDenied
                    }
                })
            })
            .await
            .map(|c| c.connection())
    }
    async fn read(&self, h: &Handle, expand: bool) -> Result<Observation, Error> {
        let conn = self.connection().await?;
        let a = proxy!(AccessibleProxy, conn, h);
        let properties = proxy!(PropertiesProxy, conn, h);
        let state = call(a.get_state()).shared();
        let role = call(a.get_role()).shared();
        let showing = async {
            let (state, role) = tokio::join!(state.clone(), role.clone());
            let state = state?;
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
            call(a.get_interfaces()).await.map(Some)
        }
        .shared();
        let properties = async {
            if !showing.clone().await? {
                return Ok(None);
            }
            call(
                properties.get_all(
                    "org.a11y.atspi.Accessible"
                        .try_into()
                        .map_err(|_| Error::StaleRef)?,
                ),
            )
            .await
            .map(Some)
        };
        let extents = async {
            if interfaces
                .clone()
                .await?
                .is_some_and(|interfaces| interfaces.contains(Interface::Component))
            {
                let component = proxy!(ComponentProxy, conn, h);
                call(component.get_extents(CoordType::Screen))
                    .await
                    .map(Some)
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
        let set = set?;
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
        let role = role?;
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
            call(a.get_attributes()).await?
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
                call(text.get_text(0, -1)).await.map(Some)
            } else if interfaces.contains(Interface::Value) {
                let value = proxy!(ValueProxy, conn, h);
                call(value.current_value())
                    .await
                    .map(|v| Some(v.to_string()))
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
        let mut reasons = Vec::new();
        match value {
            Ok(value) => node.value = value,
            Err(error) => reasons.push((
                if error == Error::Timeout {
                    Reason::Deadline
                } else {
                    Reason::ChildReadError
                },
                node.role.clone(),
            )),
        };
        let children = match children {
            Ok((children, reason)) => {
                if let Some(reason) = reason {
                    reasons.push((reason, node.role.clone()));
                }
                children
            }
            Err(error) => {
                reasons.push((
                    if error == Error::Timeout {
                        Reason::Deadline
                    } else {
                        Reason::ChildReadError
                    },
                    node.role.clone(),
                ));
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
            let objects = call(a.get_children()).await?;
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
                call(component.get_accessible_at_point(x as i32, y as i32, CoordType::Screen))
                    .await?,
            )?;
            let cell_a = proxy!(AccessibleProxy, conn, &cell);
            let index = call(cell_a.get_index_in_parent()).await?;
            let (row, col) = tokio::try_join!(
                call(table.get_row_at_index(index)),
                call(table.get_column_at_index(index))
            )?;
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
                async move { handle(call(table.get_accessible_at(row, col)).await?) }
            })
            .buffered(64)
            .collect::<Vec<_>>()
            .await;
        let mut handles = Vec::new();
        for item in result {
            match item {
                Ok(h) => handles.push(h),
                Err(error) => {
                    reason = Some(if error == Error::Timeout {
                        Reason::Deadline
                    } else {
                        Reason::ChildReadError
                    })
                }
            }
        }
        Ok((handles, reason))
    }
}

impl AccessibilitySensor for Sensor {
    fn position<'a>(
        &'a self,
        parent: &'a Handle,
        target: &'a Handle,
    ) -> Task<'a, Option<scoped::Position>> {
        Box::pin(async move {
            let conn = self.connection().await?;
            let accessible = proxy!(AccessibleProxy, conn, parent);
            if call(accessible.get_role()).await? != Role::Table {
                return Ok(None);
            }
            let table = proxy!(TableProxy, conn, parent);
            let cell = proxy!(AccessibleProxy, conn, target);
            let index = call(cell.get_index_in_parent()).await?;
            if index < 0 {
                return Err(Error::StaleRef);
            }
            let (row, column, rows, columns) = tokio::try_join!(
                call(table.get_row_at_index(index)),
                call(table.get_column_at_index(index)),
                call(table.n_rows()),
                call(table.n_columns())
            )?;
            if row < 0 || column < 0 || row >= rows || column >= columns {
                return Err(Error::StaleRef);
            }
            Ok(Some(scoped::Position {
                row,
                column,
                rows,
                columns,
            }))
        })
    }

    fn scoped<'a>(
        &'a self,
        binding: &'a scoped::Binding,
        _deadline: Instant,
        budget: usize,
    ) -> Task<'a, Tree> {
        Box::pin(async move {
            if binding.ancestors.is_empty() || binding.ancestors.len() >= budget {
                return Err(Error::StaleRef);
            }
            let conn = self.connection().await?;
            let ancestors = stream::iter(binding.ancestors.clone().into_iter().enumerate())
                .map(|(i, (old, h))| async move {
                    let expected = if i == 0 {
                        &binding.app
                    } else {
                        &binding.ancestors[i - 1].1
                    };
                    let accessible = proxy!(AccessibleProxy, conn, &h);
                    let (observation, parent) =
                        tokio::try_join!(self.read(&h, false), call(accessible.parent())).inspect_err(|error| {
                            if std::env::var_os("RIO_A11Y_TRACE").is_some() { eprintln!("a11y scoped ancestor read_failed index={i} role={} code={}", old.role, error.code()); }
                        })?;
                    let parent = handle(parent)?;
                    let node = observation.node.ok_or(Error::StaleRef)?;
                    let mut linked = parent.bus == expected.bus && parent.path == expected.path;
                    if !linked && (h.bus != binding.app.bus || h.path != binding.app.path) {
                        let expected_proxy = proxy!(AccessibleProxy, conn, expected);
                        let count = call(expected_proxy.child_count()).await?;
                        if count >= 0 && count as usize <= budget {
                            let children = call(expected_proxy.get_children()).await?;
                            if children.len() == count as usize {
                                let children = children.into_iter().map(handle).collect::<Result<Vec<_>, _>>()?;
                                linked = children.iter().filter(|child| child.bus == h.bus && child.path == h.path).count() == 1;
                            }
                        }
                    }
                    if observation.reasons.iter().any(|(r, _)| {
                        !matches!(r, Reason::DepthLimit | Reason::InvisibleSkipped | Reason::DefunctSkipped)
                    }) || node.role != old.role
                        || ((h.bus != binding.app.bus || h.path != binding.app.path)
                            && !linked)
                    {
                        if std::env::var_os("RIO_A11Y_TRACE").is_some() {
                            eprintln!("a11y scoped ancestor mismatch index={i} role={} parent={}:{} expected={}:{}", old.role, parent.bus, parent.path, expected.bus, expected.path);
                        }
                        return Err(Error::StaleRef);
                    }
                    Ok(RawNode {
                        node,
                        handle: h,
                        parent: i.checked_sub(1),
                    })
                })
                .buffered(16)
                .collect::<Vec<Result<RawNode, Error>>>()
                .await;
            let mut nodes: Vec<RawNode> = Vec::new();
            let mut used = binding.ancestors.len();
            for (i, ancestor) in ancestors.into_iter().enumerate() {
                let unchanged_parent = i == 0
                    || (nodes[i - 1].handle.bus == binding.ancestors[i - 1].1.bus
                        && nodes[i - 1].handle.path == binding.ancestors[i - 1].1.path);
                if let Ok(node) = ancestor {
                    if unchanged_parent {
                        nodes.push(node);
                        continue;
                    }
                }
                if i == 0 {
                    return Err(Error::StaleRef);
                }
                let (candidates, count) = self
                    .scoped_children(&nodes[i - 1].handle, budget.saturating_sub(used))
                    .await?;
                used += count;
                let old = &binding.ancestors[i].0;
                let node = scoped::unique_ancestor(candidates, old, i - 1)?;
                nodes.push(node);
                if std::env::var_os("RIO_A11Y_TRACE").is_some() {
                    eprintln!(
                        "a11y scoped recovered ancestor role={} examined={count}",
                        old.role
                    );
                }
            }
            let parent_index = nodes.len() - 1;
            let parent_handle = nodes[parent_index].handle.clone();
            let parent = &parent_handle;
            if used >= budget {
                return Err(Error::StaleRef);
            }
            let handles = if let Some(position) = binding.position {
                let table = proxy!(TableProxy, conn, parent);
                let (rows, columns, object, index) = tokio::try_join!(
                    call(table.n_rows()),
                    call(table.n_columns()),
                    call(table.get_accessible_at(position.row, position.column)),
                    call(table.get_index_at(position.row, position.column))
                )?;
                if rows != position.rows || columns != position.columns {
                    return Err(Error::StaleRef);
                }
                let h = handle(object)?;
                let cell = proxy!(AccessibleProxy, conn, &h);
                if index < 0 || call(cell.get_index_in_parent()).await? != index {
                    return Err(Error::StaleRef);
                }
                vec![h]
            } else {
                let (children, _) = self.scoped_children(parent, budget - used).await?;
                for mut child in children {
                    child.parent = Some(parent_index);
                    nodes.push(child);
                }
                return Ok(Tree {
                    nodes,
                    complete: true,
                    reasons: BTreeMap::new(),
                });
            };
            let candidates = stream::iter(handles)
                .map(|h| async move {
                    let accessible = proxy!(AccessibleProxy, conn, &h);
                    let (observation, actual_parent) =
                        tokio::try_join!(self.read(&h, false), call(accessible.parent()))?;
                    let actual_parent = handle(actual_parent)?;
                    if actual_parent.bus != parent.bus || actual_parent.path != parent.path {
                        return Err(Error::StaleRef);
                    }
                    if observation.reasons.iter().any(|(r, _)| {
                        !matches!(
                            r,
                            Reason::DepthLimit | Reason::InvisibleSkipped | Reason::DefunctSkipped
                        )
                    }) {
                        return Err(Error::StaleRef);
                    }
                    if observation.node.is_some() && !observation.valid_bounds {
                        return Err(Error::StaleRef);
                    }
                    Ok(observation
                        .node
                        .filter(|_| observation.valid_bounds)
                        .map(|node| RawNode {
                            node,
                            handle: h,
                            parent: Some(parent_index),
                        }))
                })
                .buffered(16)
                .collect::<Vec<Result<Option<RawNode>, Error>>>()
                .await;
            for candidate in candidates {
                if let Some(node) = candidate? {
                    nodes.push(node);
                }
            }
            Ok(Tree {
                nodes,
                complete: true,
                reasons: BTreeMap::new(),
            })
        })
    }

    fn supports_events(&self) -> bool {
        true
    }

    fn subscribe(
        &self,
        sender: tokio::sync::mpsc::Sender<events::Change>,
        ready: tokio::sync::oneshot::Sender<bool>,
    ) -> Task<'_, ()> {
        Box::pin(async move {
            use atspi::events::{
                Event, EventProperties, EventTypeProperties, FocusEvents, ObjectEvents,
                WindowEvents,
            };
            let connection = AccessibilityConnection::new()
                .await
                .map_err(|_| Error::PermissionDenied)?;
            connection
                .register_event::<ObjectEvents>()
                .await
                .map_err(|_| Error::PermissionDenied)?;
            connection
                .register_event::<FocusEvents>()
                .await
                .map_err(|_| Error::PermissionDenied)?;
            connection
                .register_event::<WindowEvents>()
                .await
                .map_err(|_| Error::PermissionDenied)?;
            let stream = connection.event_stream();
            tokio::pin!(stream);
            let _ = ready.send(true);
            while let Some(event) = stream.next().await {
                let event = event.map_err(|_| Error::StaleRef)?;
                if matches!(
                    &event,
                    Event::Window(WindowEvents::Raise(_) | WindowEvents::Lower(_))
                ) {
                    continue;
                }
                let selector_changed = matches!(&event, Event::Object(ObjectEvents::PropertyChange(e))
                    if matches!(e.property.as_str(), "accessible-name" | "accessible-role" | "accessible-parent"));
                let reconcile = selector_changed
                    || matches!(
                        &event,
                        Event::Object(
                            ObjectEvents::ChildrenChanged(_)
                                | ObjectEvents::RowInserted(_)
                                | ObjectEvents::RowDeleted(_)
                                | ObjectEvents::ColumnInserted(_)
                                | ObjectEvents::ColumnDeleted(_)
                        ) | Event::Window(_)
                    );
                let focus = matches!(&event, Event::Focus(_) | Event::Window(_));
                if reconcile && std::env::var_os("RIO_A11Y_TRACE").is_some() {
                    let property = match &event {
                        Event::Object(ObjectEvents::PropertyChange(e)) if selector_changed => {
                            e.property.as_str()
                        }
                        _ => "-",
                    };
                    eprintln!(
                        "a11y structural category={} property={} source={}:{}",
                        event.member(),
                        property,
                        event.sender(),
                        event.path()
                    );
                }
                if !reconcile
                    && !focus
                    && !matches!(
                        &event,
                        Event::Object(
                            ObjectEvents::TextChanged(_)
                                | ObjectEvents::StateChanged(_)
                                | ObjectEvents::PropertyChange(_)
                                | ObjectEvents::VisibleDataChanged(_)
                                | ObjectEvents::ModelChanged(_)
                                | ObjectEvents::SelectionChanged(_)
                                | ObjectEvents::ActiveDescendantChanged(_)
                        )
                    )
                {
                    continue;
                }
                let change = events::Change {
                    source: Handle {
                        bus: event.sender().to_string(),
                        path: event.path().to_string(),
                    },
                    reconcile,
                    focus,
                    scoped: !focus
                        && (selector_changed
                            || matches!(&event, Event::Object(ObjectEvents::ChildrenChanged(_)))),
                };
                sender.send(change).await.map_err(|_| Error::StaleRef)?;
            }
            Ok(())
        })
    }
    fn apps(&self) -> Task<'_, Vec<App>> {
        Box::pin(async move {
            let started = Instant::now();
            let conn = self
                .connection
                .get_or_try_init(|| async {
                    call(AccessibilityConnection::new()).await.map_err(|e| {
                        if e == Error::Timeout {
                            e
                        } else {
                            Error::PermissionDenied
                        }
                    })
                })
                .await?;
            log::debug!(
                "a11y connection_ms={:.3}",
                started.elapsed().as_secs_f64() * 1000.
            );
            let registry = call(conn.root_accessible_on_registry()).await?;
            let windows = crate::discovery::windows().unwrap_or_default();
            let mut apps = Vec::new();
            for object in call(registry.get_children()).await? {
                let h = handle(object)?;
                let a = proxy!(AccessibleProxy, conn.connection(), &h);
                let dbus = call(zbus::fdo::DBusProxy::new(conn.connection())).await?;
                let pid = call(dbus.get_connection_unix_process_id(
                    h.bus.as_str().try_into().map_err(|_| Error::StaleRef)?,
                ))
                .await?;
                let executable = std::fs::read_link(format!("/proc/{pid}/exe"))
                    .ok()
                    .and_then(|p| p.file_name().map(|v| v.to_string_lossy().into_owned()))
                    .unwrap_or_default();
                let mut focused = call(a.get_state()).await?.contains(NativeState::Active);
                for object in call(a.get_children()).await? {
                    let child = handle(object)?;
                    let frame = proxy!(AccessibleProxy, conn.connection(), &child);
                    focused |= call(frame.get_state()).await?.contains(NativeState::Active);
                }
                let window = windows.iter().find(|w| w.pid == pid);
                apps.push(App {
                    app_id: window
                        .map(|w| w.app_id.clone())
                        .unwrap_or_else(|| executable.clone()),
                    name: if let Some(window) = window {
                        window.name.clone()
                    } else {
                        call(a.name()).await?
                    },
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
                let level_started = Instant::now();
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
                        Ok(Err(Error::Timeout)) => {
                            tree.record(Reason::Deadline, "unknown");
                            continue;
                        }
                        Ok(Err(_)) => {
                            let recovery = async {
                                let conn = self.connection().await?;
                                let accessible = proxy!(AccessibleProxy, conn, &h);
                                let role = call(accessible.get_role())
                                    .await
                                    .ok()
                                    .map(|r| normalize_role(r.name()))
                                    .unwrap_or_else(|| "unknown".into());
                                let reason = match call(accessible.get_state()).await {
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
                                Ok::<_, Error>((reason, role))
                            };
                            match tokio::time::timeout_at(deadline.into(), recovery).await {
                                Ok(Ok((reason, role))) => tree.record(reason, &role),
                                _ => {
                                    tree.record(Reason::Deadline, "unknown");
                                    break;
                                }
                            }
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
                log::debug!(
                    "a11y level={} gathered={} elapsed_ms={:.3}",
                    depth_index,
                    tree.nodes.len(),
                    level_started.elapsed().as_secs_f64() * 1000.
                );
                level = next;
                depth_index += 1;
            }
            Ok(tree)
        })
    }
    fn refresh<'a>(&'a self, h: &'a Handle) -> Task<'a, Node> {
        Box::pin(async move {
            let observation = self.read(h, false).await?;
            if observation
                .reasons
                .iter()
                .any(|(reason, _)| *reason == Reason::Deadline)
            {
                return Err(Error::Timeout);
            }
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
                    guard.check().map_err(Error::guard)?;
                    if action == "focus" {
                        c.grab_focus().await
                    } else {
                        c.scroll_to(atspi::ScrollType::Anywhere).await
                    }
                }
                "set_value" if interfaces.contains(Interface::EditableText) => {
                    let e = proxy!(EditableTextProxy, conn, h);
                    guard.check().map_err(Error::guard)?;
                    e.set_text_contents(value.ok_or(Error::PermissionDenied)?)
                        .await
                }
                "set_value" if interfaces.contains(Interface::Value) => {
                    let v = proxy!(ValueProxy, conn, h);
                    let number = value
                        .and_then(|v| v.parse::<f64>().ok())
                        .filter(|v| v.is_finite())
                        .ok_or(Error::PermissionDenied)?;
                    guard.check().map_err(Error::guard)?;
                    v.set_current_value(number).await.map(|()| true)
                }
                "select" => {
                    let parent = handle(a.parent().await.map_err(|_| Error::StaleRef)?)?;
                    let selection = proxy!(SelectionProxy, conn, &parent);
                    let index = a.get_index_in_parent().await.map_err(|_| Error::StaleRef)?;
                    guard.check().map_err(Error::guard)?;
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
                    guard.check().map_err(Error::guard)?;
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
    #[tokio::test]
    async fn individual_calls_bound_hangs_and_preserve_errors() {
        assert_eq!(call(async { Ok::<_, Error>(7) }).await, Ok(7));
        assert_eq!(
            call(async { Err::<(), _>(Error::PermissionDenied) }).await,
            Err(Error::StaleRef)
        );
        let started = Instant::now();
        assert_eq!(
            call(std::future::pending::<Result<(), Error>>()).await,
            Err(Error::Timeout)
        );
        assert!(started.elapsed() < Duration::from_secs(2));
    }
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
