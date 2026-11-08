//! Native audio output for the tutor's voice. Playing from the webview is
//! subject to WebKit's autoplay policy, which silently blocks sound in a
//! panel the user never clicks; the Mac's default output device has no such
//! rule.

use std::collections::VecDeque;
use std::sync::{Arc, Mutex, OnceLock};

struct Player {
    queue: Arc<Mutex<VecDeque<f32>>>,
    rate: u32,
}

static PLAYER: OnceLock<Option<Player>> = OnceLock::new();

fn player() -> Option<&'static Player> {
    PLAYER.get_or_init(start).as_ref()
}

/// Opens the default output device on its own thread (cpal streams are not
/// Send) and keeps it running, playing whatever is queued.
fn start() -> Option<Player> {
    use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

    let queue = Arc::new(Mutex::new(VecDeque::<f32>::new()));
    let (tx, rx) = std::sync::mpsc::channel::<Option<u32>>();
    let q = queue.clone();
    std::thread::Builder::new()
        .name("audio-out".into())
        .spawn(move || {
            let setup = || -> Result<(cpal::Stream, u32), String> {
                let device = cpal::default_host().default_output_device().ok_or("No audio output")?;
                let config = device.default_output_config().map_err(|e| e.to_string())?;
                let channels = config.channels() as usize;
                let rate = config.sample_rate();
                let format = config.sample_format();
                let stream_config: cpal::StreamConfig = config.into();
                let err = |e| eprintln!("[audio-out] {e}");
                let stream = match format {
                    cpal::SampleFormat::F32 => {
                        let q = q.clone();
                        device.build_output_stream(
                            stream_config,
                            move |data: &mut [f32], _: &_| {
                                let mut q = q.lock().unwrap();
                                for frame in data.chunks_mut(channels) {
                                    let s = q.pop_front().unwrap_or(0.0);
                                    frame.fill(s);
                                }
                            },
                            err,
                            None,
                        )
                    }
                    cpal::SampleFormat::I16 => {
                        let q = q.clone();
                        device.build_output_stream(
                            stream_config,
                            move |data: &mut [i16], _: &_| {
                                let mut q = q.lock().unwrap();
                                for frame in data.chunks_mut(channels) {
                                    let s = q.pop_front().unwrap_or(0.0);
                                    frame.fill((s.clamp(-1.0, 1.0) * 32767.0) as i16);
                                }
                            },
                            err,
                            None,
                        )
                    }
                    f => return Err(format!("Unsupported output format {f:?}")),
                }
                .map_err(|e| e.to_string())?;
                stream.play().map_err(|e| e.to_string())?;
                Ok((stream, rate))
            };
            match setup() {
                Ok((stream, rate)) => {
                    let _ = tx.send(Some(rate));
                    // Keep the stream alive for the app's lifetime.
                    let _keep = stream;
                    loop {
                        std::thread::park();
                    }
                }
                Err(e) => {
                    eprintln!("[audio-out] {e}");
                    let _ = tx.send(None);
                }
            }
        })
        .ok()?;
    let rate = rx.recv().ok()??;
    Some(Player { queue, rate })
}

/// Plays `pcm` (mono, `src_rate` Hz) right away, replacing what was playing.
pub fn play(pcm: &[f32], src_rate: u32) -> Result<(), String> {
    play_if(pcm, src_rate, || true)
}

pub(crate) fn play_if(pcm: &[f32], src_rate: u32, allowed: impl FnOnce() -> bool) -> Result<(), String> {
    let p = player().ok_or("No audio output device")?;
    // Linear resampling to the device rate.
    let step = src_rate as f64 / p.rate as f64;
    let n = (pcm.len() as f64 / step) as usize;
    let mut out = VecDeque::with_capacity(n);
    for i in 0..n {
        let pos = i as f64 * step;
        let k = pos as usize;
        let frac = (pos - k as f64) as f32;
        let a = pcm[k.min(pcm.len() - 1)];
        let b = pcm[(k + 1).min(pcm.len() - 1)];
        out.push_back(a + (b - a) * frac);
    }
    let mut queue = p.queue.lock().unwrap();
    if allowed() {
        *queue = out;
    }
    Ok(())
}

pub fn stop() {
    if let Some(p) = PLAYER.get().and_then(|p| p.as_ref()) {
        p.queue.lock().unwrap().clear();
    }
}

#[cfg(test)]
mod tests {
    /// Plays a short sentence on the default output:
    /// `cargo test --lib audio_out -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn plays_a_sentence() {
        let tts = crate::voice::Tts::spawn();
        let (pcm, rate) = tts.say("Rio is ready.".into(), Some("en".into())).unwrap();
        super::play(&pcm, rate).unwrap();
        let p = super::player().unwrap();
        println!("device rate {} Hz, {} samples queued", p.rate, p.queue.lock().unwrap().len());
        std::thread::sleep(std::time::Duration::from_millis(2500));
        println!("left after 2.5 s: {}", p.queue.lock().unwrap().len());
        assert!(p.queue.lock().unwrap().is_empty(), "audio did not drain: output callback not running");
    }
}
