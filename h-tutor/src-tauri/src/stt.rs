//! Speech-to-text with Gladia Live (WebSocket). The microphone is captured in
//! Rust with cpal, downmixed and resampled to 16 kHz PCM16, and streamed to
//! Gladia. Partial and final transcripts are forwarded to the bar as events.
//!
//! One utterance per session: the session stops on the first final transcript
//! (or when the user clicks the mic again).

use futures_util::{SinkExt, StreamExt};
use serde::Serialize;
use serde_json::{Value, json};
use std::sync::Arc;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::{AppHandle, Emitter};
use tokio::sync::mpsc;
use tokio_tungstenite::tungstenite::Message;

const TARGET_RATE: u32 = 16_000;

/// Stop flag of the session in progress, if any.
static CURRENT: Mutex<Option<Arc<AtomicBool>>> = Mutex::new(None);

#[derive(Serialize, Clone)]
struct Transcript {
    text: String,
    is_final: bool,
    /// Detected language (ISO 639-1), e.g. "fr".
    language: Option<String>,
}

fn api_key() -> Option<String> {
    std::env::var("GLADIA_API_KEY").ok().filter(|k| !k.trim().is_empty())
}

pub fn has_key() -> bool {
    api_key().is_some()
}

#[tauri::command]
pub fn listen_stop() {
    if let Some(stop) = CURRENT.lock().unwrap().take() {
        stop.store(true, Ordering::SeqCst);
    }
}

/// Which languages Gladia may hear. "Auto" detects per sentence among the
/// supported ones, which an accent can fool: "help me" spoken with a French
/// accent came back as "m'a aidé". A language chosen by the learner pins it.
fn language_config(lang: Option<&str>) -> serde_json::Value {
    const SUPPORTED: [&str; 5] = ["en", "fr", "de", "es", "pt"];
    match lang.filter(|l| SUPPORTED.contains(l)) {
        Some(l) => json!({ "languages": [l], "code_switching": false }),
        None => json!({ "languages": SUPPORTED, "code_switching": true }),
    }
}

#[tauri::command]
pub async fn listen_start(app: AppHandle, lang: Option<String>) -> Result<(), String> {
    let key = api_key().ok_or("GLADIA_API_KEY is missing from .env")?;
    listen_stop();
    let stop = Arc::new(AtomicBool::new(false));
    *CURRENT.lock().unwrap() = Some(stop.clone());

    // 1. Open a live session.
    let res = reqwest::Client::new()
        .post("https://api.gladia.io/v2/live")
        .header("x-gladia-key", key)
        .json(&json!({
            "encoding": "wav/pcm",
            "sample_rate": TARGET_RATE,
            "bit_depth": 16,
            "channels": 1,
            "endpointing": 0.7,
            "maximum_duration_without_endpointing": 15,
            "language_config": language_config(lang.as_deref()),
            "messages_config": { "receive_partial_transcripts": true }
        }))
        .send()
        .await
        .map_err(|e| format!("Gladia: {e}"))?;
    let status = res.status();
    let body: Value = res.json().await.map_err(|e| format!("Gladia: {e}"))?;
    if !status.is_success() {
        return Err(format!("Gladia {status}: {body}"));
    }
    let url = body["url"].as_str().ok_or("Gladia: no session URL")?.to_string();

    // 2. Start the microphone on its own thread (cpal streams are not Send).
    let (audio_tx, audio_rx) = mpsc::unbounded_channel::<Vec<u8>>();
    start_mic(audio_tx, stop.clone())?;

    // 3. Pump audio up and transcripts down.
    let (ws, _) = tokio_tungstenite::connect_async(url.as_str()).await.map_err(|e| format!("Gladia WebSocket: {e}"))?;
    let (mut sink, mut source) = ws.split();
    app.emit_to("main", "stt:state", true).ok();

    let stop_up = stop.clone();
    let app_up = app.clone();
    let uploader = tauri::async_runtime::spawn(async move {
        let mut audio_rx = audio_rx;
        loop {
            if stop_up.load(Ordering::SeqCst) {
                break;
            }
            match tokio::time::timeout(std::time::Duration::from_millis(100), audio_rx.recv()).await {
                Ok(Some(chunk)) => {
                    app_up.emit_to("main", "stt:level", rms(&chunk)).ok();
                    if sink.send(Message::Binary(chunk.into())).await.is_err() {
                        break;
                    }
                }
                Ok(None) => break,
                Err(_) => {}
            }
        }
        let _ = sink.send(Message::Text(json!({ "type": "stop_recording" }).to_string().into())).await;
    });

    let app_down = app.clone();
    let stop_down = stop.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(Ok(msg)) = source.next().await {
            let Message::Text(text) = msg else { continue };
            let Ok(v) = serde_json::from_str::<Value>(&text) else { continue };
            if v["type"] != "transcript" {
                continue;
            }
            let t = Transcript {
                text: v["data"]["utterance"]["text"].as_str().unwrap_or("").trim().to_string(),
                is_final: v["data"]["is_final"].as_bool().unwrap_or(false),
                language: v["data"]["utterance"]["language"].as_str().map(String::from),
            };
            if t.text.is_empty() {
                continue;
            }
            let done = t.is_final;
            app_down.emit_to("main", "stt:transcript", t).ok();
            if done {
                stop_down.store(true, Ordering::SeqCst);
                break;
            }
        }
        stop_down.store(true, Ordering::SeqCst);
        let _ = uploader.await;
        app_down.emit_to("main", "stt:state", false).ok();
    });
    Ok(())
}

/// Loudness of a PCM16 chunk (RMS, 0..1); drives the bar's waveform.
fn rms(pcm: &[u8]) -> f32 {
    let n = pcm.len() / 2;
    if n == 0 {
        return 0.0;
    }
    let sum: f64 = pcm
        .as_chunks::<2>()
        .0
        .iter()
        .map(|b| {
            let s = i16::from_le_bytes([b[0], b[1]]) as f64 / 32768.0;
            s * s
        })
        .sum();
    (sum / n as f64).sqrt() as f32
}

/// Captures the default input device until `stop` is set, sending 16 kHz
/// mono PCM16 chunks of about 100 ms.
fn start_mic(tx: mpsc::UnboundedSender<Vec<u8>>, stop: Arc<AtomicBool>) -> Result<(), String> {
    use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

    let (ready_tx, ready_rx) = std::sync::mpsc::channel::<Result<(), String>>();
    std::thread::spawn(move || {
        let setup = || -> Result<cpal::Stream, String> {
            let device = cpal::default_host().default_input_device().ok_or("No microphone found")?;
            let config = device.default_input_config().map_err(|e| format!("Microphone: {e}"))?;
            let channels = config.channels() as usize;
            let rate = config.sample_rate() as f64;
            let mut resampler = Resampler::new(rate, TARGET_RATE as f64, channels, tx);
            let err = |e| eprintln!("[mic] {e}");
            let format = config.sample_format();
            let stream_config: cpal::StreamConfig = config.into();
            let stream = match format {
                cpal::SampleFormat::F32 => device.build_input_stream(
                    stream_config,
                    move |data: &[f32], _: &_| resampler.push(data.iter().copied()),
                    err,
                    None,
                ),
                cpal::SampleFormat::I16 => device.build_input_stream(
                    stream_config,
                    move |data: &[i16], _: &_| resampler.push(data.iter().map(|s| *s as f32 / 32768.0)),
                    err,
                    None,
                ),
                f => return Err(format!("Unsupported microphone format {f:?}")),
            }
            .map_err(|e| format!("Microphone: {e}"))?;
            stream.play().map_err(|e| format!("Microphone: {e}"))?;
            Ok(stream)
        };
        match setup() {
            Ok(stream) => {
                let _ = ready_tx.send(Ok(()));
                while !stop.load(Ordering::SeqCst) {
                    std::thread::sleep(std::time::Duration::from_millis(30));
                }
                drop(stream);
            }
            Err(e) => {
                let _ = ready_tx.send(Err(e));
            }
        }
    });
    ready_rx.recv().map_err(|_| "Microphone thread failed".to_string())?
}

/// Downmix + linear-interpolation resampling to 16 kHz, batched into PCM16 chunks.
struct Resampler {
    step: f64,
    pos: f64,
    channels: usize,
    prev: f32,
    frame: Vec<f32>,
    out: Vec<u8>,
    tx: mpsc::UnboundedSender<Vec<u8>>,
}

impl Resampler {
    fn new(from: f64, to: f64, channels: usize, tx: mpsc::UnboundedSender<Vec<u8>>) -> Self {
        Self { step: from / to, pos: 0.0, channels: channels.max(1), prev: 0.0, frame: Vec::new(), out: Vec::new(), tx }
    }

    fn push(&mut self, samples: impl Iterator<Item = f32>) {
        for s in samples {
            self.frame.push(s);
            if self.frame.len() < self.channels {
                continue;
            }
            let mono = self.frame.iter().sum::<f32>() / self.channels as f32;
            self.frame.clear();
            // Emit every output sample that falls between prev and mono.
            while self.pos <= 1.0 {
                let v = self.prev + (mono - self.prev) * self.pos as f32;
                let pcm = (v.clamp(-1.0, 1.0) * 32767.0) as i16;
                self.out.extend_from_slice(&pcm.to_le_bytes());
                self.pos += self.step;
            }
            self.pos -= 1.0;
            self.prev = mono;
            if self.out.len() >= 3200 {
                // 100 ms at 16 kHz, 16-bit
                let _ = self.tx.send(std::mem::take(&mut self.out));
            }
        }
    }
}

#[cfg(test)]
mod lang_tests {
    #[test]
    fn a_chosen_language_pins_transcription() {
        assert_eq!(super::language_config(Some("en"))["languages"], serde_json::json!(["en"]));
        assert_eq!(super::language_config(Some("en"))["code_switching"], false);
        assert_eq!(super::language_config(None)["code_switching"], true);
        assert_eq!(super::language_config(Some("xx"))["code_switching"], true);
    }
}
