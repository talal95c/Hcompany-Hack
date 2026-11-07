//! Text-to-speech with Gradium's Phonon, running locally on the CPU.
//!
//! The model lives on one dedicated thread: it is loaded once at startup
//! (downloaded from Hugging Face on first run) and requests are queued to it.
//! Phonon 40m multilingual speaks English, French, German, Spanish and
//! Portuguese: each language gets its own synthesizer (text normalization is
//! per language) and a native voice from Gradium's voice catalog.

use ptts::checkpoint::{Checkpoint, ResolveOptions, DEFAULT_MODEL};
use ptts::preprocess::Lang;
use ptts::synth::{DeviceKind, Quant, SpeechOptions, Synth};
use ptts::voice_catalog::{VoiceCatalog, DEFAULT_VOICE_CATALOG};
use std::collections::HashMap;
use std::sync::mpsc;
use std::sync::Mutex;

/// Gated on Hugging Face: needs HF_TOKEN and the model's terms accepted.
/// Falls back to the public English model (Phonon 31m) when unavailable.
const PREFERRED_MODEL: &str = "hf://gradium/phonon-40m-multilingual";

type Reply = mpsc::Sender<Result<(Vec<f32>, u32), String>>;

struct Job {
    text: String,
    lang: Option<String>,
    reply: Reply,
}

pub struct Tts {
    tx: Mutex<mpsc::Sender<Job>>,
}

/// Which model ended up loaded, or why none did. Shown in the app status.
pub static STATE: Mutex<String> = Mutex::new(String::new());

fn set_state(s: impl Into<String>) {
    *STATE.lock().unwrap() = s.into();
}

/// ISO code → Phonon language and the catalog voice used for it (None keeps
/// the checkpoint's default voice). Override with PHONON_VOICE_<LANG>.
fn lang_info(code: &str) -> Option<(Lang, Option<String>)> {
    let (lang, voice) = match code {
        "en" => (Lang::En, None),
        "fr" => (Lang::Fr, Some("Noémie")),
        "de" => (Lang::De, Some("Annika")),
        "es" => (Lang::Es, Some("Noa")),
        "pt" => (Lang::Pt, Some("Isadora")),
        _ => return None,
    };
    let custom = std::env::var(format!("PHONON_VOICE_{}", code.to_uppercase())).ok();
    Some((lang, custom.or(voice.map(String::from))))
}

/// Strips what should not be read aloud: markdown marks and emoji.
fn speakable(text: &str) -> String {
    text.chars()
        .filter(|c| !matches!(c, '*' | '#' | '`' | '_' | '>' | '|') && (*c as u32) < 0x2190)
        .collect::<String>()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
}

/// Language of `text` among the five Phonon speaks, when the detection is
/// reliable (short sentences often are not).
pub fn detect(text: &str) -> Option<&'static str> {
    use whatlang::{Detector, Lang as W};
    let detector = Detector::with_allowlist(vec![W::Eng, W::Fra, W::Deu, W::Spa, W::Por]);
    let info = detector.detect(text)?;
    if !info.is_reliable() && info.confidence() < 0.5 {
        return None;
    }
    Some(match info.lang() {
        W::Fra => "fr",
        W::Deu => "de",
        W::Spa => "es",
        W::Por => "pt",
        _ => "en",
    })
}

struct Engine {
    checkpoint: Checkpoint,
    multilingual: bool,
    catalog: Option<VoiceCatalog>,
    /// One synthesizer per language, built on first use, with its voice name.
    synths: HashMap<String, (Synth, Option<String>)>,
}

impl Engine {
    fn load() -> Result<Self, String> {
        let options = || ResolveOptions { quant: Quant::Q80, weights: None };
        let model = std::env::var("PHONON_MODEL")
            .ok()
            .filter(|m| !m.trim().is_empty())
            .unwrap_or_else(|| PREFERRED_MODEL.to_string());
        let (checkpoint, name) = match Checkpoint::locate(&model, options()) {
            Ok(c) => (c, model.trim_start_matches("hf://").to_string()),
            Err(e) => {
                eprintln!("[phonon] {model} unavailable ({e}), falling back to Phonon 31m");
                let c = Checkpoint::locate(DEFAULT_MODEL, options()).map_err(|e| e.to_string())?;
                (c, "gradium/phonon-31m-en (fallback)".to_string())
            }
        };
        let multilingual = name.contains("multilingual");
        set_state(name);
        let mut engine = Self {
            checkpoint,
            multilingual,
            catalog: VoiceCatalog::new(DEFAULT_VOICE_CATALOG).ok(),
            synths: HashMap::new(),
        };
        engine.synth("en")?; // warm up
        Ok(engine)
    }

    fn synth(&mut self, code: &str) -> Result<&(Synth, Option<String>), String> {
        let code = if self.multilingual { code } else { "en" };
        if !self.synths.contains_key(code) {
            let (lang, voice) = lang_info(code).unwrap_or((Lang::En, None));
            let mut synth = self
                .checkpoint
                .builder(lang)
                .device(DeviceKind::Cpu)
                .build()
                .map_err(|e| e.to_string())?;
            self.checkpoint.register_voices(&mut synth);
            // Fetch the native voice for this language from the catalog.
            let voice = voice.and_then(|name| {
                let catalog = self.catalog.as_ref()?;
                let entry = catalog.find(&name).ok().flatten()?;
                let path = catalog.fetch(entry).ok()?;
                synth.add_voice_file(&name, &path).ok()?;
                Some(name)
            });
            self.synths.insert(code.to_string(), (synth, voice));
        }
        Ok(&self.synths[code])
    }

    fn say(&mut self, text: &str, lang: Option<&str>) -> Result<(Vec<f32>, u32), String> {
        let text = &speakable(text);
        // The text's own language first: a French sentence read by the
        // English voice (or the reverse) is the worst outcome.
        let code = detect(text)
            .or(lang.filter(|l| lang_info(l).is_some()))
            .unwrap_or("en");
        let (synth, voice) = self.synth(code)?;
        let mut options = SpeechOptions::default();
        if let Some(v) = voice {
            options = options.voice(v.clone());
        }
        let pcm = synth.say_with(text, &options).map_err(|e| e.to_string())?;
        Ok((pcm, synth.sample_rate()))
    }
}

impl Tts {
    pub fn spawn() -> Self {
        let (tx, rx) = mpsc::channel::<Job>();
        std::thread::Builder::new()
            .name("phonon-tts".into())
            .spawn(move || {
                set_state("loading");
                let mut engine = match Engine::load() {
                    Ok(e) => Some(e),
                    Err(e) => {
                        set_state(format!("error: {e}"));
                        None
                    }
                };
                for job in rx {
                    let out = match engine.as_mut() {
                        Some(e) => e.say(&job.text, job.lang.as_deref()),
                        None => Err(format!("Phonon is not available: {}", STATE.lock().unwrap())),
                    };
                    let _ = job.reply.send(out);
                }
            })
            .expect("spawn TTS thread");
        Self { tx: Mutex::new(tx) }
    }

    /// Blocking: waits for the model (and its first load) to finish.
    pub fn say(&self, text: String, lang: Option<String>) -> Result<(Vec<f32>, u32), String> {
        let (reply, rx) = mpsc::channel();
        self.tx
            .lock()
            .unwrap()
            .send(Job { text, lang, reply })
            .map_err(|_| "TTS thread stopped")?;
        rx.recv().map_err(|_| "TTS thread stopped".to_string())?
    }
}
