use crate::{agent::Step, autopilot};
use enigo::{Axis, Button, Coordinate, Direction, Enigo, Key, Keyboard, Mouse, Settings};
use tauri::AppHandle;

static INPUT_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
pub(crate) const RIO_EVENT_TAG: i64 = 0x52494f;

pub async fn drain() -> bool {
    let pending = tauri::async_runtime::spawn_blocking(|| {
        let _guard = INPUT_LOCK.lock();
        #[cfg(target_os = "macos")]
        while !crate::macos_input::is_idle() {
            std::thread::sleep(std::time::Duration::from_millis(20));
        }
    });
    #[cfg(target_os = "macos")]
    return tokio::time::timeout(std::time::Duration::from_secs(2), pending).await.is_ok();
    #[cfg(not(target_os = "macos"))]
    pending.await.is_ok()
}

pub fn screen_point(
    nx: f64,
    ny: f64,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
) -> Result<(f64, f64), String> {
    if !nx.is_finite()
        || !ny.is_finite()
        || !(0.0..=1000.0).contains(&nx)
        || !(0.0..=1000.0).contains(&ny)
    {
        return Err("Point Holo hors écran".into());
    }
    Ok((x + nx / 1000.0 * width, y + ny / 1000.0 * height))
}

pub(crate) fn check(ticket: u64) -> Result<(), String> {
    authorization(autopilot::stop_requested(), ticket, autopilot::run_id())
}

fn authorization(stopped: bool, ticket: u64, current: u64) -> Result<(), String> {
    if stopped || ticket != current {
        Err("Arrêt demandé".into())
    } else {
        Ok(())
    }
}

fn key(value: &str) -> Result<Key, String> {
    Ok(match value.to_lowercase().as_str() {
        "ctrl" | "control" => Key::Control,
        "cmd" | "command" | "meta" | "super" => Key::Meta,
        "alt" | "option" => Key::Alt,
        "shift" => Key::Shift,
        "enter" | "return" => Key::Return,
        "tab" => Key::Tab,
        "escape" | "esc" => Key::Escape,
        "space" => Key::Space,
        "backspace" => Key::Backspace,
        "up" => Key::UpArrow,
        "down" => Key::DownArrow,
        "left" => Key::LeftArrow,
        "right" => Key::RightArrow,
        "home" => Key::Home,
        "end" => Key::End,
        "pageup" | "page_up" => Key::PageUp,
        "pagedown" | "page_down" => Key::PageDown,
        s if s.chars().count() == 1 && s.chars().all(|c| c.is_ascii_alphanumeric()) => {
            Key::Unicode(s.chars().next().ok_or("Touche vide")?)
        }
        _ => return Err(format!("Touche non autorisée : {value}")),
    })
}

pub fn perform(app: &AppHandle, step: &Step, ticket: u64, target: &crate::tutorial::App) -> Result<(), String> {
    #[cfg(not(target_os = "macos"))]
    let _ = target;
    let _lock = INPUT_LOCK
        .lock()
        .map_err(|_| "Verrou d'injection indisponible")?;
    check(ticket)?;
    #[cfg(target_os = "macos")]
    if step.kind == "press_key" {
        return keyboard_on_main(app, target, ticket, None, shortcut_keys(&step.keys)?);
    }
    #[cfg(target_os = "linux")]
    if std::env::var("XDG_SESSION_TYPE").is_ok_and(|v| v == "wayland")
        || std::env::var("DISPLAY").is_err()
    {
        return Err("L'exécution nécessite une session Linux X11".into());
    }
    let settings = Settings {
        event_source_user_data: Some(RIO_EVENT_TAG),
        open_prompt_to_get_permissions: false,
        ..Default::default()
    };
    let mut device = Enigo::new(&settings).map_err(|e| {
        format!("Injection indisponible ; vérifiez l'autorisation Accessibilité : {e}")
    })?;
    check(ticket)?;
    if matches!(step.kind.as_str(), "click" | "write" | "scroll") {
        let (nx, ny) = step.point.ok_or("L'action Holo ne contient pas de point")?;
        let (x, y) = crate::normalized_screen_point(app, nx, ny)?;
        #[cfg(target_os = "macos")]
        let (x, y) = {
            let scale = app
                .primary_monitor()
                .map_err(|e| e.to_string())?
                .ok_or("Écran introuvable")?
                .scale_factor();
            (x / scale, y / scale)
        };
        device
            .move_mouse(x.round() as i32, y.round() as i32, Coordinate::Abs)
            .map_err(|e| e.to_string())?;
        check(ticket)?;
    }
    match step.kind.as_str() {
        "click" => device
            .button(Button::Left, Direction::Click)
            .map_err(|e| e.to_string())?,
        "write" => {
            if step.text.is_empty()
                || step.text.chars().count() > 512
                || step.text.contains(['\n', '\r', '\0'])
            {
                return Err("Texte vide, trop long ou multiligne refusé".into());
            }
            device
                .button(Button::Left, Direction::Click)
                .map_err(|e| e.to_string())?;
            for character in step.text.chars() {
                check(ticket)?;
                #[cfg(target_os = "macos")]
                keyboard_on_main(app, target, ticket, Some(character.to_string()), Vec::new())?;
                #[cfg(not(target_os = "macos"))]
                device
                    .text(&character.to_string())
                    .map_err(|e| e.to_string())?;
            }
        }
        "scroll" => {
            let (amount, axis) = match step.direction.as_str() {
                "up" => (-3, Axis::Vertical),
                "down" => (3, Axis::Vertical),
                "left" => (-3, Axis::Horizontal),
                "right" => (3, Axis::Horizontal),
                _ => return Err("Direction de défilement invalide".into()),
            };
            device.scroll(amount, axis).map_err(|e| e.to_string())?;
        }
        "press_key" => {
            let keys = shortcut_keys(&step.keys)?;
            #[cfg(target_os = "macos")]
            keyboard_on_main(app, target, ticket, None, keys)?;
            #[cfg(not(target_os = "macos"))]
            {
                for key in &keys {
                    check(ticket)?;
                    device
                        .key(*key, Direction::Press)
                        .map_err(|e| e.to_string())?;
                }
                for key in keys.iter().rev() {
                    device
                        .key(*key, Direction::Release)
                        .map_err(|e| e.to_string())?;
                }
            }
        }
        _ => return Err("Action Holo non prise en charge".into()),
    }
    check(ticket)
}

fn shortcut_keys(value: &str) -> Result<Vec<Key>, String> {
    let keys = value.split('+').map(|s| key(s.trim())).collect::<Result<Vec<_>, _>>()?;
    if keys.is_empty() || keys.len() > 4 {
        return Err("Raccourci invalide".into());
    }
    Ok(keys)
}

#[cfg(target_os = "macos")]
fn keyboard_on_main(
    app: &AppHandle,
    target: &crate::tutorial::App,
    ticket: u64,
    text: Option<String>,
    keys: Vec<Key>,
) -> Result<(), String> {
    let target = target.clone();
    let own_bundle = app.config().identifier.clone();
    crate::macos_input::on_main(app, ticket, move || {
        crate::macos_input::verify(&target, &own_bundle, text.is_none())?;
        let mut device = Enigo::new(&Settings {
            event_source_user_data: Some(RIO_EVENT_TAG),
            open_prompt_to_get_permissions: false,
            ..Default::default()
        }).map_err(|e| format!("Injection indisponible ; vérifiez l'autorisation Accessibilité : {e}"))?;
        if let Some(text) = text {
            check(ticket)?;
            return device.text(&text).map_err(|e| e.to_string());
        }
        for key in &keys {
            check(ticket)?;
            device.key(*key, Direction::Press).map_err(|e| e.to_string())?;
        }
        for key in keys.iter().rev() {
            device.key(*key, Direction::Release).map_err(|e| e.to_string())?;
        }
        check(ticket)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn autopilot_coordinates_and_keys_are_bounded() {
        assert_eq!(
            screen_point(500.0, 250.0, -1920.0, 120.0, 1920.0, 1080.0).unwrap(),
            (-960.0, 390.0)
        );
        assert!(screen_point(f64::NAN, 0.0, 0.0, 0.0, 100.0, 100.0).is_err());
        assert!(screen_point(1001.0, 0.0, 0.0, 0.0, 100.0, 100.0).is_err());
        assert!(key("ctrl").is_ok());
        assert!(key("enter").is_ok());
        assert!(key("").is_err());
        assert!(key("delete").is_err());
        assert_eq!(shortcut_keys("shift+cmd+n").unwrap(), vec![Key::Shift, Key::Meta, Key::Unicode('n')]);
        assert!(shortcut_keys("").is_err());
        assert!(shortcut_keys("cmd+unknown").is_err());
        assert!(shortcut_keys("cmd+shift+alt+ctrl+n").is_err());
    }

    #[test]
    fn autopilot_stale_or_stopped_actions_are_rejected() {
        assert!(authorization(false, 5, 5).is_ok());
        assert!(authorization(true, 5, 5).is_err());
        assert!(authorization(false, 5, 6).is_err());
    }
}
