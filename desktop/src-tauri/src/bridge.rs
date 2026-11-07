use crate::{
    coordinates::{Monitor, Rect},
    guide, input, native,
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
pub fn render_ack(
    window: WebviewWindow,
    state: tauri::State<'_, Arc<State>>,
    command_id: String,
) -> Result<(), String> {
    if window.label() != "guide" || uuid::Uuid::parse_str(&command_id).is_err() {
        return Err("invalid render acknowledgement".into());
    }
    state.send(
        "input.result",
        json!({"command_id":command_id,"status":"ok",
                                     "detail":"rendered"}),
        None,
    )
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
    let token = input::grant(&state)?;
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
    guide::clear(&app);
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
    capture_requested(&app, state.inner(), crop, None, None).await
}

pub async fn capture_requested(
    app: &AppHandle,
    state: &Arc<State>,
    crop: Rect,
    request: Option<(String, u64)>,
    target: Option<String>,
) -> Result<Value, String> {
    let _lock = state.capture_lock.lock().await;
    if !state.connected.load(Ordering::SeqCst) || !native::permissions().screen {
        return Err("Engine déconnecté".into());
    }
    if request
        .as_ref()
        .is_some_and(|(_, revision)| *revision != state.revision.load(Ordering::SeqCst))
    {
        return Err("Capture périmée".into());
    }
    if !crop.valid()
        || crop.width * crop.height > 16_777_216.0
        || [crop.x, crop.y, crop.width, crop.height]
            .iter()
            .any(|v| v.fract() != 0.)
    {
        return Err("Capture trop grande ou rectangle non entier".into());
    }
    let monitor = native::monitors()?
        .into_iter()
        .find(|m| m.contains(crop))
        .ok_or("Région hors moniteur ou à cheval sur deux moniteurs")?;
    let started = Instant::now();
    let image = capture_without_overlays(app, crop, &monitor).await?;
    let (image, image_width, image_height, reference) =
        tokio::task::spawn_blocking(move || bounded_image(&image))
            .await
            .map_err(|e| e.to_string())??;
    eprintln!(
        "desktop latency capture_ms={:.2}",
        started.elapsed().as_secs_f64() * 1000.
    );
    let id = uuid::Uuid::new_v4().to_string();
    let revision = state.revision.load(Ordering::SeqCst);
    let mut payload = json!({"capture_id":id, "ui_revision":revision, "crop":crop,
        "scale":monitor.scale, "monitor_id":monitor.id,
        "image_size":{"width":image_width,"height":image_height},
        "image_ref":format!("data:image/png;base64,{}", base64::engine::general_purpose::STANDARD.encode(image))});
    if let Some((request_id, expected)) = request {
        if expected != revision {
            return Err("Capture périmée".into());
        }
        payload["request_id"] = json!(request_id);
    }
    if let Some(target) = target {
        payload["app"] = json!(target);
    }
    if !capture_fits(&state.session, &payload) {
        return Err(
            "Capture trop volumineuse pour le transport ; partager une région plus petite".into(),
        );
    }
    let mut captures = state.captures.lock().unwrap();
    captures.clear();
    captures.insert(
        id,
        Capture {
            reference,
            encoded_size: (image_width, image_height),
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

struct RestoreWindows<F: FnOnce()>(Option<F>);

impl<F: FnOnce()> Drop for RestoreWindows<F> {
    fn drop(&mut self) {
        if let Some(restore) = self.0.take() {
            restore();
        }
    }
}

async fn without_overlays<T>(
    hide: impl FnOnce() -> Result<(), String>,
    restore: impl FnOnce(),
    capture: impl std::future::Future<Output = Result<T, String>>,
) -> Result<T, String> {
    let _restore = RestoreWindows(Some(restore));
    hide()?;
    capture.await
}

pub async fn capture_without_overlays(
    app: &AppHandle,
    crop: Rect,
    monitor: &Monitor,
) -> Result<Vec<u8>, String> {
    #[cfg(target_os = "macos")]
    let _ = app;
    let monitor = monitor.clone();
    without_overlays(
        || {
            #[cfg(not(target_os = "macos"))]
            for window in app.webview_windows().values() {
                window.hide().map_err(|e| e.to_string())?;
            }
            Ok(())
        },
        || {
            #[cfg(not(target_os = "macos"))]
            guide::restore(app);
        },
        async move {
            #[cfg(not(target_os = "macos"))]
            tokio::time::sleep(Duration::from_millis(80)).await;
            tokio::task::spawn_blocking(move || native::capture(crop, &monitor))
                .await
                .map_err(|e| e.to_string())?
        },
    )
    .await
}

fn bounded_image(bytes: &[u8]) -> Result<(Vec<u8>, u32, u32, image::RgbaImage), String> {
    let mut image = image::load_from_memory(bytes).map_err(|_| "PNG invalide")?;
    let reference = image.to_rgba8();
    let factor = (1_048_576. / (image.width() as f64 * image.height() as f64))
        .sqrt()
        .min(8192. / image.width() as f64)
        .min(8192. / image.height() as f64)
        .min(1.);
    if factor < 1. {
        image = image.resize_exact(
            (image.width() as f64 * factor).floor().max(1.) as u32,
            (image.height() as f64 * factor).floor().max(1.) as u32,
            image::imageops::FilterType::Lanczos3,
        );
    }
    let mut output = std::io::Cursor::new(Vec::new());
    image
        .write_to(&mut output, image::ImageFormat::Png)
        .map_err(|_| "Encodage PNG impossible")?;
    Ok((
        output.into_inner(),
        image.width(),
        image.height(),
        reference,
    ))
}

fn capture_fits(session: &str, payload: &Value) -> bool {
    crate::protocol::envelope(session, "capture.result", payload.clone(), None)
        .to_string()
        .len()
        <= crate::protocol::MAX_MESSAGE
}

#[cfg(test)]
mod tests {
    use super::*;
    #[tokio::test]
    async fn proof_capture_excludes_restored_pill_and_restores_afterwards() {
        let visible = std::sync::atomic::AtomicBool::new(true);
        let expected = image::RgbaImage::from_pixel(8, 8, image::Rgba([1, 2, 3, 255]));
        let actual = without_overlays(
            || {
                visible.store(false, Ordering::SeqCst);
                Ok(())
            },
            || visible.store(true, Ordering::SeqCst),
            async {
                let mut actual = expected.clone();
                if visible.load(Ordering::SeqCst) {
                    actual.put_pixel(0, 0, image::Rgba([255, 0, 0, 255]));
                }
                Ok(actual)
            },
        )
        .await
        .unwrap();
        assert_eq!(actual, expected);
        assert!(visible.load(Ordering::SeqCst));
    }

    #[tokio::test]
    async fn overlay_capture_restores_after_errors_and_cancellation() {
        let visible = std::sync::atomic::AtomicBool::new(true);
        for fail_hide in [true, false] {
            let result = without_overlays(
                || {
                    visible.store(false, Ordering::SeqCst);
                    if fail_hide {
                        Err("hide failed".into())
                    } else {
                        Ok(())
                    }
                },
                || visible.store(true, Ordering::SeqCst),
                async { Err::<(), String>("capture failed".into()) },
            )
            .await;
            assert!(result.is_err());
            assert!(visible.load(Ordering::SeqCst));
        }
        let result = tokio::time::timeout(
            Duration::from_millis(1),
            without_overlays(
                || {
                    visible.store(false, Ordering::SeqCst);
                    Ok(())
                },
                || visible.store(true, Ordering::SeqCst),
                std::future::pending::<Result<(), String>>(),
            ),
        )
        .await;
        assert!(result.is_err());
        assert!(visible.load(Ordering::SeqCst));
    }

    #[test]
    fn capture_upload_has_bounded_pixels_without_upscaling() {
        for (width, height) in [(1600, 1000), (3200, 2000), (200, 100), (16000, 32)] {
            let image = image::DynamicImage::new_rgb8(width, height);
            let mut png = std::io::Cursor::new(Vec::new());
            image.write_to(&mut png, image::ImageFormat::Png).unwrap();
            let (png, w, h, reference) = bounded_image(png.get_ref()).unwrap();
            assert_eq!((reference.width(), reference.height()), (width, height));
            assert!(w * h <= 1_048_576 && w <= width && h <= height);
            assert!(w <= 8192 && h <= 8192);
            assert!(image::load_from_memory(&png).is_ok());
            assert!(
                (w as f64 / width as f64 - h as f64 / height as f64).abs()
                    <= 1. / height.min(width) as f64
            );
        }
        assert!(bounded_image(b"invalid").is_err());
    }
    #[test]
    fn oversized_window_capture_cannot_exceed_transport_limit() {
        assert!(capture_fits(
            "s",
            &json!({"image_ref":"data:image/png;base64,fixture"})
        ));
        assert!(capture_fits("s", &json!({})));
        assert!(!capture_fits(
            "s",
            &json!({"image_ref":"x".repeat(crate::protocol::MAX_MESSAGE)})
        ));
    }
}
