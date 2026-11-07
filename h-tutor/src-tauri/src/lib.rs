mod agent;
mod act;
mod autopilot;
mod autopilot_driver;
mod app_icons;
mod audio_out;
mod ax;
mod capture;
mod debug;
mod clicks;
mod holo;
mod journal;
mod skills;
mod planner;
mod qa;
mod tutorial;
mod panel;
mod search;
mod stt;
mod voice;
mod watch;
mod youtube;
mod tray;

use capture::{capture_primary, Shot};
use holo::Holo;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use tauri::{
    AppHandle, Emitter, Manager, State, WebviewUrl, WebviewWindowBuilder, WindowEvent,
};

/// A click closer than this (in points) to Holo's target counts as the step done.
const HIT_RADIUS: f64 = 48.0;

pub struct AppState {
    pub holo: Holo,
    tts: voice::Tts,
    /// Screen as it was when the current step was pointed at, used as the
    /// "before" image when checking whether the user performed the step.
    before: Mutex<Option<Shot>>,
    /// Current target in global logical coordinates, while the user must click it.
    target: Mutex<Option<(f64, f64)>>,
    /// Accessibility element of the current step (global points), if known:
    /// a click inside it counts as a hit.
    target_rect: Mutex<Option<ax::Element>>,
    last_rect: Mutex<Option<ax::Element>>,
    /// The tutorial in progress (Holo agent conversation).
    session: tauri::async_runtime::Mutex<Option<agent::Session>>,
    /// Bumped on every show/hide so a delayed hide never hides a newer pointer.
    overlay_gen: AtomicU64,
}

#[derive(Deserialize)]
struct NormPoint {
    x: f64,
    y: f64,
}

#[derive(Serialize, Clone)]
struct UserClick {
    hit: bool,
    distance: f64,
}

#[derive(Serialize, Clone)]
struct Pointer {
    /// Logical (CSS) pixels inside the overlay window.
    x: f64,
    y: f64,
    label: String,
    /// The real UI element under the point (x, y, w, h), when the app exposes
    /// an accessibility tree.
    rect: Option<[f64; 4]>,
}

#[derive(Serialize)]
struct Status {
    has_key: bool,
    has_gladia: bool,
    fast_model: String,
    smart_model: String,
    /// Phonon model loaded ("loading" while it downloads/loads).
    tts: String,
}

#[derive(Serialize, Deserialize)]
struct Answer {
    /// Short spoken answer.
    answer: String,
    /// Optional bullet points shown (not read) under the answer.
    details: Vec<String>,
    /// "point" (show `target`), "next" (step is done / skip), "repeat" (show the step again) or "none".
    action: String,
    target: String,
}

async fn shoot() -> Result<Shot, String> {
    tauri::async_runtime::spawn_blocking(capture_primary)
        .await
        .map_err(|e| e.to_string())?
}

#[tauri::command]
fn status() -> Status {
    Status {
        has_key: holo::api_key().is_some(),
        has_gladia: stt::has_key(),
        fast_model: holo::fast_model(),
        smart_model: holo::smart_model(),
        tts: voice::STATE.lock().unwrap().clone(),
    }
}

/// Localizes `target` on screen with Holo and moves the ghost cursor there.
#[tauri::command]
async fn locate(
    target: String,
    label: String,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<Pointer, String> {
    app.emit_to("overlay", "pointer:thinking", ()).ok();
    let shot = shoot().await?;
    let schema = json!({
        "type": "object",
        "properties": {
            "x": { "type": "integer", "minimum": 0, "maximum": 1000, "description": "X coordinate as integer in [0, 1000]" },
            "y": { "type": "integer", "minimum": 0, "maximum": 1000, "description": "Y coordinate as integer in [0, 1000]" }
        },
        "required": ["x", "y"]
    });
    let prompt = format!(
        "Localize an element on the GUI image according to the provided target and output a click position.\n \
         * You must output a valid JSON following the format: {schema}\n Your target is:\n{target}"
    );
    let (p, log_id): (NormPoint, _) = state
        .holo
        .structured_logged("locate", &holo::fast_model(), &[&shot.data_uri], &prompt, schema)
        .await
        .inspect_err(|_| {
            app.emit_to("overlay", "pointer:hide", ()).ok();
        })?;
    if let Some(id) = log_id {
        debug::mark_point(&id, &shot.data_uri, p.x, p.y);
    }

    let (pointer, global) = to_overlay_coords(&app, p.x, p.y, label)?;
    *state.before.lock().unwrap() = Some(shot);
    *state.target.lock().unwrap() = Some(global);
    state.overlay_gen.fetch_add(1, Ordering::SeqCst);
    set_overlay_visible(&app, true);
    app.emit_to("overlay", "pointer:show", pointer.clone()).ok();
    Ok(pointer)
}

/// Maps Holo's normalized (0..1000) point on the primary monitor to logical
/// pixels inside the overlay window (which may be offset, e.g. by the menu bar).
/// Also returns the point in global logical coordinates, to match real clicks.
fn to_overlay_coords(
    app: &AppHandle,
    nx: f64,
    ny: f64,
    label: String,
) -> Result<(Pointer, (f64, f64)), String> {
    let monitor = app
        .primary_monitor()
        .map_err(|e| e.to_string())?
        .ok_or("No primary display")?;
    let overlay = app.get_webview_window("overlay").ok_or("Overlay window missing")?;
    let origin = overlay.outer_position().map_err(|e| e.to_string())?;
    let scale = monitor.scale_factor();
    let (phys_x, phys_y) = normalized_screen_point(app, nx, ny)?;
    let pointer = Pointer {
        x: (phys_x - origin.x as f64) / scale,
        y: (phys_y - origin.y as f64) / scale,
        label,
        rect: None,
    };
    Ok((pointer, (phys_x / scale, phys_y / scale)))
}

fn normalized_screen_point(app: &AppHandle, nx: f64, ny: f64) -> Result<(f64, f64), String> {
    let monitor = app.primary_monitor().map_err(|e| e.to_string())?.ok_or("Écran principal introuvable")?;
    act::screen_point(nx, ny, monitor.position().x as f64, monitor.position().y as f64,
        monitor.size().width as f64, monitor.size().height as f64)
}

/// Shows the step's pointer (click / write / scroll) or hides it.
fn apply_step(app: &AppHandle, state: &AppState, step: &agent::Step) -> Result<(), String> {
    match (step.kind.as_str(), step.point) {
        ("click" | "write" | "scroll", Some((x, y))) => {
            let (mut pointer, global) = to_overlay_coords(app, x, y, step.instruction.clone())?;
            let rect = state.last_rect.lock().unwrap().clone();
            if let (Some(r), Some(overlay)) = (&rect, app.get_webview_window("overlay")) {
                let scale = overlay.scale_factor().unwrap_or(2.0);
                let origin = overlay.outer_position().map_err(|e| e.to_string())?;
                let (ox, oy) = (origin.x as f64 / scale, origin.y as f64 / scale);
                pointer.rect = Some([r.x - ox, r.y - oy, r.w, r.h]);
            }
            // Only clicks and fields are validated by a real click on them.
            *state.target.lock().unwrap() = (step.kind != "scroll").then_some(global);
            *state.target_rect.lock().unwrap() = rect.filter(|_| step.kind != "scroll");
            state.overlay_gen.fetch_add(1, Ordering::SeqCst);
            set_overlay_visible(app, true);
            app.emit_to("overlay", "pointer:show", pointer).ok();
        }
        _ => {
            *state.target.lock().unwrap() = None;
            *state.target_rect.lock().unwrap() = None;
            app.emit_to("overlay", "pointer:hide", ()).ok();
        }
    }
    Ok(())
}

/// One harness step, with the accessibility tree read in parallel: once Holo
/// has picked its point, the real element under it is looked up so the
/// pointer can outline it and clicks anywhere on it count.
async fn advance_step(
    app: &AppHandle,
    state: &AppState,
    session: &mut agent::Session,
    event: Option<String>,
    only_if_changed: bool,
) -> Result<agent::Step, String> {
    let ax_task = tauri::async_runtime::spawn_blocking(ax::snapshot_frontmost);
    let step = agent::advance(&state.holo, session, event, only_if_changed).await?;
    if step.unchanged {
        return Ok(step);
    }
    let mut rect = None;
    if let Some((nx, ny)) = step.point {
        let started = std::time::Instant::now();
        if let Ok(Ok(elements)) = tokio::time::timeout(std::time::Duration::from_millis(1500), ax_task).await {
            let monitor = app.primary_monitor().ok().flatten();
            if let (Some(m), Ok((_, (gx, gy)))) = (monitor, to_overlay_coords(app, nx, ny, String::new())) {
                let area = m.size().width as f64 * m.size().height as f64 / m.scale_factor().powi(2);
                rect = ax::element_at(&elements, gx, gy, area);
            }
            // When nothing contains the point, log the closest elements to
            // understand why (e.g. controls a web app does not expose).
            let nearest: Vec<Value> = if rect.is_none() {
                let (gx, gy) = to_overlay_coords(app, nx, ny, String::new()).map(|(_, g)| g).unwrap_or_default();
                let mut by_dist: Vec<(f64, &ax::Element)> = elements
                    .iter()
                    .map(|e| {
                        let dx = (e.x - gx).max(gx - (e.x + e.w)).max(0.0);
                        let dy = (e.y - gy).max(gy - (e.y + e.h)).max(0.0);
                        ((dx * dx + dy * dy).sqrt(), e)
                    })
                    .collect();
                by_dist.sort_by(|a, b| a.0.total_cmp(&b.0));
                by_dist
                    .iter()
                    .take(3)
                    .map(|(d, e)| json!({ "role": e.role, "name": e.name, "bounds": [e.x, e.y, e.w, e.h], "distance": d.round() }))
                    .collect()
            } else {
                Vec::new()
            };
            journal::event(
                "ax",
                json!({
                    "elements": elements.len(),
                    "waited_ms": started.elapsed().as_millis(),
                    "element": rect.as_ref().map(|r| json!({ "role": r.role, "name": r.name, "bounds": [r.x, r.y, r.w, r.h] })),
                    "nearest": nearest,
                }),
            );
        }
    }
    *state.last_rect.lock().unwrap() = rect;
    Ok(step)
}

/// Starts a tutorial for `goal` and returns its first step.
#[tauri::command]
async fn tutor_start(
    goal: Option<String>,
    tutorial_id: Option<String>,
    lang: Option<String>,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<agent::Step, String> {
    if autopilot::is_running() { return Err("Rio exécute déjà une tâche".into()); }
    let mut guard = state.session.lock().await;
    if autopilot::is_running() { return Err("Rio exécute déjà une tâche".into()); }
    // Both entries end up as a milestone graph: a saved tutorial, or one
    // planned by Holo from the goal and the current screen.
    let tutorial = match (tutorial_id, goal) {
        (Some(id), _) => tutorial::load(&id)?,
        (None, Some(goal)) => {
            app.emit_to("main", "tutor:planning", ()).ok();
            let shot = shoot().await?;
            planner::plan(&state.holo, &goal, &shot).await?
        }
        (None, None) => return Err("Nothing to start".into()),
    };
    let session = guard.insert(agent::Session::new(tutorial, lang.as_deref()));
    app.emit_to("main", "tutor:plan", session.progress()).ok();
    app.emit_to("overlay", "pointer:thinking", ()).ok();
    let step = advance_step(&app, &state, session, None, false).await?;
    apply_step(&app, &state, &step)?;
    arm_watch(session, &step);
    Ok(step)
}

/// Reports what the learner did and returns the next step. With
/// `only_if_changed`, returns the current step (flagged `unchanged`) without
/// calling Holo when the screen did not change.
#[tauri::command]
async fn tutor_next(
    event: String,
    only_if_changed: bool,
    lang: Option<String>,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<agent::Step, String> {
    let mut guard = state.session.lock().await;
    let session = guard.as_mut().ok_or("No tutorial in progress")?;
    session.set_lang(lang.as_deref());
    watch::disarm();
    if !only_if_changed {
        app.emit_to("overlay", "pointer:thinking", ()).ok();
    }
    let step = advance_step(&app, &state, session, Some(event), only_if_changed).await?;
    if !step.unchanged {
        apply_step(&app, &state, &step)?;
    }
    arm_watch(session, &step);
    Ok(step)
}

/// Watches the screen for the learner's action on this step.
fn arm_watch(session: &agent::Session, step: &agent::Step) {
    match (&session.before, step.kind.as_str()) {
        (_, "done") | (None, _) => watch::disarm(),
        (Some(before), kind) => watch::arm(before.thumb.clone(), kind == "write"),
    }
}

/// Resumes after a question: shows the step again and watches the screen
/// from how it looks now (the learner may have looked around meanwhile).
#[tauri::command]
async fn tutor_resume(app: AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    let guard = state.session.lock().await;
    let Some(session) = guard.as_ref() else { return Ok(()) };
    apply_step(&app, &state, &session.step)?;
    if session.step.kind != "done" {
        let now = tauri::async_runtime::spawn_blocking(capture::capture_thumb)
            .await
            .map_err(|e| e.to_string())??;
        watch::arm(now, session.step.kind == "write");
    }
    Ok(())
}

/// Skips the current milestone and returns the first step of the next one.
#[tauri::command]
async fn tutor_skip_milestone(
    lang: Option<String>,
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<agent::Step, String> {
    watch::disarm();
    let mut guard = state.session.lock().await;
    let session = guard.as_mut().ok_or("No tutorial in progress")?;
    session.set_lang(lang.as_deref());
    session.skip_milestone();
    app.emit_to("overlay", "pointer:thinking", ()).ok();
    let step = advance_step(&app, &state, session, None, false).await?;
    apply_step(&app, &state, &step)?;
    arm_watch(session, &step);
    Ok(step)
}

/// The learner's language for something they said or typed: Gladia's
/// detection when spoken (audio is the most reliable signal), else the
/// text's language when detection is confident, else `fallback`.
#[tauri::command]
fn resolve_lang(text: String, spoken: Option<String>, fallback: Option<String>) -> String {
    let supported = |l: &String| agent::language_name(l).is_some();
    spoken
        .filter(supported)
        .or_else(|| voice::detect(&text).map(String::from))
        .or(fallback.filter(supported))
        .unwrap_or_else(|| "en".into())
}

#[tauri::command]
fn list_tutorials() -> Vec<tutorial::Summary> {
    tutorial::list()
}

/// Saves the current (or just finished) run as a tutorial in the library,
/// with the path actually taken as each milestone's hints.
#[tauri::command]
async fn save_tutorial(state: State<'_, AppState>) -> Result<String, String> {
    let guard = state.session.lock().await;
    let session = guard.as_ref().ok_or("No tutorial to save")?;
    let t = agent::to_tutorial(session);
    tutorial::save(&t)?;
    journal::event("saved_as_tutorial", json!({ "tutorial_id": t.id, "version": t.version }));
    Ok(t.title)
}

/// Shows the current step's pointer again, without asking Holo.
#[tauri::command]
async fn tutor_repoint(app: AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    let guard = state.session.lock().await;
    if let Some(session) = guard.as_ref() {
        apply_step(&app, &state, &session.step)?;
    }
    Ok(())
}

#[tauri::command]
async fn tutor_stop(app: AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    watch::disarm();
    let mut guard = state.session.lock().await;
    if guard.as_ref().is_some_and(|s| !s.finished) {
        journal::end("abandoned");
    }
    *guard = None;
    *state.target.lock().unwrap() = None;
    app.emit_to("overlay", "pointer:hide", ()).ok();
    Ok(())
}

/// The app, for modules that emit UI events without a handle (live reasoning).
pub static APP: std::sync::OnceLock<AppHandle> = std::sync::OnceLock::new();

/// Shows what Holo is thinking about, live, while it decides the next step:
/// the sentence being written, at most every 150 ms.
pub fn emit_thinking(reasoning: &str) {
    static LAST: Mutex<Option<std::time::Instant>> = Mutex::new(None);
    {
        let mut last = LAST.lock().unwrap();
        if last.is_some_and(|t| t.elapsed() < std::time::Duration::from_millis(150)) {
            return;
        }
        *last = Some(std::time::Instant::now());
    }
    let Some(app) = APP.get() else { return };
    let text = reasoning.trim();
    let sentences: Vec<&str> = text.split_inclusive(['.', '!', '?', '\n']).map(str::trim).filter(|s| !s.is_empty()).collect();
    let mut snippet = sentences.last().copied().unwrap_or("").to_string();
    // A sentence just started: keep the previous one for context.
    if snippet.len() < 30 && sentences.len() > 1 {
        snippet = format!("{} {snippet}", sentences[sentences.len() - 2]);
    }
    let chars: Vec<char> = snippet.chars().collect();
    let snippet: String = if chars.len() > 150 {
        format!("…{}", chars[chars.len() - 149..].iter().collect::<String>())
    } else {
        snippet
    };
    app.emit_to("main", "holo:thinking", snippet).ok();
}

/// A status line in the bar while Holo works (e.g. "Searching Blender docs…").
pub fn emit_status(text: &str) {
    if let Some(app) = APP.get() {
        app.emit_to("main", "holo:thinking", text).ok();
    }
}

/// Bumped by every `speak` / `stop_speaking`: a slow synthesis that was
/// superseded meanwhile is dropped instead of played.
static SPEECH_GEN: AtomicU64 = AtomicU64::new(0);

/// Speaks `text` with Phonon, played natively (not through the webview,
/// whose autoplay policy can silently mute the panel).
#[tauri::command]
async fn speak(text: String, lang: Option<String>, app: AppHandle) -> Result<(), String> {
    let ticket = SPEECH_GEN.fetch_add(1, Ordering::SeqCst) + 1;
    audio_out::stop();
    let app2 = app.clone();
    let (pcm, rate) = tauri::async_runtime::spawn_blocking(move || app2.state::<AppState>().tts.say(text, lang))
        .await
        .map_err(|e| e.to_string())?
        .inspect_err(|e| eprintln!("[speak] {e}"))?;
    if SPEECH_GEN.load(Ordering::SeqCst) == ticket {
        audio_out::play(&pcm, rate).inspect_err(|e| eprintln!("[speak] {e}"))?;
    }
    Ok(())
}

#[tauri::command]
fn stop_speaking() {
    SPEECH_GEN.fetch_add(1, Ordering::SeqCst);
    audio_out::stop();
}

/// Speaks `text` with Phonon. Returns raw audio: a little-endian u32 sample
/// rate followed by mono f32 little-endian samples.
#[tauri::command]
async fn say(text: String, lang: Option<String>, app: AppHandle) -> Result<tauri::ipc::Response, String> {
    let app2 = app.clone();
    let (pcm, rate) = tauri::async_runtime::spawn_blocking(move || app2.state::<AppState>().tts.say(text, lang))
        .await
        .map_err(|e| e.to_string())??;
    let mut bytes = Vec::with_capacity(4 + pcm.len() * 4);
    bytes.extend_from_slice(&rate.to_le_bytes());
    for s in pcm {
        bytes.extend_from_slice(&s.to_le_bytes());
    }
    Ok(tauri::ipc::Response::new(bytes))
}

/// Answers a spoken question during a tutorial, looking at the screen.
#[tauri::command]
async fn ask(
    question: String,
    instruction: Option<String>,
    target: Option<String>,
    lang: Option<String>,
    state: State<'_, AppState>,
) -> Result<Answer, String> {
    // Questions pause the tutorial: exploring the screen is not doing the step.
    watch::disarm();
    let tutorial = state.session.lock().await.as_ref().map(|s| s.context()).unwrap_or_default();
    let shot = shoot().await?;
    let schema = json!({
        "type": "object",
        "properties": {
            "answer": { "type": "string" },
            "details": { "type": "array", "items": { "type": "string" }, "maxItems": 5 },
            "action": { "type": "string", "enum": ["point", "next", "repeat", "none"] },
            "target": { "type": "string" }
        },
        "required": ["answer", "details", "action", "target"]
    });
    let context = match (&instruction, &target) {
        (Some(i), Some(t)) => format!("{tutorial}The user is on this tutorial step: \"{i}\" (element: {t}).\n"),
        _ => tutorial,
    };
    let language = lang
        .as_deref()
        .and_then(agent::language_name)
        .unwrap_or("the same language as the user's question");
    let prompt = format!(
        "You are a friendly software tutor guiding the user live. The screenshot shows their screen.\n\
         {context}The user paused the tutorial to ask: \"{question}\"\n\n\
         Reply with:\n\
         - answer: one or two short spoken sentences (max 35 words), natural and helpful, in {language} \
           (the language the user used). It is read aloud.\n\
         - details: up to 5 short bullet points shown on screen when a fuller explanation helps \
           (what something is for, options, tips), in the same language. Empty list if not needed. No markdown.\n\
         - action: \"point\" if you should show them an element on screen (then describe it in target), \
           \"next\" if they say the step is done or want to skip it, \"repeat\" if they want the current \
           step shown again, otherwise \"none\".\n\
         - target: precise English description of the element to point at with its location, or empty."
    );
    state
        .holo
        .structured("ask", &holo::smart_model(), &[&shot.data_uri], &prompt, schema)
        .await
}

#[tauri::command]
fn hide_pointer(app: AppHandle, state: State<'_, AppState>) {
    *state.target.lock().unwrap() = None;
    app.emit_to("overlay", "pointer:hide", ()).ok();
    // Let the fade-out play, then take the overlay off screen entirely.
    let ticket = state.overlay_gen.fetch_add(1, Ordering::SeqCst) + 1;
    std::thread::spawn(move || {
        std::thread::sleep(std::time::Duration::from_millis(600));
        if app.state::<AppState>().overlay_gen.load(Ordering::SeqCst) == ticket {
            set_overlay_visible(&app, false);
        }
    });
}

/// Puts the overlay on or off screen without ever activating it or letting it
/// catch the mouse. On macOS this talks to the NSWindow directly:
/// `orderFrontRegardless` shows it without stealing focus, and
/// `ignoresMouseEvents` is re-applied every time so clicks always pass through.
fn set_overlay_visible(app: &AppHandle, visible: bool) {
    let Some(win) = app.get_webview_window("overlay") else { return };
    if visible {
        panel::show(&win, false, panel::LEVEL_OVERLAY);
    }
    let w = win.clone();
    let _ = win.run_on_main_thread(move || {
        #[cfg(target_os = "macos")]
        if let Ok(ptr) = w.ns_window() {
            use objc2::{msg_send, runtime::AnyObject};
            // SAFETY: Tauri hands out a valid NSWindow pointer, used on the main thread.
            unsafe {
                let ns: &AnyObject = &*(ptr as *mut AnyObject);
                let _: () = msg_send![ns, setIgnoresMouseEvents: true];
                if !visible {
                    let _: () = msg_send![ns, orderOut: std::ptr::null::<AnyObject>()];
                }
            }
        }
        #[cfg(not(target_os = "macos"))]
        {
            let _ = w.set_ignore_cursor_events(true);
            let _ = if visible { w.show() } else { w.hide() };
        }
    });
}

/// Called for every real left click on the machine. Clicks on the tutor panel
/// are ignored; others are compared with the current target.
fn on_user_click(app: &AppHandle, click: clicks::Click) {
    if autopilot::is_running() { return; }
    let state = app.state::<AppState>();

    if let Some(panel) = app.get_webview_window("main").filter(|p| p.is_visible().unwrap_or(false)) {
        if let (Ok(pos), Ok(size), Ok(scale)) =
            (panel.outer_position(), panel.outer_size(), panel.scale_factor())
        {
            let (px, py) = (pos.x as f64 / scale, pos.y as f64 / scale);
            let (pw, ph) = (size.width as f64 / scale, size.height as f64 / scale);
            if click.x >= px && click.x <= px + pw && click.y >= py && click.y <= py + ph {
                return;
            }
        }
    }

    let Some((tx, ty)) = *state.target.lock().unwrap() else {
        watch::note_click(false);
        return;
    };
    let distance = ((click.x - tx).powi(2) + (click.y - ty).powi(2)).sqrt();
    // Inside the real element when we know it, else close to Holo's point.
    let hit = match state.target_rect.lock().unwrap().as_ref() {
        Some(r) => r.contains(click.x, click.y, 4.0),
        None => distance <= HIT_RADIUS,
    };
    watch::note_click(hit);
    if hit {
        *state.target.lock().unwrap() = None;
        *state.target_rect.lock().unwrap() = None;
        app.emit_to("overlay", "pointer:hit", ()).ok();
    }
    app.emit_to("main", "user:click", UserClick { hit, distance }).ok();
}

fn setup_windows(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let monitor = app.primary_monitor()?.ok_or("no primary monitor")?;
    let scale = monitor.scale_factor();
    let pos = monitor.position().to_logical::<f64>(scale);
    let size = monitor.size().to_logical::<f64>(scale);

    // Full-screen, transparent, click-through layer that draws the ghost cursor.
    let overlay = WebviewWindowBuilder::new(app, "overlay", WebviewUrl::App("overlay.html".into()))
        .title("Rio Overlay")
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .resizable(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .focused(false)
        .focusable(false)
        .visible(false)
        .visible_on_all_workspaces(true)
        .content_protected(true)
        .position(pos.x, pos.y)
        .inner_size(size.width, size.height)
        .build()?;
    #[cfg(not(target_os = "linux"))]
    overlay.set_ignore_cursor_events(true)?;
    panel::make_panel(&overlay, false, panel::LEVEL_OVERLAY);
    let notch = WebviewWindowBuilder::new(app, "notch", WebviewUrl::App("notch.html".into()))
        .title("Rio · Autopilot")
        .transparent(true)
        .decorations(false)
        .shadow(false)
        .resizable(false)
        .always_on_top(true)
        .skip_taskbar(true)
        .focused(false)
        .visible(false)
        .visible_on_all_workspaces(true)
        .content_protected(true)
        .position(pos.x + (size.width - 460.0) / 2.0, pos.y)
        .inner_size(460.0, 190.0)
        .build()?;
    panel::make_panel(&notch, false, panel::LEVEL_OVERLAY);
    if let Some(bar) = app.get_webview_window("main") {
        panel::make_panel(&bar, true, panel::LEVEL_BAR);
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let _ = dotenvy::dotenv();
    if let Some(d) = debug::dir_path() {
        eprintln!("[debug] Holo calls are logged to {d}");
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_shortcuts(["alt+shift+space"])
                .expect("valid shortcut")
                .with_handler(|app, shortcut, event| {
                    if event.state == tauri_plugin_global_shortcut::ShortcutState::Pressed {
                        if shortcut.matches(tauri_plugin_global_shortcut::Modifiers::empty(), tauri_plugin_global_shortcut::Code::Escape) {
                            autopilot::escape(app);
                        } else {
                            tray::toggle_bar(app);
                        }
                    }
                })
                .build(),
        )
        .manage(AppState {
            holo: Holo::new(),
            tts: voice::Tts::spawn(),
            before: Mutex::new(None),
            target: Mutex::new(None),
            target_rect: Mutex::new(None),
            last_rect: Mutex::new(None),
            overlay_gen: AtomicU64::new(0),
            session: tauri::async_runtime::Mutex::new(None),
        })
        .setup(|app| {
            let _ = APP.set(app.handle().clone());
            // Menu bar app: no Dock icon, no app switcher entry.
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory);
            setup_windows(app)?;
            autopilot::setup(app.handle());
            tray::setup(app)?;
            let handle = app.handle().clone();
            clicks::watch(move |c| on_user_click(&handle, c));
            watch::spawn(app.handle().clone());
            skills::spawn(app.handle().clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            if window.label() == "main" {
                if let WindowEvent::Focused(false) = event {
                    tray::on_bar_blur(window.app_handle());
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            autopilot::autopilot_accept,
            autopilot::autopilot_stop,
            autopilot::autopilot_decline,
            autopilot::autopilot_view,
            skills::skills_list,
            skills::skill_decline,
            skills::skill_propose_now,
            tray::set_tray_status,
            tray::hide_bar,
            tray::resize_bar,
            tray::set_bar_sticky,
            say,
            speak,
            stop_speaking,
            ask,
            tutor_start,
            tutor_next,
            tutor_repoint,
            tutor_resume,
            tutor_skip_milestone,
            list_tutorials,
            resolve_lang,
            qa::answer_question,
            youtube::import_youtube,
            app_icons::app_icons,
            save_tutorial,
            tutor_stop,
            stt::listen_start,
            stt::listen_stop,
            status,
            locate,
            hide_pointer
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
