use std::sync::{
    atomic::{AtomicBool, Ordering},
    mpsc, Arc, Mutex,
};

use base64::Engine;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};

enum Control {
    Start,
    Stop,
    Quit,
}

pub struct Audio {
    sender: mpsc::Sender<Control>,
    active: Arc<AtomicBool>,
}

impl Audio {
    pub fn new(app: AppHandle, tx: tokio::sync::mpsc::Sender<Value>, session: String) -> Self {
        let (sender, receiver) = mpsc::channel();
        let active = Arc::new(AtomicBool::new(false));
        let active_thread = active.clone();
        std::thread::spawn(move || {
            let mut current: Option<(Recording, String)> = None;
            for command in receiver {
                match command {
                    Control::Start if current.is_none() => {
                        let id = uuid::Uuid::new_v4().to_string();
                        let start = crate::protocol::envelope(
                            &session,
                            "ptt.start",
                            json!({"utterance_id": id}),
                            None,
                        );
                        if tx.try_send(start).is_err() {
                            continue;
                        }
                        active_thread.store(true, Ordering::SeqCst);
                        match stream(
                            tx.clone(),
                            session.clone(),
                            id.clone(),
                            active_thread.clone(),
                            app.clone(),
                        ) {
                            Ok(stream) => {
                                current = Some((stream, id));
                                let _ = app.emit("audio.status", true);
                            }
                            Err(error) => {
                                active_thread.store(false, Ordering::SeqCst);
                                let _ = app.emit("native.error", error);
                                let _ = tx.try_send(crate::protocol::envelope(
                                    &session,
                                    "ptt.stop",
                                    json!({"utterance_id": id}),
                                    None,
                                ));
                            }
                        }
                    }
                    Control::Start => {}
                    Control::Stop | Control::Quit => {
                        active_thread.store(false, Ordering::SeqCst);
                        if let Some((stream, id)) = current.take() {
                            let Recording { stream, encoder } = stream;
                            drop(stream);
                            encoder.lock().unwrap().flush();
                            let _ = tx.try_send(crate::protocol::envelope(
                                &session,
                                "ptt.stop",
                                json!({"utterance_id": id}),
                                None,
                            ));
                        }
                        let _ = app.emit("audio.status", false);
                        if matches!(command, Control::Quit) {
                            break;
                        }
                    }
                }
            }
        });
        Self { sender, active }
    }

    pub fn start(&self) {
        let _ = self.sender.send(Control::Start);
    }
    pub fn stop(&self) {
        self.active.store(false, Ordering::SeqCst);
        let _ = self.sender.send(Control::Stop);
    }
}

impl Drop for Audio {
    fn drop(&mut self) {
        self.active.store(false, Ordering::SeqCst);
        let _ = self.sender.send(Control::Quit);
    }
}

struct Recording {
    stream: cpal::Stream,
    encoder: Arc<Mutex<Encoder>>,
}

fn stream(
    tx: tokio::sync::mpsc::Sender<Value>,
    session: String,
    id: String,
    active: Arc<AtomicBool>,
    app: AppHandle,
) -> Result<Recording, String> {
    let device = cpal::default_host()
        .default_input_device()
        .ok_or("Aucun microphone disponible")?;
    let config = device.default_input_config().map_err(|e| e.to_string())?;
    let encoder = Arc::new(Mutex::new(Encoder {
        tx,
        session,
        id,
        active: active.clone(),
        app: app.clone(),
        channels: config.channels() as usize,
        sample_rate: config.sample_rate().0,
        phase: 0,
        sequence: 0,
        bytes: Vec::with_capacity(3200),
    }));
    let callback = encoder.clone();
    let on_error = move |_error| {
        active.store(false, Ordering::SeqCst);
        let _ = app.emit(
            "native.error",
            "Microphone interrompu ; relâchez puis réessayez.",
        );
    };
    let result = match config.sample_format() {
        cpal::SampleFormat::F32 => device.build_input_stream(
            &config.into(),
            move |data: &[f32], _| callback.lock().unwrap().encode(data.iter().copied()),
            on_error,
            None,
        ),
        cpal::SampleFormat::I16 => device.build_input_stream(
            &config.into(),
            move |data: &[i16], _| {
                callback
                    .lock()
                    .unwrap()
                    .encode(data.iter().map(|s| *s as f32 / 32768.0))
            },
            on_error,
            None,
        ),
        cpal::SampleFormat::U16 => device.build_input_stream(
            &config.into(),
            move |data: &[u16], _| {
                callback
                    .lock()
                    .unwrap()
                    .encode(data.iter().map(|s| (*s as f32 - 32768.0) / 32768.0))
            },
            on_error,
            None,
        ),
        _ => return Err("Format microphone non pris en charge".into()),
    }
    .map_err(|e| e.to_string())?;
    result.play().map_err(|e| e.to_string())?;
    Ok(Recording {
        stream: result,
        encoder,
    })
}

struct Encoder {
    tx: tokio::sync::mpsc::Sender<Value>,
    session: String,
    id: String,
    active: Arc<AtomicBool>,
    app: AppHandle,
    channels: usize,
    sample_rate: u32,
    phase: u32,
    sequence: u64,
    bytes: Vec<u8>,
}

impl Encoder {
    fn encode(&mut self, data: impl Iterator<Item = f32>) {
        if !self.active.load(Ordering::SeqCst) {
            return;
        }
        let mut sum = 0.0;
        for (index, value) in data.enumerate() {
            sum += value;
            if (index + 1) % self.channels != 0 {
                continue;
            }
            self.phase += 16_000;
            while self.phase >= self.sample_rate {
                self.phase -= self.sample_rate;
                let sample = ((sum / self.channels as f32).clamp(-1., 1.) * 32767.) as i16;
                self.bytes.extend(sample.to_le_bytes());
            }
            sum = 0.0;
            if self.bytes.len() >= 3200 {
                self.flush();
                if !self.active.load(Ordering::SeqCst) {
                    return;
                }
            }
        }
    }

    fn flush(&mut self) {
        if self.bytes.is_empty() {
            return;
        }
        let packet = crate::protocol::envelope(
            &self.session,
            "audio.chunk",
            json!({
                "utterance_id":self.id, "sequence":self.sequence,
                "encoding":"pcm_s16le", "sample_rate":16000,
                "data_base64":base64::engine::general_purpose::STANDARD.encode(&self.bytes)
            }),
            None,
        );
        if self.tx.try_send(packet).is_err() {
            self.active.store(false, Ordering::SeqCst);
            let _ = self
                .app
                .emit("native.error", "File audio saturée ; dictée interrompue.");
            self.bytes.clear();
            return;
        }
        self.sequence += 1;
        self.bytes.clear();
    }
}
