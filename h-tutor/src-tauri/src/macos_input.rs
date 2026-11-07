use crate::{act, autopilot, tutorial::App};
use objc2::rc::autoreleasepool;
use objc2::runtime::AnyObject;
use objc2::{class, msg_send};
use std::ffi::{CStr, c_char};
use std::time::Duration;
use std::sync::atomic::{AtomicUsize, Ordering};
use tauri::AppHandle;

static ACTIVE: AtomicUsize = AtomicUsize::new(0);

struct MainAction;

impl Drop for MainAction {
    fn drop(&mut self) {
        ACTIVE.fetch_sub(1, Ordering::SeqCst);
    }
}

pub(crate) fn is_idle() -> bool {
    ACTIVE.load(Ordering::SeqCst) == 0
}

pub(crate) fn on_main<T: Send + 'static>(
    app: &AppHandle,
    ticket: u64,
    action: impl FnOnce() -> Result<T, String> + Send + 'static,
) -> Result<T, String> {
    let (send, receive) = std::sync::mpsc::sync_channel(1);
    let started = std::time::Instant::now();
    app.run_on_main_thread(move || {
        ACTIVE.fetch_add(1, Ordering::SeqCst);
        let _active = MainAction;
        let result = act::check(ticket).and_then(|_| action());
        let _ = send.send(result);
    })
    .map_err(|e| e.to_string())?;
    loop {
        act::check(ticket)?;
        match receive.recv_timeout(Duration::from_millis(20)) {
            Ok(result) => return result,
            Err(std::sync::mpsc::RecvTimeoutError::Disconnected) => {
                return Err("Injection : thread principal déconnecté".into());
            }
            Err(std::sync::mpsc::RecvTimeoutError::Timeout) => {}
        }
        if autopilot::stop_requested() {
            return Err("Arrêt demandé".into());
        }
        if started.elapsed() >= Duration::from_secs(2) {
            autopilot::request_stop();
            return Err("Injection : le thread principal ne répond pas".into());
        }
    }
}

unsafe fn string(value: *mut AnyObject) -> Option<String> {
    if value.is_null() {
        return None;
    }
    let utf8: *const c_char = unsafe { msg_send![value, UTF8String] };
    (!utf8.is_null()).then(|| unsafe { CStr::from_ptr(utf8).to_string_lossy().into_owned() })
}

unsafe fn identity(running: *mut AnyObject) -> App {
    let name = unsafe { msg_send![running, localizedName] };
    let bundle = unsafe { msg_send![running, bundleIdentifier] };
    App {
        name: unsafe { string(name) }.unwrap_or_default(),
        bundle_id: unsafe { string(bundle) },
        ..Default::default()
    }
}

pub(crate) fn verify(target: &App, own_bundle: &str, log: bool) -> Result<(), String> {
    autoreleasepool(|_| unsafe {
        let workspace: *mut AnyObject = msg_send![class!(NSWorkspace), sharedWorkspace];
        let running: *mut AnyObject = msg_send![workspace, frontmostApplication];
        if running.is_null() {
            return Err("Application au premier plan introuvable".into());
        }
        let foreground = identity(running);
        let pid: i32 = msg_send![running, processIdentifier];
        if log {
            eprintln!("[Rio] press_key frontmost pid={pid} bundle={:?} name={:?} target_bundle={:?}", foreground.bundle_id, foreground.name, target.bundle_id);
            crate::journal::event("rio_keyboard_focus", serde_json::json!({
                "pid": pid, "app": foreground, "target": target,
            }));
        }
        if !accepts_target(target, &foreground, pid as u32, std::process::id(), own_bundle) {
            return Err("Injection refusée : l'application cible n'est pas au premier plan".into());
        }
        Ok(())
    })
}

fn accepts_target(target: &App, foreground: &App, pid: u32, own_pid: u32, own_bundle: &str) -> bool {
    pid != own_pid
        && foreground.bundle_id.as_deref() != Some(own_bundle)
        && crate::skills::matches_app(target, foreground)
}

pub(crate) fn prepare(app: &AppHandle, target: &App, ticket: u64, log: bool) -> Result<(), String> {
    let activation_target = target.clone();
    let own_bundle = app.config().identifier.clone();
    on_main(app, ticket, move || {
        let target = activation_target;
        if verify(&target, &own_bundle, false).is_ok() {
            return Ok(());
        }
        autoreleasepool(|_| unsafe {
            let workspace: *mut AnyObject = msg_send![class!(NSWorkspace), sharedWorkspace];
            let apps: *mut AnyObject = msg_send![workspace, runningApplications];
            let count: usize = msg_send![apps, count];
            for index in 0..count {
                let running: *mut AnyObject = msg_send![apps, objectAtIndex: index];
                let identity = identity(running);
                let pid: i32 = msg_send![running, processIdentifier];
                if pid as u32 != std::process::id()
                    && identity.bundle_id.as_deref() != Some(own_bundle.as_str())
                    && crate::skills::matches_app(&target, &identity)
                {
                    let activated: bool = msg_send![running, activateWithOptions: 2usize];
                    return if activated { Ok(()) } else { Err("Activation de l'application cible refusée".into()) };
                }
            }
            Err("Application cible introuvable".into())
        })
    })?;
    for _ in 0..20 {
        let verification_target = target.clone();
        let own_bundle = app.config().identifier.clone();
        if on_main(app, ticket, move || verify(&verification_target, &own_bundle, false)).is_ok() {
            if log {
                let target = target.clone();
                let own_bundle = app.config().identifier.clone();
                on_main(app, ticket, move || verify(&target, &own_bundle, true))?;
            }
            return Ok(());
        }
        std::thread::sleep(Duration::from_millis(25));
    }
    Err("L'application cible n'a pas pris le premier plan".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn injection_requires_target_and_excludes_own_process_and_bundle() {
        let finder = App {
            name: "Finder".into(),
            bundle_id: Some("com.apple.finder".into()),
            ..Default::default()
        };
        assert!(accepts_target(&finder, &finder, 10, 20, "com.htutor.app"));
        assert!(!accepts_target(&finder, &finder, 20, 20, "com.htutor.app"));
        assert!(!accepts_target(&finder, &finder, 10, 20, "com.apple.finder"));
        assert!(!accepts_target(&finder, &App::default(), 10, 20, "com.htutor.app"));
        assert!(!accepts_target(&App::default(), &App::default(), 10, 20, "com.htutor.app"));
    }
}
