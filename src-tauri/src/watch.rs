//! Decides when to look again. Instead of trusting a click on the target
//! (hover menus, keyboard shortcuts and typing never click it), the screen is
//! watched locally: when it changes and then settles, the bar is told to send
//! the new screenshot to Holo, which judges what happened.
//!
//! Readiness depends on the action. A pointer step fires once the screen has
//! settled, or when the target was clicked without visible effect. A typing
//! step never fires on the click that focuses the field: it waits for the
//! keyboard to go quiet (or Enter), so a sentence is not cut mid-word. A
//! shortcut step also fires when keys were pressed without visible effect.
//! Keys are only counted (never recorded), and only when macOS already grants
//! the listen permission; without it, typing falls back to screen changes.

use crate::capture::{SCREEN_CHANGED as CHANGED, capture_thumb, thumb_diff};
use image::GrayImage;
use serde::Serialize;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter};

/// Two frames closer than this are "stable".
const STABLE: f32 = 0.35;
const TICK: Duration = Duration::from_millis(350);
/// A click on the target, or a shortcut, with no visible effect is reported after this.
const HIT_GRACE: Duration = Duration::from_millis(1500);
/// Screen settle time once it changed (est.).
const SETTLE: Duration = Duration::from_millis(400);
/// Typing without keyboard events: settle longer so a sentence is not cut (est.).
const TYPING_SETTLE: Duration = Duration::from_millis(1200);
/// Typing is over after this much keyboard silence (est.).
const TYPING_IDLE: Duration = Duration::from_millis(2000);

/// What kind of learner action the watcher waits for.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub enum Mode {
    /// click, scroll
    #[default]
    Pointer,
    /// write
    Typing,
    /// press_key
    Keys,
}

impl Mode {
    /// The mode for a step kind, or None when there is nothing to watch.
    pub fn for_kind(kind: &str) -> Option<Self> {
        match kind {
            "click" | "scroll" => Some(Self::Pointer),
            "write" => Some(Self::Typing),
            "press_key" => Some(Self::Keys),
            _ => None,
        }
    }
}

#[derive(Default)]
struct Watch {
    active: bool,
    mode: Mode,
    /// Screen Holo last saw.
    baseline: Option<GrayImage>,
    last: Option<GrayImage>,
    stable_since: Option<Instant>,
    hits: u32,
    misses: u32,
    /// Clicks while nothing was pointed at (shortcut or typing steps).
    clicks: u32,
    last_hit: Option<Instant>,
    keys: u32,
    enter: bool,
    last_key: Option<Instant>,
}

static WATCH: Mutex<Option<Watch>> = Mutex::new(None);

#[derive(Serialize, Clone)]
struct Changed {
    /// What we know about the learner's action, for Holo.
    event: String,
}

/// Starts watching for the learner's action on a new step. `baseline` is
/// the screen Holo based the step on.
pub fn arm(baseline: GrayImage, mode: Mode) {
    *WATCH.lock().unwrap() = Some(Watch { active: true, mode, baseline: Some(baseline), ..Default::default() });
}

pub fn disarm() {
    if let Some(w) = WATCH.lock().unwrap().as_mut() {
        w.active = false;
    }
}

/// Counts a real click during the current step: on the target, beside it,
/// or (`None`) while nothing is pointed at.
pub fn note_click(hit: Option<bool>) {
    if let Some(w) = WATCH.lock().unwrap().as_mut().filter(|w| w.active) {
        w.note_click(hit, Instant::now());
    }
}

/// Counts a key press during the current step (which key is not kept,
/// only whether it was Enter).
pub fn note_key(enter: bool) {
    if let Some(w) = WATCH.lock().unwrap().as_mut().filter(|w| w.active) {
        w.note_key(enter, Instant::now());
    }
}

impl Watch {
    fn note_click(&mut self, hit: Option<bool>, at: Instant) {
        match hit {
            Some(true) => {
                self.hits += 1;
                self.last_hit = Some(at);
            }
            Some(false) => self.misses += 1,
            None => self.clicks += 1,
        }
    }

    fn note_key(&mut self, enter: bool, at: Instant) {
        self.keys += 1;
        self.enter |= enter;
        self.last_key = Some(at);
    }

    /// Takes one frame. Returns the event for Holo when the learner's action
    /// looks finished, and disarms.
    fn tick(&mut self, now: GrayImage, at: Instant) -> Option<String> {
        let changed = self.baseline.as_ref().is_some_and(|b| thumb_diff(b, &now) > CHANGED);
        let stable = self.last.as_ref().is_some_and(|l| thumb_diff(l, &now) < STABLE);
        self.stable_since = if stable { self.stable_since.or(Some(at)) } else { None };
        self.last = Some(now);

        let stable_for = |d: Duration| self.stable_since.is_some_and(|t| at.duration_since(t) >= d);
        let quiet_for = |last: Option<Instant>, d: Duration| last.is_some_and(|t| at.duration_since(t) >= d);
        let ready = match self.mode {
            Mode::Pointer => (changed && stable_for(SETTLE)) || (!changed && quiet_for(self.last_hit, HIT_GRACE)),
            // Keyboard seen: done when it goes quiet (Enter shortens the wait)
            // and the screen has settled. Never on the focusing click alone.
            Mode::Typing if self.keys > 0 => {
                let idle = if self.enter { SETTLE } else { TYPING_IDLE };
                quiet_for(self.last_key, idle) && stable_for(SETTLE)
            }
            Mode::Typing => changed && stable_for(TYPING_SETTLE),
            Mode::Keys => (changed && stable_for(SETTLE)) || (!changed && quiet_for(self.last_key, HIT_GRACE)),
        };
        if !ready {
            return None;
        }
        self.active = false;
        Some(self.describe(changed))
    }

    fn describe(&self, changed: bool) -> String {
        describe_event(self.hits, self.misses, self.clicks, self.keys, self.enter, changed)
    }
}

/// What the watcher tells Holo about the learner's action. Shared with the
/// learner simulator so both speak exactly like the real watcher.
pub fn describe_event(hits: u32, misses: u32, clicks: u32, keys: u32, enter: bool, changed: bool) -> String {
    let mut what = if hits > 0 {
        "The learner clicked the highlighted element".to_string()
    } else if misses > 0 {
        "The learner clicked somewhere other than the highlighted element".to_string()
    } else if clicks > 0 {
        // Nothing was highlighted: not a miss.
        "The learner clicked on the screen".to_string()
    } else if keys > 0 {
        "The learner did not click".to_string()
    } else {
        "The learner did not click (hover, keyboard or scroll)".to_string()
    };
    if keys > 0 {
        what += if enter { ", used the keyboard and pressed Enter" } else { ", used the keyboard" };
    }
    if changed {
        format!("{what}, and the screen changed. Check the new screenshot to see whether the action was done.")
    } else {
        format!("{what}, but nothing visibly changed on screen.")
    }
}

pub fn spawn(app: AppHandle) {
    std::thread::Builder::new()
        .name("screen-watch".into())
        .spawn(move || {
            loop {
                std::thread::sleep(TICK);
                let armed = WATCH.lock().unwrap().as_ref().is_some_and(|w| w.active);
                if !armed {
                    continue;
                }
                let Ok(now) = capture_thumb() else { continue };

                let mut guard = WATCH.lock().unwrap();
                let Some(w) = guard.as_mut().filter(|w| w.active) else { continue };
                if let Some(event) = w.tick(now, Instant::now()) {
                    drop(guard);
                    app.emit_to("main", "watch:changed", Changed { event }).ok();
                }
            }
        })
        .expect("spawn screen watcher");
}

#[cfg(test)]
mod tests {
    use super::*;

    fn frame(v: u8) -> GrayImage {
        GrayImage::from_pixel(96, 54, image::Luma([v]))
    }

    /// Feeds `frames` (value, ms since start) and returns the first event.
    fn run(w: &mut Watch, t0: Instant, frames: &[(u8, u64)]) -> Option<(u64, String)> {
        frames.iter().find_map(|&(v, ms)| w.tick(frame(v), t0 + Duration::from_millis(ms)).map(|e| (ms, e)))
    }

    fn armed(mode: Mode) -> Watch {
        Watch { active: true, mode, baseline: Some(frame(100)), ..Default::default() }
    }

    #[test]
    fn pointer_fires_once_the_screen_settles() {
        let t0 = Instant::now();
        let mut w = armed(Mode::Pointer);
        let (ms, e) = run(&mut w, t0, &[(100, 0), (140, 350), (140, 700), (140, 1050), (140, 1400)]).unwrap();
        assert_eq!(ms, 1400);
        assert!(e.contains("screen changed"));
        assert!(!w.active);
    }

    #[test]
    fn clicking_a_field_does_not_end_typing() {
        let t0 = Instant::now();
        let mut w = armed(Mode::Typing);
        w.note_click(Some(true), t0);
        // Small text appears, below the whole-screen threshold, for 5 s.
        let frames: Vec<(u8, u64)> = (0..15).map(|i| (100, i * 350)).collect();
        for i in 0..14 {
            w.note_key(false, t0 + Duration::from_millis(i * 350));
        }
        assert!(run(&mut w, t0, &frames[..14]).is_none(), "fired while the learner was typing");
        // 2 s of keyboard silence after the last key (at 4550 ms): done.
        let (ms, e) = run(&mut w, t0, &[(100, 6000), (100, 6600)]).unwrap();
        assert_eq!(ms, 6600);
        assert!(e.contains("used the keyboard") && e.contains("nothing visibly changed"));
    }

    #[test]
    fn a_focus_click_alone_never_fires_in_typing_mode() {
        let t0 = Instant::now();
        let mut w = armed(Mode::Typing);
        w.note_click(Some(true), t0);
        let frames: Vec<(u8, u64)> = (0..20).map(|i| (100, i * 350)).collect();
        assert!(run(&mut w, t0, &frames).is_none());
    }

    #[test]
    fn enter_ends_typing_sooner() {
        let t0 = Instant::now();
        let mut w = armed(Mode::Typing);
        w.note_key(false, t0);
        w.note_key(true, t0 + Duration::from_millis(300));
        let (ms, e) = run(&mut w, t0, &[(100, 350), (100, 700), (100, 1050), (100, 1400)]).unwrap();
        assert_eq!(ms, 1400);
        assert!(e.contains("pressed Enter"));
    }

    #[test]
    fn typing_without_keyboard_access_falls_back_to_the_screen() {
        let t0 = Instant::now();
        let mut w = armed(Mode::Typing);
        // Changed and stable, but for less than the typing settle time.
        assert!(run(&mut w, t0, &[(140, 0), (140, 350), (140, 1000)]).is_none());
        assert!(run(&mut w, t0, &[(140, 1600)]).is_some());
    }

    #[test]
    fn a_shortcut_without_visible_effect_is_reported() {
        let t0 = Instant::now();
        let mut w = armed(Mode::Keys);
        w.note_key(false, t0);
        let (ms, e) = run(&mut w, t0, &[(100, 700), (100, 1400), (100, 1750)]).unwrap();
        assert_eq!(ms, 1750);
        assert!(e.contains("nothing visibly changed"));
    }

    #[test]
    fn mode_follows_the_step() {
        assert_eq!(Mode::for_kind("write"), Some(Mode::Typing));
        assert_eq!(Mode::for_kind("press_key"), Some(Mode::Keys));
        assert_eq!(Mode::for_kind("scroll"), Some(Mode::Pointer));
        assert_eq!(Mode::for_kind("done"), None);
        assert_eq!(Mode::for_kind("pending"), None);
    }

    #[test]
    fn a_click_on_a_shortcut_step_is_not_a_miss() {
        let t0 = Instant::now();
        let mut w = armed(Mode::Keys);
        w.note_click(None, t0);
        w.note_key(false, t0);
        let (_, e) = run(&mut w, t0, &[(140, 350), (140, 700), (140, 1050), (140, 1400)]).unwrap();
        assert!(e.starts_with("The learner clicked on the screen, used the keyboard"), "{e}");
        assert!(!e.contains("other than the highlighted"));
    }
}
