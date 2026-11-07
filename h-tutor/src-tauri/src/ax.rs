//! Accessibility tree of the frontmost app, through Vercel Labs'
//! `agent-desktop` CLI (https://github.com/vercel-labs/agent-desktop).
//!
//! Used to snap Holo's point to the real UI element under it: the ghost
//! pointer outlines that element, and a click anywhere inside it counts.
//! Optional: when the CLI is missing, the app has no accessibility tree
//! (Blender draws its own UI) or the window is on another Space, the vision
//! path works alone.
//!
//! Reading a window's tree takes ~2 s, so it runs in parallel with Holo.

use serde_json::Value;
use std::process::Command;

/// An interactive element, bounds in global screen points.
#[derive(Clone, Debug)]
pub struct Element {
    pub role: String,
    pub name: String,
    pub x: f64,
    pub y: f64,
    pub w: f64,
    pub h: f64,
}

impl Element {
    pub fn contains(&self, px: f64, py: f64, margin: f64) -> bool {
        px >= self.x - margin && px <= self.x + self.w + margin && py >= self.y - margin && py <= self.y + self.h + margin
    }
}

fn run(args: &[&str]) -> Option<Value> {
    let out = Command::new("agent-desktop").args(args).output().ok()?;
    let v: Value = serde_json::from_slice(&out.stdout).ok()?;
    v["ok"].as_bool().filter(|ok| *ok).map(|_| v)
}

/// The frontmost app's process id (our bar never activates, so this is the
/// app being taught).
#[cfg(target_os = "macos")]
fn frontmost_pid() -> Option<i64> {
    use objc2::rc::autoreleasepool;
    use objc2::runtime::AnyObject;
    use objc2::{class, msg_send};
    autoreleasepool(|_| unsafe {
        let ws: *mut AnyObject = msg_send![class!(NSWorkspace), sharedWorkspace];
        let app: *mut AnyObject = msg_send![ws, frontmostApplication];
        if app.is_null() {
            return None;
        }
        let pid: i32 = msg_send![app, processIdentifier];
        Some(pid as i64)
    })
}

#[cfg(not(target_os = "macos"))]
fn frontmost_pid() -> Option<i64> {
    None
}

/// Interactive elements of the frontmost app's main window.
pub fn snapshot_frontmost() -> Vec<Element> {
    let Some(pid) = frontmost_pid() else { return vec![] };
    let Some(windows) = run(&["list-windows"]) else { return vec![] };
    // Its largest real window (skips menu bars and 500x500 placeholders).
    let wid = windows["data"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|w| w["pid"].as_i64() == Some(pid))
        .filter_map(|w| {
            let b = &w["bounds"];
            let (bw, bh) = (b["width"].as_f64()?, b["height"].as_f64()?);
            let id = w["id"].as_str()?.to_string();
            (bh > 100.0 && (bw, bh) != (500.0, 500.0)).then_some((id, bw * bh))
        })
        .max_by(|a, b| a.1.total_cmp(&b.1))
        .map(|(id, _)| id);
    let Some(wid) = wid else { return vec![] };
    let Some(snap) = run(&["snapshot", "--window-id", &wid, "-i", "--compact", "--include-bounds"]) else {
        return vec![];
    };
    let mut out = Vec::new();
    collect(&snap["data"]["tree"], &mut out);
    out
}

fn collect(node: &Value, out: &mut Vec<Element>) {
    if node["ref_id"].is_string() {
        let b = &node["bounds"];
        if let (Some(x), Some(y), Some(w), Some(h)) =
            (b["x"].as_f64(), b["y"].as_f64(), b["width"].as_f64(), b["height"].as_f64())
        {
            if w > 2.0 && h > 2.0 {
                out.push(Element {
                    role: node["role"].as_str().unwrap_or("").to_string(),
                    name: node["name"].as_str().or(node["description"].as_str()).unwrap_or("").to_string(),
                    x,
                    y,
                    w,
                    h,
                });
            }
        }
    }
    for c in node["children"].as_array().into_iter().flatten() {
        collect(c, out);
    }
}

/// The element Holo pointed at: the smallest interactive element containing
/// the point (containers bigger than a quarter of the screen are ignored).
pub fn element_at(elements: &[Element], px: f64, py: f64, screen_area: f64) -> Option<Element> {
    elements
        .iter()
        .filter(|e| e.contains(px, py, 0.0) && e.w * e.h < screen_area / 4.0)
        .min_by(|a, b| (a.w * a.h).total_cmp(&(b.w * b.h)))
        .cloned()
}
