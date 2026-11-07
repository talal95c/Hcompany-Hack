//! Decides when to look again. Instead of trusting a click on the target
//! (hover menus, keyboard shortcuts and typing never click it), the screen is
//! watched locally: when it changes and then settles, the bar is told to send
//! the new screenshot to Holo, which judges what happened.

use crate::capture::{capture_thumb, thumb_diff};
use image::GrayImage;
use serde::Serialize;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter};

/// Mean thumbnail difference that counts as "the screen changed" (hover
/// highlights stay below it; menus, dialogs and new objects go above).
const CHANGED: f32 = 0.8;
/// Two frames closer than this are "stable".
const STABLE: f32 = 0.35;
const TICK: Duration = Duration::from_millis(350);
/// A click on the target with no visible effect is reported after this.
const HIT_GRACE: Duration = Duration::from_millis(1500);

#[derive(Default)]
struct Watch {
    active: bool,
    /// Screen Holo last saw.
    baseline: Option<GrayImage>,
    last: Option<GrayImage>,
    stable_since: Option<Instant>,
    settle: Duration,
    hits: u32,
    misses: u32,
    last_hit: Option<Instant>,
}

static WATCH: Mutex<Option<Watch>> = Mutex::new(None);

#[derive(Serialize, Clone)]
struct Changed {
    /// What we know about the learner's action, for Holo.
    event: String,
}

/// Starts watching for the learner's action on a new step. `baseline` is
/// the screen Holo based the step on; `typing` waits longer for the screen
/// to settle, so a sentence is not cut mid-word.
pub fn arm(baseline: GrayImage, typing: bool) {
    *WATCH.lock().unwrap() = Some(Watch {
        active: true,
        baseline: Some(baseline),
        settle: Duration::from_millis(if typing { 1200 } else { 400 }),
        ..Default::default()
    });
}

pub fn disarm() {
    if let Some(w) = WATCH.lock().unwrap().as_mut() {
        w.active = false;
    }
}

/// Counts a real click during the current step.
pub fn note_click(hit: bool) {
    if let Some(w) = WATCH.lock().unwrap().as_mut().filter(|w| w.active) {
        if hit {
            w.hits += 1;
            w.last_hit = Some(Instant::now());
        } else {
            w.misses += 1;
        }
    }
}

fn describe(w: &Watch, changed: bool) -> String {
    let what = if w.hits > 0 {
        "The learner clicked the highlighted element"
    } else if w.misses > 0 {
        "The learner clicked somewhere other than the highlighted element"
    } else {
        "The learner did not click (hover, keyboard or scroll)"
    };
    if changed {
        format!("{what}, and the screen changed. Check the new screenshot to see whether the action was done.")
    } else {
        format!("{what}, but nothing visibly changed on screen.")
    }
}

pub fn spawn(app: AppHandle) {
    std::thread::Builder::new()
        .name("screen-watch".into())
        .spawn(move || loop {
            std::thread::sleep(TICK);
            let armed = WATCH.lock().unwrap().as_ref().is_some_and(|w| w.active);
            if !armed {
                continue;
            }
            let Ok(now) = capture_thumb() else { continue };

            let mut guard = WATCH.lock().unwrap();
            let Some(w) = guard.as_mut().filter(|w| w.active) else { continue };
            let changed = w.baseline.as_ref().is_some_and(|b| thumb_diff(b, &now) > CHANGED);
            let stable = w.last.as_ref().is_some_and(|l| thumb_diff(l, &now) < STABLE);
            w.stable_since = if stable { w.stable_since.or(Some(Instant::now())) } else { None };
            w.last = Some(now);

            let settled = changed && w.stable_since.is_some_and(|t| t.elapsed() >= w.settle);
            let silent_hit = !changed && w.last_hit.is_some_and(|t| t.elapsed() >= HIT_GRACE);
            if settled || silent_hit {
                let event = describe(w, settled);
                w.active = false;
                drop(guard);
                app.emit_to("main", "watch:changed", Changed { event }).ok();
            }
        })
        .expect("spawn screen watcher");
}
