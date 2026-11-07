//! Watches real mouse clicks so a step is validated by what the user actually
//! did, not by guessing from screenshots.
//!
//! macOS: a listen-only CGEventTap receives every mouse-down as an event, even
//! a trackpad tap shorter than any polling interval. If the tap cannot be
//! created (permission), it falls back to polling the button state.

#[derive(Clone, Copy, Debug)]
pub struct Click {
    /// Global logical coordinates (points), origin at the top-left of the main display.
    pub x: f64,
    pub y: f64,
}

#[cfg(target_os = "macos")]
mod imp {
    use super::Click;
    use std::ffi::c_void;
    use std::sync::atomic::{AtomicPtr, Ordering};
    use std::sync::OnceLock;

    #[repr(C)]
    #[derive(Clone, Copy)]
    struct CGPoint {
        x: f64,
        y: f64,
    }

    type Callback = extern "C" fn(*mut c_void, u32, *mut c_void, *mut c_void) -> *mut c_void;

    const SESSION_TAP: u32 = 1; // kCGSessionEventTap
    const HEAD_INSERT: u32 = 0; // kCGHeadInsertEventTap
    const LISTEN_ONLY: u32 = 1; // kCGEventTapOptionListenOnly
    const LEFT_DOWN: u32 = 1; // kCGEventLeftMouseDown
    const RIGHT_DOWN: u32 = 3; // kCGEventRightMouseDown
    const SOURCE_USER_DATA: u32 = 42;
    const TAP_DISABLED_BY_TIMEOUT: u32 = 0xFFFF_FFFE;
    const TAP_DISABLED_BY_USER: u32 = 0xFFFF_FFFF;

    #[link(name = "CoreGraphics", kind = "framework")]
    unsafe extern "C" {
        fn CGEventTapCreate(
            tap: u32,
            place: u32,
            options: u32,
            events_of_interest: u64,
            callback: Callback,
            user_info: *mut c_void,
        ) -> *mut c_void;
        fn CGEventTapEnable(tap: *mut c_void, enable: bool);
        fn CGEventGetLocation(event: *const c_void) -> CGPoint;
        fn CGEventGetIntegerValueField(event: *const c_void, field: u32) -> i64;
        fn CGEventSourceButtonState(state: i32, button: u32) -> bool;
        fn CGEventCreate(source: *const c_void) -> *mut c_void;
    }

    #[link(name = "CoreFoundation", kind = "framework")]
    unsafe extern "C" {
        static kCFRunLoopCommonModes: *const c_void;
        fn CFMachPortCreateRunLoopSource(alloc: *const c_void, port: *mut c_void, order: isize) -> *mut c_void;
        fn CFRunLoopGetCurrent() -> *mut c_void;
        fn CFRunLoopAddSource(rl: *mut c_void, source: *mut c_void, mode: *const c_void);
        fn CFRunLoopRun();
        fn CFRelease(cf: *const c_void);
    }

    static HANDLER: OnceLock<Box<dyn Fn(Click) + Send + Sync>> = OnceLock::new();
    static TAP: AtomicPtr<c_void> = AtomicPtr::new(std::ptr::null_mut());

    extern "C" fn on_event(_proxy: *mut c_void, kind: u32, event: *mut c_void, _user: *mut c_void) -> *mut c_void {
        match kind {
            // macOS disables slow taps; turn it back on.
            TAP_DISABLED_BY_TIMEOUT | TAP_DISABLED_BY_USER => unsafe {
                let tap = TAP.load(Ordering::SeqCst);
                if !tap.is_null() {
                    CGEventTapEnable(tap, true);
                }
            },
            LEFT_DOWN | RIGHT_DOWN => {
                if unsafe { CGEventGetIntegerValueField(event, SOURCE_USER_DATA) } == crate::act::RIO_EVENT_TAG {
                    return event;
                }
                let p = unsafe { CGEventGetLocation(event) };
                if let Some(h) = HANDLER.get() {
                    h(Click { x: p.x, y: p.y });
                }
            }
            _ => {}
        }
        event
    }

    /// Returns true when the event tap is running.
    fn start_tap() -> bool {
        let (ready_tx, ready_rx) = std::sync::mpsc::channel();
        std::thread::Builder::new()
            .name("click-tap".into())
            .spawn(move || unsafe {
                let mask = (1u64 << LEFT_DOWN) | (1u64 << RIGHT_DOWN);
                let tap = CGEventTapCreate(SESSION_TAP, HEAD_INSERT, LISTEN_ONLY, mask, on_event, std::ptr::null_mut());
                if tap.is_null() {
                    let _ = ready_tx.send(false);
                    return;
                }
                TAP.store(tap, Ordering::SeqCst);
                let source = CFMachPortCreateRunLoopSource(std::ptr::null(), tap, 0);
                CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes);
                CGEventTapEnable(tap, true);
                let _ = ready_tx.send(true);
                CFRunLoopRun();
            })
            .ok();
        ready_rx.recv().unwrap_or(false)
    }

    /// Fallback: polls the left button (misses very short trackpad taps).
    fn start_polling() {
        std::thread::spawn(|| {
            let mut was_down = false;
            loop {
                let down = unsafe { CGEventSourceButtonState(0, 0) };
                if down && !was_down {
                    unsafe {
                        let ev = CGEventCreate(std::ptr::null());
                        if !ev.is_null() {
                            let p = CGEventGetLocation(ev);
                            CFRelease(ev);
                            if let Some(h) = HANDLER.get() {
                                h(Click { x: p.x, y: p.y });
                            }
                        }
                    }
                }
                was_down = down;
                std::thread::sleep(std::time::Duration::from_millis(8));
            }
        });
    }

    pub fn watch(on_click: impl Fn(Click) + Send + Sync + 'static) {
        if HANDLER.set(Box::new(on_click)).is_err() {
            return;
        }
        if start_tap() {
            eprintln!("[clicks] event tap active");
        } else {
            eprintln!("[clicks] event tap unavailable, polling the mouse button");
            start_polling();
        }
    }
}

#[cfg(not(target_os = "macos"))]
mod imp {
    use super::Click;
    pub fn watch(_on_click: impl Fn(Click) + Send + Sync + 'static) {}
}

pub use imp::watch;
