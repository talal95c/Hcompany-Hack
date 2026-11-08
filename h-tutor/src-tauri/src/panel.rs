//! Turns Tauri windows into non-activating `NSPanel`s, like Spotlight or
//! Raycast. A normal window activates the app when shown, and macOS answers
//! by leaving the other app's full-screen Space. A non-activating panel
//! floats over full-screen apps and can take keyboard input without that.

#[cfg(not(target_os = "macos"))]
use tauri::WebviewWindow;

pub const LEVEL_BAR: isize = 25; // NSStatusWindowLevel
pub const LEVEL_OVERLAY: isize = 101; // NSPopUpMenuWindowLevel

#[cfg(target_os = "macos")]
mod imp {
    use objc2::{
        msg_send,
        runtime::{AnyClass, AnyObject, Bool, ClassBuilder, Sel},
        sel,
    };
    use std::ffi::CStr;
    use std::sync::OnceLock;
    use tauri::WebviewWindow;

    extern "C-unwind" fn yes(_this: &AnyObject, _cmd: Sel) -> Bool {
        Bool::YES
    }
    extern "C-unwind" fn no(_this: &AnyObject, _cmd: Sel) -> Bool {
        Bool::NO
    }

    /// NSPanel subclass; `can_key` decides whether it may take keyboard focus.
    fn panel_class(can_key: bool) -> &'static AnyClass {
        static KEY: OnceLock<&'static AnyClass> = OnceLock::new();
        static PASSIVE: OnceLock<&'static AnyClass> = OnceLock::new();
        let (cell, name): (_, &CStr) = if can_key { (&KEY, c"HoloKeyPanel") } else { (&PASSIVE, c"HoloPassivePanel") };
        cell.get_or_init(|| {
            let superclass = AnyClass::get(c"NSPanel").expect("NSPanel");
            let mut b = ClassBuilder::new(name, superclass).expect("unique class name");
            let f = if can_key { yes } else { no };
            // SAFETY: signatures match `- (BOOL)canBecomeKeyWindow` / `canBecomeMainWindow`.
            unsafe {
                b.add_method(sel!(canBecomeKeyWindow), f as extern "C-unwind" fn(_, _) -> _);
                b.add_method(sel!(canBecomeMainWindow), no as extern "C-unwind" fn(_, _) -> _);
            }
            b.register()
        })
    }

    fn with_ns(win: &WebviewWindow, f: impl FnOnce(&AnyObject) + Send + 'static) {
        let w = win.clone();
        let _ = win.run_on_main_thread(move || {
            if let Ok(ptr) = w.ns_window() {
                // SAFETY: Tauri hands out a valid NSWindow pointer, used on the main thread.
                f(unsafe { &*(ptr as *mut AnyObject) });
            }
        });
    }

    fn pin(ns: &AnyObject, level: isize) {
        // CanJoinAllSpaces | Stationary | IgnoresCycle | FullScreenAuxiliary
        let behavior: usize = (1 << 0) | (1 << 4) | (1 << 6) | (1 << 8);
        unsafe {
            let _: () = msg_send![ns, setCollectionBehavior: behavior];
            let _: () = msg_send![ns, setLevel: level];
        }
    }

    pub fn make_panel(win: &WebviewWindow, can_key: bool, level: isize) {
        let notch = win.label() == "main";
        with_ns(win, move |ns| unsafe {
            AnyObject::set_class(ns, panel_class(can_key));
            let mask: usize = msg_send![ns, styleMask];
            let _: () = msg_send![ns, setStyleMask: mask | (1 << 7)]; // NonactivatingPanel
            let _: () = msg_send![ns, setFloatingPanel: true];
            let _: () = msg_send![ns, setHidesOnDeactivate: false];
            pin(ns, level);
            if notch {
                let content: *mut AnyObject = msg_send![ns, contentView];
                if let Some(content) = content.as_ref() {
                    let _: () = msg_send![content, setWantsLayer: Bool::YES];
                    let layer: *mut AnyObject = msg_send![content, layer];
                    if let Some(layer) = layer.as_ref() {
                        let _: () = msg_send![layer, setCornerRadius: 20.0_f64];
                        let flipped: Bool = msg_send![layer, isGeometryFlipped];
                        let corners = if flipped.as_bool() { 10_usize } else { 5_usize };
                        let _: () = msg_send![layer, setMaskedCorners: corners];
                        let _: () = msg_send![layer, setMasksToBounds: Bool::YES];
                    }
                }
            }
        });
    }

    /// Shows the panel on the current Space without activating the app.
    pub fn show(win: &WebviewWindow, key: bool, level: isize) {
        with_ns(win, move |ns| unsafe {
            pin(ns, level);
            let _: () = msg_send![ns, orderFrontRegardless];
            if key {
                let _: () = msg_send![ns, makeKeyWindow];
            }
        });
    }
}

#[cfg(target_os = "macos")]
pub use imp::{make_panel, show};

#[cfg(not(target_os = "macos"))]
pub fn make_panel(_win: &WebviewWindow, _can_key: bool, _level: isize) {}

#[cfg(not(target_os = "macos"))]
pub fn show(win: &WebviewWindow, key: bool, _level: isize) {
    let _ = win.show();
    if key {
        let _ = win.set_focus();
    }
}
