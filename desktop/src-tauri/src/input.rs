use std::{
    sync::atomic::Ordering,
    time::{Duration, Instant},
};

use enigo::{Button, Coordinate, Direction, Enigo, Key, Keyboard, Mouse, Settings};
use serde::Deserialize;
use serde_json::Value;

use crate::{native, State};

pub struct Consent {
    pub token: String,
    pub until: Instant,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    Move { x: f64, y: f64 },
    Click { x: f64, y: f64, button: String },
    Key { key: String },
    Text { text: String },
    Scroll { amount: i32 },
}

pub fn grant(state: &State) -> String {
    let token = uuid::Uuid::new_v4().to_string();
    state.stopped.store(false, Ordering::SeqCst);
    *state.consent.lock().unwrap() = Some(Consent {
        token: token.clone(),
        until: Instant::now() + Duration::from_secs(60),
    });
    token
}

pub fn stop(state: &State) {
    state.stopped.store(true, Ordering::SeqCst);
    *state.consent.lock().unwrap() = None;
    state.captures.lock().unwrap().clear();
    state.audio.stop();
}

pub fn perform(state: &State, payload: &Value) -> Result<(), String> {
    let _guard = guard(state, payload["consent_token"].as_str().unwrap_or(""))?;
    if !native::permissions().accessibility || !native::blender_focused() {
        stop(state);
        return Err("Blender must have focus and Accessibility permission".into());
    }
    let id = payload["capture_id"].as_str().ok_or("missing capture")?;
    let capture = state
        .captures
        .lock()
        .unwrap()
        .remove(id)
        .ok_or("fresh capture required for every action")?;
    if capture.at.elapsed() > Duration::from_secs(10) {
        return Err("capture expired".into());
    }
    let action: Action =
        serde_json::from_value(payload["action"].clone()).map_err(|e| e.to_string())?;
    let mut enigo = Enigo::new(&Settings::default()).map_err(|e| e.to_string())?;
    _guard.check()?;
    let mut move_to = |x, y| -> Result<(), String> {
        let (lx, ly) = capture.monitor.point(capture.crop, x, y)?;
        enigo
            .move_mouse(lx.round() as i32, ly.round() as i32, Coordinate::Abs)
            .map_err(|e| e.to_string())
    };
    match action {
        Action::Move { x, y } => move_to(x, y)?,
        Action::Click { x, y, button } => {
            let button = match button.as_str() {
                "left" => Button::Left,
                "right" => Button::Right,
                "middle" => Button::Middle,
                _ => return Err("unsupported button".into()),
            };
            move_to(x, y)?;
            _guard.check()?;
            if state.stopped.load(Ordering::SeqCst) || !native::blender_focused() {
                return Err("stopped or focus lost".into());
            }
            enigo
                .button(button, Direction::Click)
                .map_err(|e| e.to_string())?;
        }
        Action::Key { key } => {
            let key = allowed_key(&key)?;
            enigo
                .key(key, Direction::Click)
                .map_err(|e| e.to_string())?;
        }
        Action::Text { text } => {
            if text.is_empty()
                || text.len() > 128
                || !text
                    .chars()
                    .all(|c| c.is_alphanumeric() || " _-.".contains(c))
            {
                return Err("text must be a simple Blender label, not code or a secret".into());
            }
            enigo.text(&text).map_err(|e| e.to_string())?;
        }
        Action::Scroll { amount } => {
            if !(-10..=10).contains(&amount) {
                return Err("scroll out of bounds".into());
            }
            enigo
                .scroll(amount, enigo::Axis::Vertical)
                .map_err(|e| e.to_string())?;
        }
    }
    // No held-key API is exposed; enigo also releases tracked keys on drop.
    Ok(())
}

pub struct ActionGuard<'a> {
    consent: &'a std::sync::Mutex<Option<Consent>>,
    stopped: &'a std::sync::atomic::AtomicBool,
    connected: &'a std::sync::atomic::AtomicBool,
    token: &'a str,
    _lock: tokio::sync::MutexGuard<'a, ()>,
}

impl ActionGuard<'_> {
    pub fn check(&self) -> Result<(), String> {
        check_consent(
            self.consent.lock().unwrap().as_ref(),
            self.token,
            self.stopped.load(Ordering::SeqCst),
            self.connected.load(Ordering::SeqCst),
            Instant::now(),
        )
    }
}

fn check_consent(
    consent: Option<&Consent>,
    token: &str,
    stopped: bool,
    connected: bool,
    now: Instant,
) -> Result<(), String> {
    if stopped || !connected || !consent.is_some_and(|c| c.token == token && now < c.until) {
        Err("consent missing, stopped or expired".into())
    } else {
        Ok(())
    }
}

pub fn guard<'a>(state: &'a State, token: &'a str) -> Result<ActionGuard<'a>, String> {
    guard_parts(
        &state.consent,
        &state.stopped,
        &state.connected,
        &state.input_lock,
        token,
    )
}

pub fn guard_parts<'a>(
    consent: &'a std::sync::Mutex<Option<Consent>>,
    stopped: &'a std::sync::atomic::AtomicBool,
    connected: &'a std::sync::atomic::AtomicBool,
    lock: &'a tokio::sync::Mutex<()>,
    token: &'a str,
) -> Result<ActionGuard<'a>, String> {
    let guard = ActionGuard {
        consent,
        stopped,
        connected,
        token,
        _lock: lock.try_lock().map_err(|_| "desktop busy")?,
    };
    guard.check()?;
    Ok(guard)
}

fn allowed_key(key: &str) -> Result<Key, String> {
    Ok(match key {
        "tab" => Key::Tab,
        "enter" => Key::Return,
        "escape" => Key::Escape,
        "space" => Key::Space,
        "up" => Key::UpArrow,
        "down" => Key::DownArrow,
        "left" => Key::LeftArrow,
        "right" => Key::RightArrow,
        value if value.len() == 1 && value.chars().all(|c| c.is_ascii_alphanumeric()) => {
            Key::Unicode(value.chars().next().unwrap())
        }
        _ => return Err("system/modifier shortcuts are not permitted".into()),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn action_guards_reject_missing_expired_stopped_and_busy() {
        let now = Instant::now();
        let consent = Consent {
            token: "token".into(),
            until: now + Duration::from_secs(1),
        };
        assert!(check_consent(None, "token", false, true, now).is_err());
        assert!(check_consent(Some(&consent), "wrong", false, true, now).is_err());
        assert!(check_consent(
            Some(&consent),
            "token",
            false,
            true,
            now + Duration::from_secs(2)
        )
        .is_err());
        assert!(check_consent(Some(&consent), "token", true, true, now).is_err());
        assert!(check_consent(Some(&consent), "token", false, false, now).is_err());
        assert!(check_consent(Some(&consent), "token", false, true, now).is_ok());
        let lock = tokio::sync::Mutex::new(());
        let _held = lock.try_lock().unwrap();
        assert!(lock.try_lock().is_err());
    }
    #[test]
    fn rejects_system_shortcuts_and_unknown_actions() {
        for value in ["cmd", "ctrl", "alt", "delete", "F12", ""] {
            assert!(allowed_key(value).is_err());
        }
        assert!(allowed_key("tab").is_ok());
        assert!(serde_json::from_value::<Action>(
            serde_json::json!({"type":"shell","command":"whoami"})
        )
        .is_err());
        assert!(serde_json::from_value::<Action>(
            serde_json::json!({"type":"key","key":"a","extra":1})
        )
        .is_err());
    }
}
