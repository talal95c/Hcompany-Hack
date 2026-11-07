//! Goal mode: turns a free-form goal ("comment je crée un container ?") into
//! a milestone graph, looking at the learner's screen. The result goes
//! through exactly the same harness as an authored tutorial.

use crate::capture::Shot;
use crate::holo::{self, Holo};
use crate::tutorial::{App, Milestone, Tutorial};
use serde::Deserialize;
use serde_json::json;

#[derive(Deserialize)]
struct Plan {
    title: String,
    app: String,
    goal: String,
    milestones: Vec<PlanMilestone>,
}

#[derive(Deserialize)]
struct PlanMilestone {
    goal: String,
    done_when: String,
    #[serde(default)]
    hints: Vec<String>,
    #[serde(default)]
    teach: String,
}

/// `knowledge`: what the organization's knowledge base knows about the request
/// (platform.rs), so milestones and hints follow its proven paths.
pub async fn plan(holo: &Holo, request: &str, shot: &Shot, knowledge: Option<&str>) -> Result<Tutorial, String> {
    let schema = json!({
        "type": "object",
        "properties": {
            "title": { "type": "string", "description": "Short tutorial title, max 6 words, English" },
            "app": { "type": "string", "description": "Application the tutorial is about" },
            "goal": { "type": "string", "description": "The overall goal as an imperative sentence, English" },
            "milestones": {
                "type": "array", "minItems": 1, "maxItems": 7,
                "items": {
                    "type": "object",
                    "properties": {
                        "goal": { "type": "string" },
                        "done_when": { "type": "string" },
                        "hints": { "type": "array", "items": { "type": "string" }, "maxItems": 3 },
                        "teach": { "type": "string" }
                    },
                    "required": ["goal", "done_when", "hints", "teach"]
                }
            }
        },
        "required": ["title", "app", "goal", "milestones"]
    });
    let prompt = format!(
        "You design hands-on software tutorials. The screenshot shows the learner's screen right now.\n\
         The learner's request (it may be a question, a goal or a pasted tutorial):\n\"\"\"\n{request}\n\"\"\"\n\n\
         Design the tutorial as 1 to 7 milestones the learner will reach in the application's graphical \
         interface, in order. A milestone is a meaningful sub-goal (e.g. \"Add a torus\"), not a single click.\n\
         For each milestone, in English:\n\
         - goal: an imperative sub-goal.\n\
         - done_when: the intended state, visible on screen once it is reached, concrete enough to check on a \
           screenshot (e.g. \"A Torus object is listed in the outliner\"). Describe the state, not a specific \
           object the learner may not have: the screen may not be a fresh app (\"no mesh left in the outliner\", \
           not \"the default cube is gone\").\n\
         - hints: up to 3 short known GUI paths (e.g. \"Add > Mesh > Torus\"), only if you are confident.\n\
         - teach: one sentence about the concept behind it, or empty.\n\
         Use the application visible on screen when relevant. Keep the tutorial focused on the request."
    );
    let prompt = match knowledge {
        Some(k) => format!(
            "{prompt}\n\nThe organization's knowledge base has these paths. When they match the request, build the \
             milestones from them and use their steps as hints (menu paths and shortcuts for the learner's version); \
             ignore the ones that do not match.\n{k}"
        ),
        None => prompt,
    };
    let p: Plan = holo.structured("plan", &holo::smart_model(), &[&shot.data_uri], &prompt, schema).await?;

    let milestones: Vec<Milestone> = p
        .milestones
        .into_iter()
        .enumerate()
        .map(|(i, m)| Milestone {
            id: format!("m{}", i + 1),
            goal: m.goal,
            done_when: m.done_when,
            hints: m.hints,
            teach: Some(m.teach).filter(|t| !t.trim().is_empty()),
            ..Default::default()
        })
        .collect();
    let t = Tutorial {
        id: crate::tutorial::slug(&format!("{} {}", p.app, p.title)),
        version: 1,
        title: p.title,
        app: App { name: p.app, bundle_id: None, min_version: None },
        goal: p.goal,
        language: None,
        source: "generated".into(),
        source_url: None,
        start: None,
        milestones,
    };
    t.validate()?;
    Ok(t)
}
