//! Debug journal: every Holo call is saved to `h-tutor/debug/<session>/` with
//! the exact screenshots sent, the prompt, the raw answer and the latency.
//! Localizations also get a copy of the screenshot with the predicted point
//! drawn on it. Disable with HOLO_DEBUG=0.

use base64::{engine::general_purpose::STANDARD, Engine};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::OnceLock;

static DIR: OnceLock<Option<PathBuf>> = OnceLock::new();
static COUNTER: AtomicU32 = AtomicU32::new(0);

fn dir() -> Option<&'static PathBuf> {
    DIR.get_or_init(|| {
        if std::env::var("HOLO_DEBUG").is_ok_and(|v| v == "0") {
            return None;
        }
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        // Outside src-tauri so writing here never triggers a dev rebuild.
        let d = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../debug").join(stamp.to_string());
        std::fs::create_dir_all(&d).ok()?;
        Some(d)
    })
    .as_ref()
}

fn decode_data_uri(uri: &str) -> Option<Vec<u8>> {
    STANDARD.decode(uri.split_once(",")?.1).ok()
}

/// Records one call; returns its sequence id (e.g. "007-locate") for follow-ups.
pub fn record(tag: &str, model: &str, images: &[&str], prompt: &str, response: &str, ms: u128) -> Option<String> {
    // Inside a tutorial, side calls (questions, pointing) go to its journal.
    if crate::journal::current_dir().is_some() {
        let shots: Vec<String> = images.iter().filter_map(|u| crate::journal::shot(u)).collect();
        let parsed: Value = serde_json::from_str(response).unwrap_or(Value::Null);
        crate::journal::event(tag, json!({
            "model": model, "latency_ms": ms, "shots": shots, "prompt": prompt,
            "response": if parsed.is_null() { json!(response) } else { parsed },
        }));
        return shots.first().map(|s| format!("journal:{s}"));
    }
    let dir = dir()?;
    let id = format!("{:03}-{tag}", COUNTER.fetch_add(1, Ordering::SeqCst) + 1);
    let mut files = Vec::new();
    for (i, uri) in images.iter().enumerate() {
        if let Some(bytes) = decode_data_uri(uri) {
            let name = format!("{id}-img{i}.jpg");
            if std::fs::write(dir.join(&name), bytes).is_ok() {
                files.push(name);
            }
        }
    }
    let parsed: Value = serde_json::from_str(response).unwrap_or(Value::Null);
    let entry = json!({
        "id": id, "tag": tag, "model": model, "latency_ms": ms,
        "images": files, "prompt": prompt, "response_raw": response, "response": parsed,
    });
    std::fs::write(dir.join(format!("{id}.json")), serde_json::to_vec_pretty(&entry).ok()?).ok()?;
    Some(id)
}

/// Saves the screenshot with a red crosshair at the normalized (0..1000) point.
pub fn mark_point(id: &str, data_uri: &str, nx: f64, ny: f64) {
    if let Some(rel) = id.strip_prefix("journal:") {
        crate::journal::mark(rel, data_uri, nx, ny);
        return;
    }
    let Some(dir) = dir() else { return };
    let Some(bytes) = decode_data_uri(data_uri) else { return };
    let Ok(img) = image::load_from_memory(&bytes) else { return };
    let mut img = img.to_rgb8();
    let (w, h) = img.dimensions();
    let (cx, cy) = ((nx / 1000.0 * w as f64) as i64, (ny / 1000.0 * h as f64) as i64);
    let red = image::Rgb([255, 0, 0]);
    let mut put = |x: i64, y: i64| {
        if x >= 0 && y >= 0 && (x as u32) < w && (y as u32) < h {
            img.put_pixel(x as u32, y as u32, red);
        }
    };
    for d in -28..=28i64 {
        for t in -1..=1i64 {
            if d.abs() > 6 {
                put(cx + d, cy + t);
                put(cx + t, cy + d);
            }
        }
    }
    for a in 0..360 {
        let r = (a as f64).to_radians();
        for rad in [18.0, 19.0] {
            put(cx + (rad * r.cos()) as i64, cy + (rad * r.sin()) as i64);
        }
    }
    let _ = img.save(dir.join(format!("{id}-marked.jpg")));
}

pub fn dir_path() -> Option<String> {
    dir().map(|d| d.display().to_string())
}
