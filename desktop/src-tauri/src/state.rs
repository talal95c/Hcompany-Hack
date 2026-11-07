use crate::{
    audio,
    coordinates::{Monitor, Rect},
    input, protocol,
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
    pub connected: AtomicBool,
    pub stopped: AtomicBool,
    pub shutdown_done: AtomicBool,
    pub consent: Mutex<Option<input::Consent>>,
    pub captures: Mutex<HashMap<String, Capture>>,
    pub input_lock: Mutex<()>,
    pub capture_lock: tokio::sync::Mutex<()>,
    pub generation: AtomicU64,
    pub revision: AtomicU64,
    pub seen: Mutex<VecDeque<String>>,
    pub results: Mutex<HashMap<String, Value>>,
    pub audio: audio::Audio,
}

impl State {
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
