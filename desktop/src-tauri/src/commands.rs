use crate::{
    guide, input,
    tts::{NoSpeech, Speech},
    State,
};
use serde_json::{json, Value};
use std::{
    sync::{atomic::Ordering, Arc},
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, Manager};

pub async fn receive(app: &AppHandle, state: &Arc<State>, packet: Value) {
    let id = packet["message_id"].as_str().unwrap().to_owned();
    {
        let mut seen = state.seen.lock().unwrap();
        if seen.contains(&id) {
            return;
        }
        seen.push_back(id.clone());
        if seen.len() > 512 {
            seen.pop_front();
        }
    }
    let payload = &packet["payload"];
    match packet["type"].as_str().unwrap() {
        "a11y.request" => {
            let payload = payload.clone();
            let state = state.clone();
            tauri::async_runtime::spawn(async move {
                let result = state.a11y.request(&state, payload).await;
                let _ = state.send("a11y.result", result, Some(&id));
            });
        }
        "ping" => {
            let _ = state.send("pong", payload.clone(), Some(&id));
        }
        "lesson.state" => {
            if let Some(revision) = payload["ui_revision"].as_u64() {
                if revision != state.revision.swap(revision, Ordering::SeqCst) {
                    state.captures.lock().unwrap().clear();
                    guide::clear(app);
                }
            }
            let _ = app.emit("lesson:state", payload);
        }
        "error" => {
            let _ = app.emit("native:error", payload["message"].clone());
        }
        "highlight.rect" => {
            schedule_highlight(app, state, payload, None);
        }
        "capture.request" => {
            let app = app.clone();
            let state = state.clone();
            let payload = payload.clone();
            tauri::async_runtime::spawn(async move {
                let resolved = match capture_scope(&payload) {
                    Ok(CaptureScope::Window(target)) => {
                        crate::discovery::resolve(&state.a11y, &target)
                            .await
                            .map(|w| (w.window_bounds, Some(w.app_id)))
                    }
                    Ok(CaptureScope::Rect(Some(crop))) => Ok((crop, None)),
                    Ok(CaptureScope::Rect(None)) => {
                        crate::native::app_window_rect().map(|r| (r, None))
                    }
                    Err(error) => Err(error),
                };
                let (crop, target) = match resolved {
                    Ok(resolved) => resolved,
                    Err(error) => {
                        let _ = app.emit("native:error", error);
                        return;
                    }
                };
                let request = payload["request_id"].as_str().unwrap().to_owned();
                let revision = payload["ui_revision"].as_u64().unwrap();
                let app = app.clone();
                let state = state.clone();
                tauri::async_runtime::spawn(async move {
                    if let Err(error) = crate::bridge::capture_requested(
                        &app,
                        &state,
                        crop,
                        Some((request, revision)),
                        target,
                    )
                    .await
                    {
                        let _ = app.emit("native:error", error);
                    }
                });
            });
        }
        "command" => {
            if payload["recipient"] != "desktop" {
                return;
            }
            let command = payload["command_id"].as_str().unwrap().to_owned();
            if let Some(result) = state.results.lock().unwrap().get(&command).cloned() {
                let _ = state.send("input.result", result, Some(&id));
                return;
            }
            let generation = payload["generation"].as_u64().unwrap();
            let kind = payload["type"].as_str().unwrap();
            if kind == "stop" {
                input::stop(state);
                guide::clear(app);
                return;
            }
            if generation < state.generation.load(Ordering::SeqCst)
                || payload["deadline_ms"].as_f64().unwrap() <= 0.
            {
                return;
            }
            if generation > state.generation.swap(generation, Ordering::SeqCst) {
                guide::clear(app);
            }
            let p = &payload["payload"];
            match kind {
                "highlight.rect" => {
                    let mut p = p.clone();
                    p["duration_ms"] = json!(p["duration_ms"]
                        .as_f64()
                        .unwrap()
                        .min(payload["deadline_ms"].as_f64().unwrap()));
                    schedule_highlight(app, state, &p, Some(&command));
                }
                "pointer" => pointer(
                    app,
                    state,
                    p,
                    payload["deadline_ms"].as_f64().unwrap(),
                    &command,
                ),
                "success" => {
                    if !payload["expected_scene_revision"].is_null() {
                        let duration_ms = payload["deadline_ms"].as_f64().unwrap().min(2500.);
                        guide::show(
                            app,
                            "guide:success",
                            json!({"text":p["text"],"duration_ms":duration_ms,"command_id":command}),
                            duration_ms,
                        );
                    }
                }
                "say" => {
                    let _ = NoSpeech.speak(p["text"].as_str().unwrap());
                    let _ = app.emit("speech:text", p["text"].clone());
                }
                "input.action" => {
                    state.results.lock().unwrap().insert(command.clone(), json!({"command_id":command,"status":"rejected","detail":"already accepted; never replay"}));
                    let state = state.clone();
                    let app = app.clone();
                    let action = p.clone();
                    let budget = payload["deadline_ms"].as_f64().unwrap().min(10_000.);
                    let received = Instant::now();
                    tokio::task::spawn_blocking(move || {
                        let started = Instant::now();
                        let result = if received.elapsed().as_secs_f64() * 1000. > budget {
                            Err("expired".into())
                        } else {
                            input::perform(&state, &action)
                        };
                        eprintln!(
                            "desktop latency input_ms={:.2} status={}",
                            started.elapsed().as_secs_f64() * 1000.,
                            if result.is_ok() { "ok" } else { "rejected" }
                        );
                        let result = json!({"command_id":command,"status":if result.is_ok() {"ok"} else {"rejected"},"detail":result.err().unwrap_or_else(|| "Action exécutée ; vérification engine requise.".into())});
                        {
                            let mut results = state.results.lock().unwrap();
                            if results.len() > 512 {
                                results.clear();
                            }
                            results.insert(command, result.clone());
                        }
                        let _ = state.send("input.result", result.clone(), Some(&id));
                        let _ = app.emit("input:result", result);
                    });
                }
                _ => {}
            }
        }
        _ => {}
    }
}

enum CaptureScope {
    Window(String),
    Rect(Option<crate::coordinates::Rect>),
}
fn capture_scope(payload: &Value) -> Result<CaptureScope, String> {
    match payload["scope"].as_str() {
        Some("window") if payload["crop"].is_null() => payload["app"]
            .as_str()
            .filter(|a| !a.is_empty())
            .map(|a| CaptureScope::Window(a.into()))
            .ok_or_else(|| "Application de capture manquante".into()),
        None | Some("rect") => {
            if payload["crop"].is_null() {
                Ok(CaptureScope::Rect(None))
            } else {
                serde_json::from_value(payload["crop"].clone())
                    .map(|r| CaptureScope::Rect(Some(r)))
                    .map_err(|_| "Rectangle de capture invalide".into())
            }
        }
        _ => Err("Portée de capture invalide".into()),
    }
}

fn highlight_rect(payload: &Value) -> Option<crate::coordinates::Rect> {
    serde_json::from_value::<crate::coordinates::ScreenRect>(payload["rect"].clone())
        .ok()
        .map(|r| r.rect())
        .filter(|r| r.valid())
}

pub async fn highlight_bounds(
    service: &crate::a11y::Service,
    payload: &Value,
) -> Option<crate::coordinates::Rect> {
    let mut rect = highlight_rect(payload);
    if let (Some(reference), Some(snapshot)) =
        (payload["ref"].as_str(), payload["snapshot_id"].as_str())
    {
        if let Ok(Ok(bounds)) = tokio::time::timeout(
            Duration::from_millis(500),
            service.highlight_bounds(reference, snapshot, payload["app"].as_str()),
        )
        .await
        {
            rect = Some(bounds);
        }
    }
    rect
}

fn schedule_highlight(app: &AppHandle, state: &Arc<State>, payload: &Value, command: Option<&str>) {
    let revision = state.guide.reserve();
    let app = app.clone();
    let state = state.clone();
    let payload = payload.clone();
    let command = command.map(str::to_owned);
    tauri::async_runtime::spawn(async move {
        highlight(&app, &state, &payload, command.as_deref(), revision).await;
    });
}

async fn highlight(
    app: &AppHandle,
    state: &State,
    payload: &Value,
    command: Option<&str>,
    revision: u64,
) {
    let rect = highlight_bounds(&state.a11y, payload).await;
    if !state.connected.load(Ordering::SeqCst) || !state.guide.pending_current(revision) {
        return;
    }
    let Some(rect) = rect.filter(|r| r.valid()) else {
        return;
    };
    let Some(window) = app.get_webview_window("guide") else {
        return;
    };
    let Some(mut monitor) = crate::native::monitors()
        .ok()
        .and_then(|ms| ms.into_iter().find(|m| m.contains(rect)))
    else {
        return;
    };
    if let Ok(monitors) = window.available_monitors() {
        if let Some(native) = monitors.iter().find(|m| {
            m.position().x as f64 == monitor.physical.x
                && m.position().y as f64 == monitor.physical.y
        }) {
            monitor.scale = native.scale_factor();
        }
    }
    let Ok(css) = monitor.overlay_rect(rect) else {
        return;
    };
    let _ = window.set_position(tauri::PhysicalPosition::new(
        monitor.physical.x as i32,
        monitor.physical.y as i32,
    ));
    let _ = window.set_size(tauri::PhysicalSize::new(
        monitor.physical.width as u32,
        monitor.physical.height as u32,
    ));
    let duration = payload["duration_ms"].as_f64().unwrap_or(0.).max(0.);
    let mut event = json!({"rect":css,"color":payload["color"],"label":payload["label"],"duration_ms":duration});
    if let Some(command) = command {
        event["command_id"] = json!(command);
    }
    guide::show_if_current(app, "guide:highlight", event, duration, revision);
}

fn pointer(app: &AppHandle, state: &State, payload: &Value, budget: f64, command: &str) {
    let captures = state.captures.lock().unwrap();
    let Some(c) = captures.get(payload["capture_id"].as_str().unwrap()) else {
        return;
    };
    if c.ui_revision != payload["ui_revision"].as_u64().unwrap()
        || c.at.elapsed() > Duration::from_secs(10)
    {
        return;
    }
    let Ok((x, y)) = c.monitor.point(
        c.crop,
        payload["x"].as_f64().unwrap(),
        payload["y"].as_f64().unwrap(),
    ) else {
        return;
    };
    let Some(guide) = app.get_webview_window("guide") else {
        return;
    };
    let mut pos = guide.outer_position().unwrap_or_default();
    if let Ok(monitors) = guide.available_monitors() {
        if let Some(m) = monitors.iter().find(|m| {
            m.position().x as f64 <= c.crop.x
                && m.position().y as f64 <= c.crop.y
                && (m.position().x as f64 + m.size().width as f64) > c.crop.x
                && (m.position().y as f64 + m.size().height as f64) > c.crop.y
        }) {
            let _ = guide.set_position(*m.position());
            let _ = guide.set_size(*m.size());
            pos = *m.position();
        }
    }
    let scale = guide.scale_factor().unwrap_or(1.);
    #[cfg(target_os = "macos")]
    let (css_x, css_y) = (x - c.monitor.logical_x, y - c.monitor.logical_y);
    #[cfg(not(target_os = "macos"))]
    let (css_x, css_y) = ((x - pos.x as f64) / scale, (y - pos.y as f64) / scale);
    let zone = json!({"x":(c.crop.x-pos.x as f64)/scale,"y":(c.crop.y-pos.y as f64)/scale,"width":c.crop.width/scale,"height":c.crop.height/scale});
    guide::show(
        app,
        "guide:pointer",
        json!({"x":css_x,"y":css_y,"zone":zone,"duration_ms":budget.min(5000.),"command_id":command}),
        budget.min(5000.),
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn highlight_rect_matches_wire_schema_not_capture_shape() {
        let payload =
            json!({"rect":{"x":-100,"y":20,"w":200,"h":80},"color":"red","duration_ms":1000});
        let packet = crate::protocol::envelope("s", "highlight.rect", payload.clone(), None);
        assert!(crate::protocol::validate(&packet, "s").is_ok());
        let rect = highlight_rect(&payload).unwrap();
        assert_eq!(
            (rect.x, rect.y, rect.width, rect.height),
            (-100., 20., 200., 80.)
        );
        assert!(highlight_rect(&json!({"rect":{"x":0,"y":0,"width":10,"height":10}})).is_none());
    }
    #[test]
    fn capture_scope_preserves_legacy_and_requires_window_app() {
        assert!(matches!(
            capture_scope(&json!({"crop":null})),
            Ok(CaptureScope::Rect(None))
        ));
        assert!(matches!(
            capture_scope(&json!({"scope":"rect","crop":{"x":-10,"y":20,"width":40,"height":30}})),
            Ok(CaptureScope::Rect(Some(_)))
        ));
        assert!(
            matches!(capture_scope(&json!({"scope":"window","app":"Editor","crop":null})),Ok(CaptureScope::Window(app)) if app=="Editor")
        );
        for invalid in [
            json!({"scope":"window","crop":null}),
            json!({"scope":"window","app":"","crop":null}),
            json!({"scope":"window","app":"Editor","crop":{}}),
            json!({"scope":"unknown","crop":null}),
            json!({"scope":"rect","crop":{}}),
        ] {
            assert!(capture_scope(&invalid).is_err());
        }
    }
}
