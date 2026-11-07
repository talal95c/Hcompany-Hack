#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod a11y;
mod audio;
mod bridge;
mod commands;
mod coordinates;
mod discovery;
mod guide;
mod input;
mod native;
mod protocol;
mod state;
mod transport;
mod tts;

use commands::receive;
use state::{Capture, Lifecycle, State};
use std::{
    collections::{HashMap, VecDeque},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};
use tauri::Manager;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use tokio::sync::{mpsc, watch};

fn main() {
    std::thread::spawn(protocol::warm);
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            bridge::frontend_ready,
            bridge::render_ack,
            bridge::permission_status,
            bridge::permission_request,
            bridge::monitor_list,
            bridge::desktop_status,
            bridge::capture_region,
            bridge::user_intent,
            bridge::consent_grant,
            bridge::stop_actions,
            bridge::ptt,
            bridge::sidecar_start,
            bridge::sidecar_stop,
            bridge::panel_toggle,
            bridge::quit
        ])
        .setup(|app| {
            let guide = app
                .get_webview_window("guide")
                .ok_or("fenêtre guide absente")?;
            guide.set_ignore_cursor_events(true)?;
            guide.hide()?;
            if let Some(m) = guide.primary_monitor()? {
                guide.set_position(*m.position())?;
                guide.set_size(*m.size())?;
            }
            let pill = app
                .get_webview_window("pill")
                .ok_or("fenêtre pill absente")?;
            pill.set_ignore_cursor_events(true)?;
            let (tx, rx) = mpsc::channel(32);
            let (lifecycle, control) = watch::channel(Lifecycle::Running);
            let (frontend, _) = watch::channel(0);
            let session = std::env::var("ENGINE_SESSION_ID")
                .unwrap_or_else(|_| uuid::Uuid::new_v4().to_string());
            let state = Arc::new(State {
                session: session.clone(),
                token: std::env::var("ENGINE_SESSION_TOKEN")
                    .unwrap_or_else(|_| uuid::Uuid::new_v4().to_string()),
                tx: tx.clone(),
                lifecycle,
                frontend,
                guide: guide::Visibility::default(),
                connected: Arc::new(AtomicBool::new(false)),
                stopped: Arc::new(AtomicBool::new(true)),
                shutdown_done: AtomicBool::new(false),
                consent: Arc::new(Mutex::new(None)),
                captures: Mutex::new(HashMap::new()),
                input_lock: Arc::new(tokio::sync::Mutex::new(())),
                a11y: a11y::Service::default(),
                focus: discovery::Tracker::default(),
                capture_lock: tokio::sync::Mutex::new(()),
                generation: AtomicU64::new(0),
                revision: AtomicU64::new(0),
                seen: Mutex::new(VecDeque::new()),
                results: Mutex::new(HashMap::new()),
                audio: audio::Audio::new(app.handle().clone(), tx, session),
            });
            app.manage(state.clone());
            app.global_shortcut()
                .on_shortcut("Ctrl+Shift+Escape", |app, _, event| {
                    if event.state == ShortcutState::Pressed {
                        let state = app.state::<Arc<State>>();
                        input::stop(&state);
                        let _ = state.send(
                            "user.intent",
                            serde_json::json!({"text":"stop","source":"bouton"}),
                            None,
                        );
                        guide::clear(app);
                    }
                })?;
            let shortcut =
                std::env::var("HCOMPANY_PTT_HOTKEY").unwrap_or_else(|_| "Ctrl+Shift+Space".into());
            let startup_error = if let Err(error) =
                app.global_shortcut()
                    .on_shortcut(shortcut.as_str(), |app, _, event| {
                        let state = app.state::<Arc<State>>();
                        if event.state == ShortcutState::Pressed
                            && state.connected.load(Ordering::SeqCst)
                        {
                            state.audio.start();
                        } else {
                            state.audio.stop();
                        }
                    }) {
                eprintln!("desktop PTT hotkey unavailable: {error}");
                Some("Raccourci vocal indisponible ; utilisez le bouton micro.")
            } else {
                None
            };
            let hover_app = app.handle().clone();
            std::thread::spawn(move || loop {
                let state = hover_app.state::<Arc<State>>();
                if state.shutdown_done.load(Ordering::SeqCst) {
                    break;
                }
                if let Some(pill) = hover_app.get_webview_window("pill") {
                    if let (Ok(cursor), Ok(pos), Ok(size)) = (
                        hover_app.cursor_position(),
                        pill.outer_position(),
                        pill.outer_size(),
                    ) {
                        let inside = cursor.x >= pos.x as f64
                            && cursor.y >= pos.y as f64
                            && cursor.x < pos.x as f64 + size.width as f64
                            && cursor.y < pos.y as f64 + size.height as f64;
                        let _ = pill.set_ignore_cursor_events(!inside);
                    }
                }
                std::thread::sleep(Duration::from_millis(25));
            });
            tauri::async_runtime::spawn(transport::run(
                app.handle().clone(),
                state,
                rx,
                control,
                startup_error,
            ));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("échec du lancement desktop");
    app.run(|app, event| {
        if let tauri::RunEvent::ExitRequested { api, .. } = event {
            let state = app.state::<Arc<State>>();
            if !state.shutdown_done.load(Ordering::SeqCst) {
                api.prevent_exit();
                input::stop(&state);
                let _ = state.lifecycle.send(Lifecycle::Shutdown);
            }
        }
    });
}
