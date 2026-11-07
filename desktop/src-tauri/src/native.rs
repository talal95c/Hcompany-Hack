use crate::coordinates::{Monitor, Rect};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
pub struct Permissions {
    pub screen: bool,
    pub accessibility: bool,
    pub microphone: bool,
}

#[cfg(target_os = "linux")]
pub fn app_window_rect() -> Result<Rect, String> {
    use x11rb::{
        connection::Connection,
        protocol::xproto::{AtomEnum, ConnectionExt, MapState},
    };
    let (conn, screen) = connection()?;
    let root = conn.setup().roots[screen].root;
    let atom = conn
        .intern_atom(false, b"_NET_WM_PID")
        .map_err(|e| e.to_string())?
        .reply()
        .map_err(|e| e.to_string())?
        .atom;
    let windows = conn
        .query_tree(root)
        .map_err(|e| e.to_string())?
        .reply()
        .map_err(|e| e.to_string())?
        .children;
    for window in windows.into_iter().rev() {
        let pid = conn
            .get_property(false, window, atom, AtomEnum::CARDINAL, 0, 1)
            .map_err(|e| e.to_string())?
            .reply()
            .map_err(|e| e.to_string())?;
        let Some(pid) = pid.value32().and_then(|mut values| values.next()) else {
            continue;
        };
        if pid == std::process::id() {
            continue;
        }
        let attrs = conn
            .get_window_attributes(window)
            .map_err(|e| e.to_string())?
            .reply()
            .map_err(|e| e.to_string())?;
        if attrs.map_state != MapState::VIEWABLE {
            continue;
        }
        let geometry = conn
            .get_geometry(window)
            .map_err(|e| e.to_string())?
            .reply()
            .map_err(|e| e.to_string())?;
        let position = conn
            .translate_coordinates(window, root, 0, 0)
            .map_err(|e| e.to_string())?
            .reply()
            .map_err(|e| e.to_string())?;
        return Ok(Rect {
            x: position.dst_x.into(),
            y: position.dst_y.into(),
            width: geometry.width.into(),
            height: geometry.height.into(),
        });
    }
    Err("Fenêtre applicative introuvable".into())
}

#[cfg(not(target_os = "linux"))]
pub fn app_window_rect() -> Result<Rect, String> {
    Err("L'adaptateur doit fournir le rectangle de la fenêtre sur cette plateforme".into())
}

pub fn permissions() -> Permissions {
    #[cfg(target_os = "macos")]
    {
        let value = mac_call(&["permissions"])
            .ok()
            .and_then(|s| serde_json::from_slice::<serde_json::Value>(&s).ok());
        return Permissions {
            screen: value.as_ref().is_some_and(|v| v["screen"] == true),
            accessibility: value.as_ref().is_some_and(|v| v["accessibility"] == true),
            microphone: value.as_ref().is_some_and(|v| v["microphone"] == true),
        };
    }
    #[cfg(not(target_os = "macos"))]
    {
        use cpal::traits::HostTrait;
        Permissions {
            screen: monitors().is_ok(),
            accessibility: enigo::Enigo::new(&enigo::Settings::default()).is_ok(),
            microphone: cpal::default_host().default_input_device().is_some(),
        }
    }
}

pub fn request_permission(kind: &str) -> Result<(), String> {
    if !["screen", "accessibility", "microphone"].contains(&kind) {
        return Err("unknown permission".into());
    }
    #[cfg(target_os = "macos")]
    mac_call(&["request", kind]).map(|_| ())?;
    Ok(())
}

#[cfg(target_os = "linux")]
fn connection() -> Result<(x11rb::rust_connection::RustConnection, usize), String> {
    if std::env::var("XDG_SESSION_TYPE").as_deref() == Ok("wayland") {
        return Err("Capture/injection Wayland non autorisée ; utiliser une session X11.".into());
    }
    x11rb::connect(None).map_err(|e| e.to_string())
}

#[cfg(target_os = "linux")]
pub fn monitors() -> Result<Vec<Monitor>, String> {
    use x11rb::{connection::Connection, protocol::randr::ConnectionExt};
    let (conn, screen) = connection()?;
    let root = &conn.setup().roots[screen];
    let result = conn
        .randr_get_monitors(root.root, true)
        .map_err(|e| e.to_string())?
        .reply()
        .map_err(|e| e.to_string())?;
    Ok(result
        .monitors
        .into_iter()
        .map(|m| Monitor {
            id: m.name.to_string(),
            physical: Rect {
                x: m.x as f64,
                y: m.y as f64,
                width: m.width as f64,
                height: m.height as f64,
            },
            logical_x: m.x as f64,
            logical_y: m.y as f64,
            scale: 1.0,
        })
        .collect())
}

#[cfg(target_os = "linux")]
pub fn capture(crop: Rect, _monitor: &Monitor) -> Result<Vec<u8>, String> {
    use x11rb::{
        connection::Connection,
        protocol::xproto::{ConnectionExt, ImageFormat},
    };
    let (conn, screen) = connection()?;
    let root = &conn.setup().roots[screen];
    if ![24, 32].contains(&root.root_depth) {
        return Err("unsupported X11 pixel depth".into());
    }
    let reply = conn
        .get_image(
            ImageFormat::Z_PIXMAP,
            root.root,
            crop.x as i16,
            crop.y as i16,
            crop.width as u16,
            crop.height as u16,
            u32::MAX,
        )
        .map_err(|e| e.to_string())?
        .reply()
        .map_err(|e| e.to_string())?;
    let width = crop.width as u32;
    let height = crop.height as u32;
    let stride = reply.data.len() / height as usize;
    if stride != width as usize * 4 {
        return Err("unsupported X11 pixel layout".into());
    }
    let rgba: Vec<u8> = reply
        .data
        .as_chunks::<4>()
        .0
        .iter()
        .flat_map(|p| [p[2], p[1], p[0], 255])
        .collect();
    let image = image::RgbaImage::from_raw(width, height, rgba).ok_or("invalid image")?;
    let mut output = std::io::Cursor::new(Vec::new());
    image
        .write_to(&mut output, image::ImageFormat::Png)
        .map_err(|e| e.to_string())?;
    Ok(output.into_inner())
}

#[cfg(target_os = "linux")]
pub fn blender_focused() -> bool {
    use x11rb::{
        connection::Connection,
        protocol::xproto::{AtomEnum, ConnectionExt},
    };
    let result = (|| -> Result<bool, String> {
        let (conn, screen) = connection()?;
        let atom = |name: &[u8]| {
            conn.intern_atom(false, name)
                .map_err(|e| e.to_string())?
                .reply()
                .map(|v| v.atom)
                .map_err(|e| e.to_string())
        };
        let root = conn.setup().roots[screen].root;
        let active = conn
            .get_property(
                false,
                root,
                atom(b"_NET_ACTIVE_WINDOW")?,
                AtomEnum::WINDOW,
                0,
                1,
            )
            .map_err(|e| e.to_string())?
            .reply()
            .map_err(|e| e.to_string())?;
        let Some(window) = active.value32().and_then(|mut v| v.next()) else {
            return Ok(false);
        };
        let pid = conn
            .get_property(
                false,
                window,
                atom(b"_NET_WM_PID")?,
                AtomEnum::CARDINAL,
                0,
                1,
            )
            .map_err(|e| e.to_string())?
            .reply()
            .map_err(|e| e.to_string())?;
        let Some(pid) = pid.value32().and_then(|mut v| v.next()) else {
            return Ok(false);
        };
        let path = std::fs::read_link(format!("/proc/{pid}/exe")).map_err(|e| e.to_string())?;
        Ok(path
            .file_name()
            .is_some_and(|s| s == "blender" || s == "blender-bin"))
    })();
    result.unwrap_or(false)
}

#[cfg(test)]
mod live_tests {
    use super::*;
    #[test]
    #[ignore = "requires a real desktop session; run through pytest -m live"]
    fn live_native_capture() {
        let monitors = monitors().unwrap();
        let monitor = monitors.first().expect("active monitor");
        let crop = Rect {
            x: monitor.physical.x,
            y: monitor.physical.y,
            width: 256.,
            height: 128.,
        };
        let start = std::time::Instant::now();
        let bytes = capture(crop, monitor).unwrap();
        let elapsed = start.elapsed().as_secs_f64() * 1000.;
        let image = image::load_from_memory(&bytes).unwrap();
        assert_eq!((image.width(), image.height()), (256, 128));
        println!(
            "live native capture_ms={elapsed:.2} png_bytes={}",
            bytes.len()
        );
        use enigo::Mouse;
        let device = enigo::Enigo::new(&enigo::Settings::default()).unwrap();
        assert!(device.location().is_ok());
    }
}

#[cfg(target_os = "windows")]
pub fn monitors() -> Result<Vec<Monitor>, String> {
    xcap::Monitor::all()
        .map_err(|e| e.to_string())?
        .into_iter()
        .map(|m| {
            let x = m.x().map_err(|e| e.to_string())? as f64;
            let y = m.y().map_err(|e| e.to_string())? as f64;
            Ok(Monitor {
                id: m.id().map_err(|e| e.to_string())?.to_string(),
                physical: Rect {
                    x,
                    y,
                    width: m.width().map_err(|e| e.to_string())? as f64,
                    height: m.height().map_err(|e| e.to_string())? as f64,
                },
                logical_x: x,
                logical_y: y,
                scale: 1.0,
            })
        })
        .collect()
}

#[cfg(target_os = "windows")]
pub fn capture(crop: Rect, monitor: &Monitor) -> Result<Vec<u8>, String> {
    let m = xcap::Monitor::all()
        .map_err(|e| e.to_string())?
        .into_iter()
        .find(|m| m.id().is_ok_and(|id| id.to_string() == monitor.id))
        .ok_or("monitor disappeared")?;
    let image = m
        .capture_region(
            (crop.x - monitor.physical.x) as u32,
            (crop.y - monitor.physical.y) as u32,
            crop.width as u32,
            crop.height as u32,
        )
        .map_err(|e| e.to_string())?;
    let mut output = std::io::Cursor::new(Vec::new());
    image
        .write_to(&mut output, image::ImageFormat::Png)
        .map_err(|e| e.to_string())?;
    Ok(output.into_inner())
}

#[cfg(target_os = "windows")]
pub fn blender_focused() -> bool {
    xcap::Window::all().is_ok_and(|windows| {
        windows.iter().any(|w| {
            w.is_focused().unwrap_or(false)
                && w.app_name()
                    .is_ok_and(|n| n.eq_ignore_ascii_case("blender"))
        })
    })
}

#[cfg(target_os = "macos")]
pub fn mac_call(args: &[&str]) -> Result<Vec<u8>, String> {
    use std::os::unix::fs::PermissionsExt;
    let dir = std::env::temp_dir().join(format!("hcompany-native-{}", std::process::id()));
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    std::fs::set_permissions(&dir, std::fs::Permissions::from_mode(0o700))
        .map_err(|e| e.to_string())?;
    let path = dir.join("native");
    if !path.exists() {
        std::fs::write(
            &path,
            include_bytes!(concat!(env!("OUT_DIR"), "/native-macos")),
        )
        .map_err(|e| e.to_string())?;
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o700))
            .map_err(|e| e.to_string())?;
    }
    let output = std::process::Command::new(path)
        .args(args)
        .output()
        .map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).into_owned());
    }
    Ok(output.stdout)
}

#[cfg(target_os = "macos")]
pub fn monitors() -> Result<Vec<Monitor>, String> {
    serde_json::from_slice(&mac_call(&["monitors"])?).map_err(|e| e.to_string())
}

#[cfg(target_os = "macos")]
pub fn capture(crop: Rect, monitor: &Monitor) -> Result<Vec<u8>, String> {
    mac_call(&[
        "capture",
        &std::process::id().to_string(),
        &monitor.id,
        &(crop.x - monitor.physical.x).to_string(),
        &(crop.y - monitor.physical.y).to_string(),
        &crop.width.to_string(),
        &crop.height.to_string(),
    ])
}

#[cfg(target_os = "macos")]
pub fn blender_focused() -> bool {
    mac_call(&["focus"]).is_ok_and(|v| v == b"true")
}
