//! YouTube video → interactive tutorial.
//!
//! 1. yt-dlp: metadata (title, chapters) and a low-resolution download.
//! 2. ffmpeg: mono audio, and one key frame per chapter (or per segment).
//! 3. Gladia (pre-recorded): timestamped transcript.
//! 4. Holo, vision: reads the key frames with their narration (what the
//!    screen shows, what the presenter does, the GUI path used).
//! 5. Holo: designs the milestone graph, each milestone linked to the
//!    second of the video that shows it.
//!
//! The result is a regular tutorial (source "youtube") saved to the library.

use crate::holo::{self, Holo};
use crate::tutorial::{self, App, Milestone, Tutorial};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::Command;
use tauri::{AppHandle, Emitter};

/// Longest video imported (seconds).
const MAX_DURATION: f64 = 45.0 * 60.0;
/// Key frames read by Holo (one per chapter, at most this many).
const MAX_FRAMES: usize = 16;
/// Images per Holo call (the API takes up to 5).
const FRAMES_PER_CALL: usize = 4;

#[derive(Serialize, Clone)]
struct Progress {
    stage: &'static str,
    detail: String,
}

fn progress(app: &AppHandle, stage: &'static str, detail: impl Into<String>) {
    app.emit_to("main", "import:progress", Progress { stage, detail: detail.into() }).ok();
}

pub fn is_youtube(url: &str) -> bool {
    let u = url.trim();
    (u.starts_with("http://") || u.starts_with("https://") || u.starts_with("www.") || u.starts_with("youtu"))
        && (u.contains("youtube.com/") || u.contains("youtu.be/"))
}

/// A tool from Homebrew may not be on the PATH of an app launched from Finder.
fn tool(name: &str) -> PathBuf {
    for dir in ["/opt/homebrew/bin", "/usr/local/bin"] {
        let p = Path::new(dir).join(name);
        if p.exists() {
            return p;
        }
    }
    PathBuf::from(name)
}

fn run(cmd: &mut Command, what: &str) -> Result<Vec<u8>, String> {
    let out = cmd.output().map_err(|e| format!("{what}: {e} (is it installed? brew install yt-dlp ffmpeg)"))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(format!("{what} failed: {}", err.lines().last().unwrap_or("").trim()));
    }
    Ok(out.stdout)
}

#[derive(Clone)]
struct Segment {
    title: String,
    start: f64,
    end: f64,
}

struct Video {
    id: String,
    title: String,
    uploader: String,
    url: String,
    segments: Vec<Segment>,
}

fn metadata(url: &str) -> Result<Video, String> {
    let out = run(Command::new(tool("yt-dlp")).args(["-J", "--no-playlist", "--socket-timeout", "30", url]), "yt-dlp")?;
    let m: Value = serde_json::from_slice(&out).map_err(|e| format!("yt-dlp: {e}"))?;
    let duration = m["duration"].as_f64().unwrap_or(0.0);
    if duration <= 0.0 {
        return Err("This video has no duration (live stream?)".into());
    }
    if duration > MAX_DURATION {
        return Err(format!("Video too long ({} min): 45 min max", (duration / 60.0).round()));
    }
    let mut segments: Vec<Segment> = m["chapters"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(|c| {
            Some(Segment {
                title: c["title"].as_str()?.to_string(),
                start: c["start_time"].as_f64()?,
                end: c["end_time"].as_f64()?,
            })
        })
        .collect();
    // No chapters (or too many): even segments.
    if segments.len() < 3 || segments.len() > MAX_FRAMES {
        let n = ((duration / 90.0).round() as usize).clamp(4, 12);
        segments = (0..n)
            .map(|i| Segment {
                title: format!("Part {}", i + 1),
                start: duration * i as f64 / n as f64,
                end: duration * (i + 1) as f64 / n as f64,
            })
            .collect();
    }
    Ok(Video {
        id: m["id"].as_str().unwrap_or("video").to_string(),
        title: m["title"].as_str().unwrap_or("YouTube tutorial").to_string(),
        uploader: m["uploader"].as_str().unwrap_or("").to_string(),
        url: m["webpage_url"].as_str().unwrap_or(url).to_string(),
        segments,
    })
}

fn download(url: &str, dir: &Path) -> Result<(PathBuf, PathBuf), String> {
    let video = dir.join("video.mp4");
    if !video.exists() {
        run(
            Command::new(tool("yt-dlp")).args([
                "-q",
                "--no-playlist",
                "-f",
                "b[height<=480][ext=mp4]/bv*[height<=480][ext=mp4]+ba[ext=m4a]/b[height<=480]/b",
                "--merge-output-format",
                "mp4",
                "--ffmpeg-location",
                &tool("ffmpeg").to_string_lossy(),
                "-o",
                &video.to_string_lossy(),
                url,
            ]),
            "yt-dlp download",
        )?;
    }
    let audio = dir.join("audio.mp3");
    if !audio.exists() {
        run(
            Command::new(tool("ffmpeg")).args(["-loglevel", "error", "-y", "-i"]).arg(&video).args([
                "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "32k",
            ]).arg(&audio),
            "ffmpeg audio",
        )?;
    }
    Ok((video, audio))
}

/// One key frame inside each segment (40% in: past the title card).
fn key_frames(video: &Path, segments: &[Segment], dir: &Path) -> Result<Vec<String>, String> {
    segments
        .iter()
        .enumerate()
        .map(|(i, s)| {
            let t = (s.start + (s.end - s.start) * 0.4).min(s.end - 1.0).max(0.0);
            let path = dir.join(format!("frame{i:02}.jpg"));
            run(
                Command::new(tool("ffmpeg"))
                    .args(["-loglevel", "error", "-y", "-ss", &format!("{t:.1}"), "-i"])
                    .arg(video)
                    .args(["-frames:v", "1", "-vf", "scale=1280:-2", "-q:v", "4"])
                    .arg(&path),
                "ffmpeg frame",
            )?;
            let bytes = std::fs::read(&path).map_err(|e| e.to_string())?;
            Ok(format!("data:image/jpeg;base64,{}", STANDARD.encode(bytes)))
        })
        .collect()
}

#[derive(Deserialize, Clone)]
struct Utterance {
    start: f64,
    text: String,
}

/// Gladia pre-recorded transcription: upload, create the job, poll.
async fn transcribe(audio: &Path) -> Result<(Vec<Utterance>, Option<String>), String> {
    let key = std::env::var("GLADIA_API_KEY").map_err(|_| "GLADIA_API_KEY is missing from .env")?;
    let http = reqwest::Client::new();
    let bytes = tokio::fs::read(audio).await.map_err(|e| e.to_string())?;
    let form = reqwest::multipart::Form::new().part(
        "audio",
        reqwest::multipart::Part::bytes(bytes).file_name("audio.mp3").mime_str("audio/mpeg").map_err(|e| e.to_string())?,
    );
    let up: Value = http
        .post("https://api.gladia.io/v2/upload")
        .header("x-gladia-key", &key)
        .multipart(form)
        .send()
        .await
        .map_err(|e| format!("Gladia upload: {e}"))?
        .json()
        .await
        .map_err(|e| format!("Gladia upload: {e}"))?;
    let audio_url = up["audio_url"].as_str().ok_or_else(|| format!("Gladia upload: {up}"))?;
    let job: Value = http
        .post("https://api.gladia.io/v2/pre-recorded")
        .header("x-gladia-key", &key)
        .json(&json!({ "audio_url": audio_url }))
        .send()
        .await
        .map_err(|e| format!("Gladia: {e}"))?
        .json()
        .await
        .map_err(|e| format!("Gladia: {e}"))?;
    let result_url = job["result_url"].as_str().ok_or_else(|| format!("Gladia: {job}"))?.to_string();
    for _ in 0..200 {
        tokio::time::sleep(std::time::Duration::from_secs(3)).await;
        let r: Value = http
            .get(&result_url)
            .header("x-gladia-key", &key)
            .send()
            .await
            .map_err(|e| format!("Gladia: {e}"))?
            .json()
            .await
            .map_err(|e| format!("Gladia: {e}"))?;
        match r["status"].as_str() {
            Some("done") => {
                let t = &r["result"]["transcription"];
                let utterances = serde_json::from_value(t["utterances"].clone()).unwrap_or_default();
                let lang = t["languages"][0].as_str().map(String::from);
                return Ok((utterances, lang));
            }
            Some("error") => return Err(format!("Gladia transcription failed: {}", r["error_code"])),
            _ => {}
        }
    }
    Err("Gladia transcription timed out".into())
}

fn narration(utt: &[Utterance], s: &Segment, limit: usize) -> String {
    let t: String = utt
        .iter()
        .filter(|u| u.start >= s.start && u.start < s.end)
        .map(|u| u.text.trim())
        .collect::<Vec<_>>()
        .join(" ");
    t.chars().take(limit).collect()
}

#[derive(Deserialize)]
struct FrameNote {
    index: usize,
    screen: String,
    action: String,
    gui_path: String,
}

/// Holo reads the key frames, a few per call, with their narration.
async fn read_frames(
    holo: &Holo,
    frames: &[String],
    segments: &[Segment],
    utt: &[Utterance],
) -> Result<Vec<FrameNote>, String> {
    let schema = json!({
        "type": "object",
        "properties": { "frames": { "type": "array", "items": {
            "type": "object",
            "properties": {
                "index": { "type": "integer" },
                "screen": { "type": "string" },
                "action": { "type": "string" },
                "gui_path": { "type": "string" }
            },
            "required": ["index", "screen", "action", "gui_path"]
        }}},
        "required": ["frames"]
    });
    let mut notes = Vec::new();
    for chunk in (0..frames.len()).collect::<Vec<_>>().chunks(FRAMES_PER_CALL) {
        let mut text = String::new();
        let images: Vec<&str> = chunk.iter().map(|&i| frames[i].as_str()).collect();
        for (k, &i) in chunk.iter().enumerate() {
            let s = &segments[i];
            text += &format!(
                "Image {k} = frame {i}, chapter \"{}\" ({}s-{}s). Narration: {}\n",
                s.title,
                s.start as u32,
                s.end as u32,
                narration(utt, s, 700)
            );
        }
        let prompt = format!(
            "These images are key frames from a software tutorial video, in order, each with the narration of \
             its chapter:\n{text}\nFor each frame (use its frame number as index) give, in English:\n\
             - screen: the app and the visible panel, menu or dialog and its state; only what you see.\n\
             - action: what the presenter does or tells the viewer to do in this chapter, concretely.\n\
             - gui_path: the GUI path or shortcut actually shown or said (e.g. \"Add > Mesh > Torus\", \
               \"Shift+A\"), empty if none. Never invent one."
        );
        let r: Value = holo.structured("yt_read", &holo::smart_model(), &images, &prompt, schema.clone()).await?;
        if let Ok(mut batch) = serde_json::from_value::<Vec<FrameNote>>(r["frames"].clone()) {
            notes.append(&mut batch);
        }
    }
    Ok(notes)
}

#[derive(Deserialize)]
struct Plan {
    title: String,
    app: String,
    goal: String,
    milestones: Vec<PlanMilestone>,
}

#[derive(Deserialize)]
struct PlanMilestone {
    goal: String,
    done_when: String,
    #[serde(default)]
    hints: Vec<String>,
    #[serde(default)]
    teach: String,
    #[serde(default)]
    video_at: Option<u32>,
}

/// Holo designs the milestone graph from the chapters and the frame notes.
async fn design(holo: &Holo, v: &Video, notes: &[FrameNote]) -> Result<Plan, String> {
    let chapters: String = v.segments.iter().map(|s| format!("- {}s {}\n", s.start as u32, s.title)).collect();
    let seen: String = notes
        .iter()
        .filter_map(|n| {
            let s = v.segments.get(n.index)?;
            Some(format!(
                "- [{} @ {}s] screen: {} | action: {} | path: {}\n",
                s.title, s.start as u32, n.screen, n.action, n.gui_path
            ))
        })
        .collect();
    let prompt = format!(
        "You turn a YouTube software tutorial into a hands-on interactive tutorial that a learner will follow \
         live in the app, guided by an AI tutor that sees their screen.\n\n\
         Video: \"{}\" by {}\nChapters:\n{chapters}\n\
         What the video shows, chapter by chapter (from key frames and narration):\n{seen}\n\
         Design 3 to 10 milestones the learner can actually perform inside the application, in the video's \
         order. Skip parts that only talk, or happen outside the app (downloading, installing).\n\
         For each milestone, in English:\n\
         - goal: an imperative sub-goal (e.g. \"Add a torus\").\n\
         - done_when: the intended state, checkable on a screenshot of the learner's screen; describe the state, \
           not a specific object they may not have.\n\
         - hints: the GUI paths and shortcuts the video itself shows or says for it (from the notes above); \
           do not add ones from memory.\n\
         - teach: one sentence the video explains about the concept, or empty.\n\
         - video_at: the second in the video where it is shown.\n\
         Also: a short title (max 6 words), the app name, and the overall goal as an imperative sentence.",
        v.title, v.uploader
    );
    let schema = json!({
        "type": "object",
        "properties": {
            "title": { "type": "string" },
            "app": { "type": "string" },
            "goal": { "type": "string" },
            "milestones": { "type": "array", "minItems": 2, "maxItems": 10, "items": {
                "type": "object",
                "properties": {
                    "goal": { "type": "string" },
                    "done_when": { "type": "string" },
                    "hints": { "type": "array", "items": { "type": "string" }, "maxItems": 4 },
                    "teach": { "type": "string" },
                    "video_at": { "type": "integer" }
                },
                "required": ["goal", "done_when", "hints", "teach", "video_at"]
            }}
        },
        "required": ["title", "app", "goal", "milestones"]
    });
    // Designing benefits from a little thinking (unlike single grounding calls).
    let body = json!({
        "model": holo::smart_model(),
        "messages": [{ "role": "user", "content": prompt }],
        "temperature": 0.0,
        "structured_outputs": { "json": schema },
        "reasoning_effort": "low",
    });
    let (msg, ms) = holo.chat(&body).await?;
    let raw = msg["content"].as_str().ok_or("Holo returned no tutorial")?;
    crate::debug::record("yt_design", &holo::smart_model(), &[], &prompt, raw, ms);
    serde_json::from_str(raw.trim().trim_start_matches("```json").trim_end_matches("```"))
        .map_err(|e| format!("Unexpected tutorial JSON ({e})"))
}

#[derive(Serialize)]
pub struct Imported {
    pub id: String,
    pub title: String,
    pub app: String,
    pub milestones: usize,
    pub language: Option<String>,
}

/// The whole pipeline; `report` receives each stage. Saves and returns the tutorial.
pub async fn run_import(
    holo: &Holo,
    url: &str,
    report: impl Fn(&'static str, String),
) -> Result<(Tutorial, Option<String>), String> {
    if !is_youtube(url) {
        return Err("Not a YouTube link".into());
    }
    report("video", "Reading the video…".into());
    let u = url.to_string();
    let video = tauri::async_runtime::spawn_blocking(move || metadata(&u)).await.map_err(|e| e.to_string())??;
    let dir = std::env::temp_dir().join("h-tutor-youtube").join(tutorial::slug(&video.id));
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;

    report("video", format!("Downloading “{}”…", video.title));
    let (u, d) = (video.url.clone(), dir.clone());
    let (video_file, audio) = tauri::async_runtime::spawn_blocking(move || download(&u, &d))
        .await
        .map_err(|e| e.to_string())??;

    report("transcript", "Transcribing with Gladia…".into());
    let segments = video.segments.clone();
    let (vf, d) = (video_file.clone(), dir.clone());
    let frames_task = tauri::async_runtime::spawn_blocking(move || key_frames(&vf, &segments, &d));
    let (utterances, language) = transcribe(&audio).await?;
    let frames = frames_task.await.map_err(|e| e.to_string())??;

    report("reading", format!("Holo is watching {} key moments…", frames.len()));
    let notes = read_frames(holo, &frames, &video.segments, &utterances).await?;

    report("designing", "Holo is designing the milestones…".into());
    let plan = design(holo, &video, &notes).await?;

    let milestones: Vec<Milestone> = plan
        .milestones
        .into_iter()
        .enumerate()
        .map(|(i, m)| Milestone {
            id: format!("m{}", i + 1),
            goal: m.goal,
            done_when: m.done_when,
            hints: m.hints,
            teach: Some(m.teach).filter(|t| !t.trim().is_empty()),
            video_at: m.video_at,
            ..Default::default()
        })
        .collect();
    let t = Tutorial {
        id: tutorial::slug(&format!("{} {} {}", plan.app, plan.title, video.id)),
        version: 1,
        title: plan.title,
        app: App { name: plan.app, bundle_id: None, min_version: None },
        goal: plan.goal,
        language: language.clone(),
        source: "youtube".into(),
        source_url: Some(video.url.clone()),
        start: None,
        milestones,
    };
    tutorial::save(&t)?;
    report("saved", format!("“{}” is in your library", t.title));
    Ok((t, language))
}

/// Imports a YouTube video, reporting each stage to the bar.
#[tauri::command]
pub async fn import_youtube(url: String, app: AppHandle, state: tauri::State<'_, crate::AppState>) -> Result<Imported, String> {
    let (t, language) = run_import(&state.holo, &url, |stage, detail| progress(&app, stage, detail)).await?;
    Ok(Imported { id: t.id, title: t.title, app: t.app.name, milestones: t.milestones.len(), language })
}

#[cfg(test)]
mod tests {
    /// End-to-end on a real video (network, Gladia and Holo keys needed):
    /// `cargo test --lib youtube -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn imports_a_real_video() {
        let _ = dotenvy::from_path(concat!(env!("CARGO_MANIFEST_DIR"), "/../.env"));
        let holo = crate::holo::Holo::new();
        let started = std::time::Instant::now();
        let (t, lang) = tauri::async_runtime::block_on(super::run_import(
            &holo,
            "https://www.youtube.com/watch?v=B0J27sf9N1Y",
            |stage, detail| println!("[{:>5.1}s] {stage}: {detail}", started.elapsed().as_secs_f32()),
        ))
        .unwrap();
        println!("{} ({} milestones, {:?})", t.title, t.milestones.len(), lang);
        for m in &t.milestones {
            println!("  @{:?}s {} | done when: {} | hints: {:?}", m.video_at, m.goal, m.done_when, m.hints);
        }
        assert!(t.milestones.len() >= 2);
    }
}
