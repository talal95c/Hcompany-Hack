//! The simulated learner: sees the screen and the tutor's message (never the
//! goal), decides what to do like a given persona, and sometimes errs or asks.
//!
//! The model plays the person (where to click, what to answer, what to ask).
//! How often they misclick or ask is drawn by code from a seeded generator,
//! so a run can be replayed and two harness versions compared fairly.

use crate::agent::Step;
use crate::holo::{self, Holo};
use serde::Deserialize;
use serde_json::json;

#[derive(Clone, Debug)]
pub struct Persona {
    pub id: &'static str,
    /// Who they are, for the model.
    pub description: &'static str,
    /// Chance that a click or field lands off target.
    pub misclick: f64,
    /// Chance, on each new step, that they first ask the tutor something.
    pub ask_rate: f64,
}

pub fn personas() -> Vec<Persona> {
    vec![
        Persona {
            id: "diligent",
            description: "A careful adult who follows instructions exactly and rarely asks questions.",
            misclick: 0.0,
            ask_rate: 0.0,
        },
        Persona {
            id: "novice",
            description: "A complete beginner with computers: slow, unsure of the vocabulary (menu, field, \
                checkbox), sometimes clicks next to the target, and asks basic questions.",
            misclick: 0.15,
            ask_rate: 0.25,
        },
        Persona {
            id: "distracted",
            description: "Someone in a hurry who skims instructions, often clicks the wrong thing and \
                sometimes guesses instead of reading.",
            misclick: 0.3,
            ask_rate: 0.1,
        },
        Persona {
            id: "curious",
            description: "A curious learner who wants to understand why each step matters and asks a lot \
                of questions, sometimes about other features they see.",
            misclick: 0.05,
            ask_rate: 0.5,
        },
    ]
}

pub fn persona(id: &str) -> Option<Persona> {
    personas().into_iter().find(|p| p.id == id)
}

/// Small deterministic generator (xorshift64*), so runs replay.
pub struct Rng(u64);

impl Rng {
    pub fn new(seed: u64) -> Self {
        Self(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15) | 1)
    }
    /// Uniform in [0, 1).
    pub fn next(&mut self) -> f64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        (self.0.wrapping_mul(0x2545_F491_4F6C_DD1D) >> 11) as f64 / (1u64 << 53) as f64
    }
    pub fn chance(&mut self, p: f64) -> bool {
        self.next() < p
    }
    /// A misclick offset: 50 to 140 units away (normalized 0..1000), random direction.
    pub fn offset(&mut self) -> (f64, f64) {
        let angle = self.next() * std::f64::consts::TAU;
        let r = 50.0 + self.next() * 90.0;
        (r * angle.cos(), r * angle.sin())
    }
}

/// What the learner model returns.
#[derive(Deserialize, Debug, Clone)]
pub struct Decision {
    /// "do", "answer" or "stuck"
    #[serde(rename = "move")]
    pub kind: String,
    /// "click", "type", "key", "scroll" or "none"
    pub action: String,
    #[serde(default)]
    pub x: f64,
    #[serde(default)]
    pub y: f64,
    #[serde(default)]
    pub text: String,
    #[serde(default)]
    pub keys: String,
    #[serde(default)]
    pub direction: String,
    #[serde(default)]
    pub reply: String,
    /// A question this persona could ask now (asked only when the dice say so).
    #[serde(default)]
    pub question: String,
}

/// What the learner sees of the tutor.
pub struct View<'a> {
    pub step: &'a Step,
    /// Where the pointer is drawn on the screenshot, if visible.
    pub pointer: Option<(f64, f64)>,
    /// Earlier exchanges with the tutor ("You asked …; the tutor answered …").
    pub notes: &'a [String],
}

pub async fn decide(holo: &Holo, persona: &Persona, view: &View<'_>, screenshot: &str) -> Result<Decision, String> {
    let step = view.step;
    let mut tutor = format!("The tutor says: \"{}\"", step.instruction);
    match step.kind.as_str() {
        "write" => tutor += &format!("\nText to type: \"{}\" (into: {})", step.text, step.element),
        "press_key" => tutor += &format!("\nKeys to press: {}", step.keys),
        "ask_learner" => {
            tutor += "\nThe tutor is asking YOU a question: answer it with move \"answer\" (as this person would, \
                      possibly unsure or wrong).";
            if !step.options.is_empty() {
                tutor += &format!(" Choices: {}.", step.options.join(" / "));
            }
        }
        _ => {}
    }
    let pointer = match (view.pointer, step.hint_only) {
        (Some(_), _) => "The red circle on the screenshot is where the tutor points.",
        (None, true) => "The tutor wants you to find it yourself: there is no pointer.",
        (None, false) => "There is no pointer on the screenshot.",
    };
    let notes = if view.notes.is_empty() {
        String::new()
    } else {
        format!("\nYour earlier exchanges:\n{}", view.notes.join("\n"))
    };
    let prompt = format!(
        "You are role-playing a person who is learning to use this application for the first time, guided live by \
         a tutor. Persona: {persona}\n\
         You only see the screen and the tutor's latest message; you do not know the overall goal.\n\
         {pointer}\n{tutor}{notes}\n\n\
         Decide your next move:\n\
         - do: perform what the tutor asked. action is click, type, key or scroll. x and y are integers in [0, 1000] \
           on this screenshot (for type: the field to type into, and text is exactly what you type; for key: keys \
           like \"enter\" or \"cmd+a\"; for scroll: direction up or down).\n\
         - answer: only when the tutor asked you a question; put your reply in reply (in French).\n\
         - stuck: you cannot find what the tutor means on the screen.\n\
         Always also fill question with one short question this person could ask the tutor right now, in French.",
        persona = persona.description,
    );
    let schema = json!({
        "type": "object",
        "properties": {
            "move": { "type": "string", "enum": ["do", "answer", "stuck"] },
            "action": { "type": "string", "enum": ["click", "type", "key", "scroll", "none"] },
            "x": { "type": "integer", "minimum": 0, "maximum": 1000 },
            "y": { "type": "integer", "minimum": 0, "maximum": 1000 },
            "text": { "type": "string" },
            "keys": { "type": "string" },
            "direction": { "type": "string", "enum": ["up", "down", "left", "right", ""] },
            "reply": { "type": "string" },
            "question": { "type": "string" }
        },
        "required": ["move", "action", "x", "y", "text", "keys", "direction", "reply", "question"]
    });
    let model = std::env::var("SIM_LEARNER_MODEL").unwrap_or_else(|_| holo::fast_model());
    holo.structured("sim_learner", &model, &[screenshot], &prompt, schema).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rng_replays_and_stays_in_range() {
        let (mut a, mut b) = (Rng::new(7), Rng::new(7));
        for _ in 0..1000 {
            let v = a.next();
            assert_eq!(v, b.next());
            assert!((0.0..1.0).contains(&v));
        }
        let mut r = Rng::new(1);
        let hits = (0..10_000).filter(|_| r.chance(0.25)).count();
        assert!((2_200..2_800).contains(&hits), "{hits}");
        let (dx, dy) = Rng::new(3).offset();
        let d = (dx * dx + dy * dy).sqrt();
        assert!((50.0..=140.0).contains(&d));
    }

    #[test]
    fn personas_are_known() {
        assert!(persona("novice").is_some() && persona("nobody").is_none());
        assert!(personas().iter().all(|p| (0.0..=1.0).contains(&p.misclick) && (0.0..=1.0).contains(&p.ask_rate)));
    }
}
