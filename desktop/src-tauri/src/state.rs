use crate::{
    audio,
    coordinates::{Monitor, Rect},
    guide, input, protocol,
};
use serde_json::Value;
use std::{
    collections::{HashMap, VecDeque},
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        Mutex,
    },
    time::Instant,
};
use tokio::sync::{mpsc, watch};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Lifecycle {
    Running,
    Stopped,
    Shutdown,
}

pub struct Capture {
    pub crop: Rect,
    pub monitor: Monitor,
    pub ui_revision: u64,
    pub at: Instant,
}

pub struct State {
    pub session: String,
    pub token: String,
    pub tx: mpsc::Sender<Value>,
    pub lifecycle: watch::Sender<Lifecycle>,
    pub frontend: watch::Sender<u8>,
    pub guide: guide::Visibility,
    pub connected: AtomicBool,
    pub stopped: AtomicBool,
    pub shutdown_done: AtomicBool,
    pub consent: Mutex<Option<input::Consent>>,
    pub captures: Mutex<HashMap<String, Capture>>,
    pub input_lock: tokio::sync::Mutex<()>,
    pub a11y: crate::a11y::Service,
    pub capture_lock: tokio::sync::Mutex<()>,
    pub generation: AtomicU64,
    pub revision: AtomicU64,
    pub seen: Mutex<VecDeque<String>>,
    pub results: Mutex<HashMap<String, Value>>,
    pub audio: audio::Audio,
}

impl State {
    pub fn frontend_ready(&self, window: &str) -> Result<(), String> {
        let bit = frontend_bit(window)?;
        self.frontend.send_modify(|ready| *ready |= bit);
        Ok(())
    }

    pub fn send(&self, kind: &str, payload: Value, reply: Option<&str>) -> Result<(), String> {
        if !self.connected.load(Ordering::SeqCst) {
            return Err("Engine déconnecté".into());
        }
        let packet = protocol::envelope(&self.session, kind, payload, reply);
        protocol::validate(&packet, &self.session)?;
        self.tx
            .try_send(packet)
            .map_err(|_| "File engine saturée".into())
    }
}

fn frontend_bit(window: &str) -> Result<u8, String> {
    match window {
        "guide" => Ok(1),
        "pill" => Ok(2),
        _ => Err("unknown frontend window".into()),
    }
}

pub async fn wait_for_frontend(
    mut ready: watch::Receiver<u8>,
    mut control: watch::Receiver<Lifecycle>,
) -> bool {
    loop {
        if *control.borrow() == Lifecycle::Shutdown {
            return false;
        }
        if *ready.borrow_and_update() == 3 {
            return true;
        }
        tokio::select! {
            result = ready.changed() => if result.is_err() { return false; },
            result = control.changed() => if result.is_err() { return false; },
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn both_frontends_must_acknowledge_listeners() {
        let (ready, rx) = watch::channel(0);
        let (_control, control_rx) = watch::channel(Lifecycle::Running);
        let mut waiting = tokio::spawn(wait_for_frontend(rx, control_rx));
        for _ in 0..2 {
            ready.send_modify(|bits| *bits |= frontend_bit("pill").unwrap());
            assert!(
                tokio::time::timeout(std::time::Duration::from_millis(10), &mut waiting)
                    .await
                    .is_err()
            );
        }
        ready.send_modify(|bits| *bits |= frontend_bit("guide").unwrap());
        assert!(waiting.await.unwrap());
        assert!(frontend_bit("other").is_err());
    }

    #[tokio::test]
    async fn readiness_survives_early_acks_and_shutdown_cancels_wait() {
        let (ready, rx) = watch::channel(0);
        let (control, control_rx) = watch::channel(Lifecycle::Running);
        ready.send_modify(|bits| *bits = 3);
        assert!(wait_for_frontend(rx, control_rx.clone()).await);
        let (_not_ready, rx) = watch::channel(0);
        control.send(Lifecycle::Shutdown).unwrap();
        assert!(!wait_for_frontend(rx, control_rx).await);
    }
}
