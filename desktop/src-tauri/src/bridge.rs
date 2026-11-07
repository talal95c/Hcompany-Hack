use crate::{
    coordinates::Rect,
    input, native,
    tts::{NoSpeech, Speech},
    Capture, Lifecycle, State,
};
use base64::Engine;
use serde_json::{json, Value};
use std::{
    sync::{atomic::Ordering, Arc},
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, Manager, WebviewWindow};

fn pill(window: &WebviewWindow) -> Result<(), String> {
    if window.label() != "pill" {
        return Err("interactive window required".into());
    }
    Ok(())
}

#[tauri::command]
pub fn frontend_ready(
    window: WebviewWindow,
    state: tauri::State<'_, Arc<State>>,
) -> Result<(), String> {
    state.frontend_ready(window.label())
}

#[tauri::command]
pub fn permission_status() -> native::Permissions {
    native::permissions()
}

#[tauri::command]
pub async fn permission_request(
    app: AppHandle,
    window: WebviewWindow,
    kind: String,
) -> Result<native::Permissions, String> {
    pill(&window)?;
    tokio::task::spawn_blocking(move || native::request_permission(&kind))
        .await
        .map_err(|e| e.to_string())??;
    let permissions = native::permissions();
    let state = app.state::<Arc<State>>();
    let _ = state.send(
        "permissions",
        serde_json::to_value(&permissions).unwrap(),
        None,
    );
    let _ = app.emit("permission:changed", &permissions);
    Ok(permissions)
}

#[tauri::command]
pub fn monitor_list() -> Result<Vec<crate::coordinates::Monitor>, String> {
    native::monitors()
}

#[tauri::command]
pub fn desktop_status(state: tauri::State<'_, Arc<State>>) -> Value {
    json!({"connected":state.connected.load(Ordering::SeqCst), "permissions":native::permissions(),
        "ptt_hotkey":std::env::var("HCOMPANY_PTT_HOTKEY").unwrap_or_else(|_| "Ctrl+Shift+Space".into()),
        "stop_hotkey":"Ctrl+Shift+Escape"})
}

#[tauri::command]
pub fn user_intent(
    window: WebviewWindow,
    state: tauri::State<'_, Arc<State>>,
    text: String,
) -> Result<(), String> {
    pill(&window)?;
    if text.trim().is_empty() || text.len() > 4096 {
        return Err("Texte vide ou trop long".into());
    }
    state.send(
        "user.intent",
        json!({"text":text, "source":"clavier"}),
        None,
    )
}

#[tauri::command]
pub fn consent_grant(
    window: WebviewWindow,
    state: tauri::State<'_, Arc<State>>,
) -> Result<(), String> {
    pill(&window)?;
    if !state.connected.load(Ordering::SeqCst) {
        return Err("Engine déconnecté".into());
    }
    let token = input::grant(&state);
    state.send("user.intent", json!({"text":json!({"intent":"fais-le","consent_token":token}).to_string(),"source":"bouton"}), None)
}

#[tauri::command]
pub fn stop_actions(app: AppHandle, state: tauri::State<'_, Arc<State>>) {
    input::stop(&state);
    NoSpeech.stop();
    let _ = state.send(
        "user.intent",
        json!({"text":"stop", "source":"bouton"}),
        None,
    );
    let _ = app.emit("guide:clear", ());
}

#[tauri::command]
pub fn ptt(state: tauri::State<'_, Arc<State>>, active: bool) -> Result<(), String> {
    if active {
        if !state.connected.load(Ordering::SeqCst) {
            return Err("Engine déconnecté".into());
        }
        state.audio.start();
    } else {
        state.audio.stop();
    }
    Ok(())
}

#[tauri::command]
pub fn sidecar_start(
    window: WebviewWindow,
    state: tauri::State<'_, Arc<State>>,
) -> Result<(), String> {
    pill(&window)?;
    state
        .lifecycle
        .send(Lifecycle::Running)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn sidecar_stop(
    window: WebviewWindow,
    state: tauri::State<'_, Arc<State>>,
) -> Result<(), String> {
    pill(&window)?;
    input::stop(&state);
    state
        .lifecycle
        .send(Lifecycle::Stopped)
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub fn quit(app: AppHandle) {
    app.exit(0);
}

#[tauri::command]
pub fn panel_toggle(window: WebviewWindow, expanded: bool) -> Result<(), String> {
    pill(&window)?;
    window
        .set_size(tauri::LogicalSize::new(
            430.,
            if expanded { 560. } else { 138. },
        ))
        .map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn capture_region(
    app: AppHandle,
    window: WebviewWindow,
    state: tauri::State<'_, Arc<State>>,
    crop: Rect,
) -> Result<Value, String> {
    pill(&window)?;
    let _lock = state.capture_lock.lock().await;
    if !state.connected.load(Ordering::SeqCst) {
        return Err("Engine déconnecté".into());
    }
    if !crop.valid()
        || crop.width * crop.height > 1_048_576.0
        || [crop.x, crop.y, crop.width, crop.height]
            .iter()
            .any(|v| v.fract() != 0.)
    {
        return Err("Capture limitée à une région entière de 1 Mpx".into());
    }
    let monitor = native::monitors()?
        .into_iter()
        .find(|m| m.contains(crop))
        .ok_or("Région hors moniteur ou à cheval sur deux moniteurs")?;
    let started = Instant::now();
    #[cfg(not(target_os = "macos"))]
    for window in app.webview_windows().values() {
        window.hide().map_err(|e| e.to_string())?;
    }
    #[cfg(not(target_os = "macos"))]
    tokio::time::sleep(Duration::from_millis(80)).await;
    let monitor_for_capture = monitor.clone();
    let image =
        tokio::task::spawn_blocking(move || native::capture(crop, &monitor_for_capture)).await;
    #[cfg(not(target_os = "macos"))]
    for label in ["guide", "pill"] {
        if let Some(window) = app.get_webview_window(label) {
            let _ = window.show();
        }
    }
    let image = image.map_err(|e| e.to_string())??;
    eprintln!(
        "desktop latency capture_ms={:.2}",
        started.elapsed().as_secs_f64() * 1000.
    );
    let id = uuid::Uuid::new_v4().to_string();
    let revision = state.revision.fetch_add(1, Ordering::SeqCst) + 1;
    let payload = json!({"capture_id":id, "ui_revision":revision, "crop":crop,
        "scale":monitor.scale, "monitor_id":monitor.id,
        "image_ref":format!("data:image/png;base64,{}", base64::engine::general_purpose::STANDARD.encode(image))});
    let mut captures = state.captures.lock().unwrap();
    captures.clear();
    captures.insert(
        id,
        Capture {
            crop,
            monitor,
            ui_revision: revision,
            at: Instant::now(),
        },
    );
    drop(captures);
    state.send("capture.result", payload, None)?;
    let result = json!({"ui_revision":revision, "crop":crop});
    let _ = app.emit("capture:result", &result);
    Ok(result)
}
