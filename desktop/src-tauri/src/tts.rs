pub trait Speech: Send + Sync {
    fn speak(&self, text: &str) -> Result<(), String>;
    fn stop(&self);
}

pub struct NoSpeech;

impl Speech for NoSpeech {
    fn speak(&self, _text: &str) -> Result<(), String> {
        Err("Synthèse vocale indisponible : texte affiché.".into())
    }

    fn stop(&self) {}
}
