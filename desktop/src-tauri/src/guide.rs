use crate::State;
use serde_json::Value;
use std::{
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Arc,
    },
    time::Duration,
};
use tauri::{AppHandle, Emitter, Manager, WebviewWindow};

fn set_visible(window: &WebviewWindow, visible: bool) {
    #[cfg(target_os = "linux")]
    {
        use gtk::prelude::WidgetExt;
        if let Ok(window) = window.gtk_window() {
            if visible {
                window.show_all();
            } else {
                window.hide();
            }
        }
    }
    #[cfg(not(target_os = "linux"))]
    let _ = if visible {
        window.show()
    } else {
        window.hide()
    };
}

#[derive(Default)]
pub struct Visibility {
    revision: AtomicU64,
    active: AtomicBool,
}

impl Visibility {
    fn update(&self, active: bool) -> u64 {
        self.active.store(active, Ordering::SeqCst);
        self.revision.fetch_add(1, Ordering::SeqCst) + 1
    }

    fn current(&self, revision: u64) -> bool {
        self.revision.load(Ordering::SeqCst) == revision
    }
}

fn hide(app: &AppHandle) {
    app.state::<Arc<State>>().guide.update(false);
    if let Some(window) = app.get_webview_window("guide") {
        set_visible(&window, false);
    }
    let _ = app.emit("guide:clear", ());
}

fn raise_pill(app: &AppHandle) {
    if let Some(pill) = app.get_webview_window("pill") {
        #[cfg(target_os = "linux")]
        {
            use gtk::prelude::WidgetExt;
            if let Ok(window) = pill.gtk_window() {
                if let Some(surface) = window.window() {
                    surface.raise();
                }
            }
        }
        #[cfg(not(target_os = "linux"))]
        let _ = pill.set_always_on_top(true);
    }
}

pub fn clear(app: &AppHandle) {
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || hide(&handle));
}

pub fn show(app: &AppHandle, event: &'static str, payload: Value, duration_ms: f64) {
    let Ok(duration) = Duration::try_from_secs_f64(duration_ms / 1000.) else {
        return;
    };
    let Some(expiry) = tokio::time::Instant::now().checked_add(duration) else {
        return;
    };
    let handle = app.clone();
    // Serialize visibility and expiry on the event loop, not WebKit's repaint timers.
    let _ = app.run_on_main_thread(move || {
        let revision = handle.state::<Arc<State>>().guide.update(true);
        if let Some(window) = handle.get_webview_window("guide") {
            set_visible(&window, true);
        }
        raise_pill(&handle);
        let _ = handle.emit_to("guide", event, payload);
        tauri::async_runtime::spawn(async move {
            tokio::time::sleep_until(expiry).await;
            let app = handle.clone();
            let _ = handle.run_on_main_thread(move || {
                if app.state::<Arc<State>>().guide.current(revision) {
                    hide(&app);
                }
            });
        });
    });
}

#[cfg(not(target_os = "macos"))]
pub fn restore(app: &AppHandle) {
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || {
        for label in ["guide", "pill"] {
            if label == "guide"
                && !handle
                    .state::<Arc<State>>()
                    .guide
                    .active
                    .load(Ordering::SeqCst)
            {
                continue;
            }
            if let Some(window) = handle.get_webview_window(label) {
                set_visible(&window, true);
            }
        }
        raise_pill(&handle);
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn old_expiry_cannot_clear_a_new_visual() {
        let visibility = Visibility::default();
        assert!(!visibility.active.load(Ordering::SeqCst));
        let old = visibility.update(true);
        let current = visibility.update(true);
        assert!(!visibility.current(old));
        assert!(visibility.current(current));
        visibility.update(false);
        assert!(!visibility.current(current));
        assert!(!visibility.active.load(Ordering::SeqCst));
    }
}
