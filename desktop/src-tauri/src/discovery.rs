use crate::{a11y, coordinates::Rect, State};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{sync::Mutex, time::Duration};

#[derive(Clone, Deserialize, Serialize, PartialEq)]
pub struct Window {
    pub app_id: String,
    pub name: String,
    pub pid: u32,
    pub window_title: String,
    pub window_bounds: Rect,
    pub scale: f64,
    #[serde(default)]
    pub focused: bool,
}

#[derive(Clone, Deserialize)]
pub struct Target {
    pub app_id: String,
    pub name: String,
    pub pid: u32,
}
impl Target {
    pub fn matches(&self, requested: &str) -> bool {
        requested.eq_ignore_ascii_case(&self.app_id)
            || requested.eq_ignore_ascii_case(&self.name)
            || requested == self.pid.to_string()
    }
    #[cfg(any(test, target_os = "linux"))]
    pub fn same_app(&self, window: &Window) -> bool {
        self.pid == window.pid && self.app_id.eq_ignore_ascii_case(&window.app_id)
    }
}
impl From<&Window> for Target {
    fn from(w: &Window) -> Self {
        Self {
            app_id: w.app_id.clone(),
            name: w.name.clone(),
            pid: w.pid,
        }
    }
}

#[derive(Default)]
pub struct Tracker {
    last: Mutex<Option<Window>>,
}
impl Tracker {
    pub fn target(&self) -> Option<Target> {
        self.last.lock().unwrap().as_ref().map(Target::from)
    }
    fn observe(&self, window: &Window) {
        if window.pid != std::process::id() {
            *self.last.lock().unwrap() = Some(window.clone());
        }
    }
    fn latest(&self) -> Option<Window> {
        self.last.lock().unwrap().clone()
    }
}

#[cfg(target_os = "linux")]
pub fn target_focused(target: &Target) -> bool {
    focused()
        .ok()
        .flatten()
        .is_some_and(|w| target.same_app(&w))
}
#[cfg(target_os = "macos")]
pub fn target_focused(target: &Target) -> bool {
    crate::native::mac_call(&["focus"])
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Target>(&bytes).ok())
        .is_some_and(|front| {
            front.pid == target.pid && front.app_id.eq_ignore_ascii_case(&target.app_id)
        })
}
#[cfg(target_os = "windows")]
pub fn target_focused(target: &Target) -> bool {
    use windows_sys::Win32::UI::WindowsAndMessaging::{
        GetForegroundWindow, GetWindowThreadProcessId,
    };
    let mut pid = 0;
    unsafe {
        GetWindowThreadProcessId(GetForegroundWindow(), &mut pid);
    }
    pid == target.pid && process_exe(pid).is_some_and(|id| id.eq_ignore_ascii_case(&target.app_id))
}
pub fn focused() -> Result<Option<Window>, String> {
    Ok(windows()?.into_iter().find(|w| w.focused))
}

async fn enrich(service: &a11y::Service, windows: &mut [Window]) -> Option<Vec<u32>> {
    match tokio::time::timeout(Duration::from_millis(500), service.applications()).await {
        Ok(Ok(apps)) => {
            for window in windows {
                if let Some(app) = apps.iter().find(|a| a.pid == window.pid) {
                    if !app.name.is_empty() {
                        window.name = app.name.clone();
                    }
                }
            }
            Some(apps.iter().map(|a| a.pid).collect())
        }
        _ => None,
    }
}

pub async fn resolve(service: &a11y::Service, requested: &str) -> Result<Window, String> {
    let mut windows = tokio::task::spawn_blocking(windows)
        .await
        .map_err(|_| "Lecture des fenêtres indisponible")??;
    enrich(service, &mut windows).await;
    windows
        .into_iter()
        .find(|w| {
            if requested.eq_ignore_ascii_case("focused") {
                w.focused
            } else {
                Target::from(w).matches(requested)
            }
        })
        .ok_or_else(|| "Fenêtre de l'application introuvable".into())
}

pub async fn poll(state: &State, previous: &mut Option<Value>) {
    let Ok(Ok(current)) = tokio::task::spawn_blocking(focused).await else {
        return;
    };
    if current.is_none() && previous.is_some() {
        return;
    }
    let Some(mut window) = current.or_else(|| state.focus.latest()) else {
        return;
    };
    let accessibility = match enrich(&state.a11y, std::slice::from_mut(&mut window)).await {
        Some(pids) if pids.contains(&window.pid) => "available",
        Some(_) => "unavailable",
        None => "unknown",
    };
    state.focus.observe(&window);
    let payload = focus_payload(&window, accessibility);
    if previous.as_ref() != Some(&payload) && state.send("app.focus", payload.clone(), None).is_ok()
    {
        *previous = Some(payload);
    }
}

pub fn focus_payload(window: &Window, accessibility: &str) -> Value {
    json!({"app_id":window.app_id,"name":window.name,"window_title":window.window_title,"window_bounds":window.window_bounds.screen(),"scale":window.scale,"accessibility":accessibility})
}

#[cfg(target_os = "linux")]
pub fn windows() -> Result<Vec<Window>, String> {
    use x11rb::{
        connection::Connection,
        protocol::xproto::{AtomEnum, ConnectionExt, MapState},
    };
    if std::env::var("XDG_SESSION_TYPE").as_deref() == Ok("wayland") {
        return Err("Découverte de fenêtres indisponible sous Wayland".into());
    }
    let (conn, screen) = x11rb::connect(None).map_err(|_| "Connexion X11 indisponible")?;
    let root = conn.setup().roots[screen].root;
    let atom = |name: &[u8]| -> Result<u32, String> {
        Ok(conn
            .intern_atom(false, name)
            .map_err(|_| "Atome X11 indisponible")?
            .reply()
            .map_err(|_| "Atome X11 indisponible")?
            .atom)
    };
    let pid_atom = atom(b"_NET_WM_PID")?;
    let title_atom = atom(b"_NET_WM_NAME")?;
    let utf8 = atom(b"UTF8_STRING")?;
    let property = |window, atom, kind, len| {
        conn.get_property(false, window, atom, kind, 0, len)
            .ok()?
            .reply()
            .ok()
    };
    let active = property(
        root,
        atom(b"_NET_ACTIVE_WINDOW")?,
        AtomEnum::WINDOW.into(),
        1,
    )
    .and_then(|p| p.value32()?.next())
    .filter(|w| *w != 0);
    let mut active = active
        .or_else(|| conn.get_input_focus().ok()?.reply().ok().map(|r| r.focus))
        .unwrap_or(0);
    for _ in 0..32 {
        if active == 0
            || active == root
            || property(active, pid_atom, AtomEnum::CARDINAL.into(), 1)
                .is_some_and(|p| p.value32().and_then(|mut v| v.next()).is_some())
        {
            break;
        }
        let Some(parent) = conn
            .query_tree(active)
            .ok()
            .and_then(|c| c.reply().ok())
            .map(|r| r.parent)
        else {
            break;
        };
        active = parent;
    }
    let clients = property(
        root,
        atom(b"_NET_CLIENT_LIST_STACKING")?,
        AtomEnum::WINDOW.into(),
        65536,
    )
    .and_then(|p| Some(p.value32()?.collect::<Vec<_>>()));
    let clients = match clients {
        Some(v) if !v.is_empty() => v,
        _ => {
            conn.query_tree(root)
                .map_err(|_| "Fenêtres indisponibles")?
                .reply()
                .map_err(|_| "Fenêtres indisponibles")?
                .children
        }
    };
    let mut result = Vec::new();
    for id in clients.into_iter().rev() {
        let Some(pid) =
            property(id, pid_atom, AtomEnum::CARDINAL.into(), 1).and_then(|p| p.value32()?.next())
        else {
            continue;
        };
        if pid == std::process::id() {
            continue;
        }
        let Some(attrs) = conn
            .get_window_attributes(id)
            .ok()
            .and_then(|c| c.reply().ok())
        else {
            continue;
        };
        if attrs.map_state != MapState::VIEWABLE {
            continue;
        }
        let Some(geometry) = conn.get_geometry(id).ok().and_then(|c| c.reply().ok()) else {
            continue;
        };
        let Some(pos) = conn
            .translate_coordinates(id, root, 0, 0)
            .ok()
            .and_then(|c| c.reply().ok())
        else {
            continue;
        };
        let Some(bounds) = Rect::atspi_screen(
            pos.dst_x.into(),
            pos.dst_y.into(),
            geometry.width.into(),
            geometry.height.into(),
        ) else {
            continue;
        };
        let Some(app_id) = std::fs::read_link(format!("/proc/{pid}/exe"))
            .ok()
            .and_then(|p| p.file_name().map(|s| s.to_string_lossy().into_owned()))
        else {
            continue;
        };
        let title = property(id, title_atom, utf8, 4096)
            .filter(|p| !p.value.is_empty())
            .or_else(|| property(id, AtomEnum::WM_NAME.into(), AtomEnum::ANY.into(), 4096))
            .map(|p| String::from_utf8_lossy(&p.value).into_owned())
            .unwrap_or_default();
        result.push(Window {
            name: app_id.clone(),
            app_id,
            pid,
            window_title: title,
            window_bounds: bounds,
            scale: 1.,
            focused: id == active,
        });
    }
    result.sort_by_key(|w| !w.focused);
    Ok(result)
}

#[cfg(target_os = "macos")]
pub fn windows() -> Result<Vec<Window>, String> {
    serde_json::from_slice(&crate::native::mac_call(&[
        "windows",
        &std::process::id().to_string(),
    ])?)
    .map_err(|_| "Fenêtres indisponibles".into())
}

#[cfg(target_os = "windows")]
fn process_exe(pid: u32) -> Option<String> {
    use windows_sys::Win32::{
        Foundation::CloseHandle,
        System::Threading::{
            OpenProcess, QueryFullProcessImageNameW, PROCESS_QUERY_LIMITED_INFORMATION,
        },
    };
    let mut buffer = vec![0u16; 32768];
    let mut len = buffer.len() as u32;
    let ok = unsafe {
        let handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid);
        if handle.is_null() {
            return None;
        }
        let ok = QueryFullProcessImageNameW(handle, 0, buffer.as_mut_ptr(), &mut len);
        CloseHandle(handle);
        ok != 0
    };
    if !ok {
        return None;
    }
    std::path::Path::new(&String::from_utf16_lossy(&buffer[..len as usize]))
        .file_name()
        .map(|s| s.to_string_lossy().into_owned())
}

#[cfg(target_os = "windows")]
pub fn windows() -> Result<Vec<Window>, String> {
    let mut result = Vec::new();
    for w in xcap::Window::all().map_err(|_| "Fenêtres indisponibles")? {
        let pid = w.pid().map_err(|_| "Processus indisponible")?;
        if pid == std::process::id() || w.is_minimized().unwrap_or(true) {
            continue;
        }
        let Some(app_id) = process_exe(pid) else {
            continue;
        };
        result.push(Window {
            name: w.app_name().unwrap_or_else(|_| app_id.clone()),
            app_id,
            pid,
            window_title: w.title().unwrap_or_default(),
            window_bounds: Rect {
                x: w.x().unwrap_or(0) as f64,
                y: w.y().unwrap_or(0) as f64,
                width: w.width().unwrap_or(0) as f64,
                height: w.height().unwrap_or(0) as f64,
            },
            scale: 1.,
            focused: w.is_focused().unwrap_or(false),
        });
    }
    result.retain(|w| w.window_bounds.valid());
    result.sort_by_key(|w| !w.focused);
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn window() -> Window {
        Window {
            app_id: "editor-bin".into(),
            name: "Editor".into(),
            pid: 42,
            window_title: "Document".into(),
            window_bounds: Rect {
                x: -100.,
                y: 20.,
                width: 800.,
                height: 600.,
            },
            scale: 2.,
            focused: true,
        }
    }
    #[test]
    fn target_matching_and_tracker_retain_external_app() {
        let window = window();
        let target = Target::from(&window);
        for name in ["EDITOR-bin", "editor", "42"] {
            assert!(target.matches(name));
        }
        assert!(!target.matches("other"));
        assert!(target.same_app(&window));
        assert!(!target.same_app(&Window {
            pid: 43,
            ..window.clone()
        }));
        let tracker = Tracker::default();
        assert!(tracker.target().is_none());
        tracker.observe(&window);
        tracker.observe(&Window {
            pid: std::process::id(),
            ..window.clone()
        });
        assert!(tracker.target().unwrap().same_app(&window));
    }
    #[test]
    fn focus_payloads_validate_without_pid_or_extra_fields() {
        for status in ["available", "unavailable", "unknown"] {
            let payload = focus_payload(&window(), status);
            assert!(payload.get("pid").is_none());
            let packet = crate::protocol::envelope("s", "app.focus", payload, None);
            assert!(crate::protocol::validate(&packet, "s").is_ok());
        }
    }
}
