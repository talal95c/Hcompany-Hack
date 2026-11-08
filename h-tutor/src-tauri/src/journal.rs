//! Session journal: everything a tutorial run did, for replay, analytics and
//! turning a successful run into a tutorial.
//!
//! ```text
//! sessions/<timestamp>-<slug>/
//!   session.json   metadata and outcome
//!   tutorial.json  the milestone graph that was followed
//!   events.jsonl   one event per line, appended live
//!   shots/         screenshots Holo saw (and the same with its point marked)
//! ```

use base64::{Engine, engine::general_purpose::STANDARD};
use serde_json::{Value, json};
use std::io::Write;
use std::path::PathBuf;
use std::sync::Mutex;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

struct Journal {
    dir: PathBuf,
    started: Instant,
    shots: u32,
    meta: Value,
}

static CURRENT: Mutex<Option<Journal>> = Mutex::new(None);

pub fn sessions_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../sessions")
}

fn now_secs() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

/// Opens a new session folder; closes the previous one as abandoned.
pub fn begin(tutorial: &crate::tutorial::Tutorial, lang: Option<&str>, mode: &str) -> Option<PathBuf> {
    end("abandoned");
    let stamp = now_secs();
    let dir = sessions_dir().join(format!("{stamp}-{}", crate::tutorial::slug(&tutorial.title)));
    std::fs::create_dir_all(dir.join("shots")).ok()?;
    std::fs::write(dir.join("tutorial.json"), serde_json::to_vec_pretty(tutorial).ok()?).ok()?;
    let meta = json!({
        "id": dir.file_name()?.to_string_lossy(),
        "tutorial_id": tutorial.id,
        "tutorial_version": tutorial.version,
        "tutorial_source": tutorial.source,
        "title": tutorial.title,
        "goal": tutorial.goal,
        "app": tutorial.app.name,
        "language": lang,
        "mode": mode,
        "started_at": stamp,
        "ended_at": null,
        "outcome": "in_progress",
    });
    std::fs::write(dir.join("session.json"), serde_json::to_vec_pretty(&meta).ok()?).ok()?;
    *CURRENT.lock().unwrap() = Some(Journal { dir: dir.clone(), started: Instant::now(), shots: 0, meta });
    Some(dir)
}

/// Appends one event; `fields` is merged with `t` (seconds since start) and `type`.
pub fn event(kind: &str, fields: Value) {
    let mut guard = CURRENT.lock().unwrap();
    let Some(j) = guard.as_mut() else { return };
    let mut e = json!({ "t": (j.started.elapsed().as_secs_f64() * 10.0).round() / 10.0, "type": kind });
    if let (Some(e), Value::Object(f)) = (e.as_object_mut(), fields) {
        e.extend(f);
    }
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(j.dir.join("events.jsonl")) {
        let _ = writeln!(f, "{e}");
    }
}

/// Saves a screenshot (data URI) and returns its path relative to the
/// session. The file is written by the background writer: the path is
/// known at once, the bytes land shortly after.
pub fn shot(data_uri: &str) -> Option<String> {
    let mut guard = CURRENT.lock().unwrap();
    let j = guard.as_mut()?;
    j.shots += 1;
    let rel = format!("shots/{:04}.jpg", j.shots);
    queue(Job { dir: j.dir.clone(), rel: rel.clone(), data_uri: data_uri.to_string(), mark: None });
    Some(rel)
}

/// Saves a copy of a saved shot with a red crosshair at the normalized
/// point, in the background.
pub fn mark(rel: &str, data_uri: &str, nx: f64, ny: f64) {
    let Some(dir) = current_dir() else { return };
    queue(Job { dir, rel: rel.to_string(), data_uri: data_uri.to_string(), mark: Some((nx, ny)) });
}

/// One screenshot write. The session folder is fixed when the job is
/// queued, so a late write never lands in the next session.
struct Job {
    dir: PathBuf,
    rel: String,
    data_uri: String,
    /// Normalized point to mark, for the `-marked` copy.
    mark: Option<(f64, f64)>,
}

/// Screenshot writes waiting for the writer; beyond this they are dropped
/// (the journal is best effort, the learner's step is not).
const QUEUE: usize = 32;

static WRITER: std::sync::LazyLock<Option<std::sync::mpsc::SyncSender<Job>>> = std::sync::LazyLock::new(|| {
    let (tx, rx) = std::sync::mpsc::sync_channel::<Job>(QUEUE);
    std::thread::Builder::new()
        .name("journal-writer".into())
        .spawn(move || {
            for job in rx {
                write_job(&job);
            }
        })
        .ok()?;
    Some(tx)
});

fn queue(job: Job) {
    match WRITER.as_ref().map(|tx| tx.try_send(job)) {
        Some(Ok(())) => {}
        Some(Err(std::sync::mpsc::TrySendError::Full(job))) => eprintln!("[journal] writer busy, dropped {}", job.rel),
        _ => eprintln!("[journal] writer unavailable"),
    }
}

fn write_job(job: &Job) {
    let Some(bytes) = job.data_uri.split_once(',').and_then(|(_, b)| STANDARD.decode(b).ok()) else { return };
    match job.mark {
        None => {
            let _ = std::fs::write(job.dir.join(&job.rel), bytes);
        }
        Some((nx, ny)) => {
            let Ok(img) = image::load_from_memory(&bytes) else { return };
            let mut img = img.to_rgb8();
            crosshair(&mut img, nx, ny);
            let _ = img.save(job.dir.join(job.rel.replace(".jpg", "-marked.jpg")));
        }
    }
}

/// Draws a red crosshair at the normalized (0..1000) point.
pub fn crosshair(img: &mut image::RgbImage, nx: f64, ny: f64) {
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
}

pub fn current_dir() -> Option<PathBuf> {
    CURRENT.lock().unwrap().as_ref().map(|j| j.dir.clone())
}

pub fn set_mode(mode: &str) {
    if let Some(j) = CURRENT.lock().unwrap().as_mut() { j.meta["mode"] = json!(mode); }
}

pub fn skill_run(mode: crate::skills::Mode, outcome: &str) -> Option<crate::skills::Run> {
    let guard = CURRENT.lock().unwrap();
    let j = guard.as_ref()?;
    Some(crate::skills::Run {
        date: now_secs(),
        mode,
        outcome: outcome.into(),
        duration_s: j.started.elapsed().as_secs(),
        session_id: j.dir.file_name()?.to_string_lossy().into_owned(),
    })
}

/// Closes the session with its outcome ("completed", "abandoned", "error").
pub fn end(outcome: &str) {
    let Some(mut j) = CURRENT.lock().unwrap().take() else { return };
    j.meta["outcome"] = json!(outcome);
    j.meta["ended_at"] = json!(now_secs());
    j.meta["duration_s"] = json!(j.started.elapsed().as_secs());
    let _ = std::fs::write(j.dir.join("session.json"), serde_json::to_vec_pretty(&j.meta).unwrap_or_default());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn writer_saves_shots_and_marked_copies() {
        let dir = std::env::temp_dir().join(format!("rio-journal-test-{}", std::process::id()));
        std::fs::create_dir_all(dir.join("shots")).unwrap();
        let mut jpeg = std::io::Cursor::new(Vec::new());
        image::RgbImage::new(64, 40).write_to(&mut jpeg, image::ImageFormat::Jpeg).unwrap();
        let data_uri = format!("data:image/jpeg;base64,{}", STANDARD.encode(jpeg.get_ref()));
        let rel = "shots/0001.jpg".to_string();
        write_job(&Job { dir: dir.clone(), rel: rel.clone(), data_uri: data_uri.clone(), mark: None });
        write_job(&Job { dir: dir.clone(), rel, data_uri, mark: Some((500.0, 500.0)) });
        assert_eq!(std::fs::read(dir.join("shots/0001.jpg")).unwrap(), *jpeg.get_ref());
        let marked = image::open(dir.join("shots/0001-marked.jpg")).unwrap().to_rgb8();
        assert!(marked.get_pixel(32 + 10, 20).0[0] > 150, "crosshair drawn");
        std::fs::remove_dir_all(dir).ok();
    }
}
