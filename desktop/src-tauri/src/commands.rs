use crate::{
    input,
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
        "ping" => {
            let _ = state.send("pong", payload.clone(), Some(&id));
        }
        "lesson.state" => {
            state.captures.lock().unwrap().clear();
            let _ = app.emit("guide:clear", ());
            let _ = app.emit("lesson:state", payload);
        }
        "error" => {
            let _ = app.emit("native:error", payload["message"].clone());
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
                let _ = app.emit("guide:clear", ());
                return;
            }
            if generation < state.generation.load(Ordering::SeqCst)
                || payload["deadline_ms"].as_f64().unwrap() <= 0.
            {
                return;
            }
            if generation > state.generation.swap(generation, Ordering::SeqCst) {
                let _ = app.emit("guide:clear", ());
            }
            let p = &payload["payload"];
            match kind {
                "pointer" => pointer(app, state, p, payload["deadline_ms"].as_f64().unwrap()),
                "success" => {
                    if !payload["expected_scene_revision"].is_null() {
                        let _ = app.emit_to("guide", "guide:success", json!({"text":p["text"],"duration_ms":payload["deadline_ms"].as_f64().unwrap().min(2500.)}));
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

fn pointer(app: &AppHandle, state: &State, payload: &Value, budget: f64) {
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
    if let Ok(monitors) = guide.available_monitors() {
        if let Some(m) = monitors.iter().find(|m| {
            m.position().x as f64 <= c.crop.x
                && m.position().y as f64 <= c.crop.y
                && (m.position().x as f64 + m.size().width as f64) > c.crop.x
                && (m.position().y as f64 + m.size().height as f64) > c.crop.y
        }) {
            let _ = guide.set_position(*m.position());
            let _ = guide.set_size(*m.size());
        }
    }
    let scale = guide.scale_factor().unwrap_or(1.);
    let pos = guide.outer_position().unwrap_or_default();
    #[cfg(target_os = "macos")]
    let (css_x, css_y) = (x - c.monitor.logical_x, y - c.monitor.logical_y);
    #[cfg(not(target_os = "macos"))]
    let (css_x, css_y) = ((x - pos.x as f64) / scale, (y - pos.y as f64) / scale);
    let zone = json!({"x":(c.crop.x-pos.x as f64)/scale,"y":(c.crop.y-pos.y as f64)/scale,"width":c.crop.width/scale,"height":c.crop.height/scale});
    let _ = app.emit_to(
        "guide",
        "guide:pointer",
        json!({"x":css_x,"y":css_y,"zone":zone,"duration_ms":budget.min(5000.)}),
    );
}
