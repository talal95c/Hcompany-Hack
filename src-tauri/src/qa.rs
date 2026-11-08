//! The front door: whatever the learner types or says, Holo decides what
//! they need. It looks at the screen, may call `search` for up-to-date docs
//! (same tool as the tutorial harness), then either:
//! - `reply`: they want information; a short spoken answer, details, and the
//!   on-screen element it is about (so the bar can still offer "Show me");
//! - `guide`: they want to do it now; the bar starts a guided tutorial.

use crate::capture::capture_primary;
use crate::holo::{self, Holo};
use crate::search::{self, Source};
use serde::Serialize;
use serde_json::{Value, json};

#[derive(Serialize)]
pub struct QaAnswer {
    /// "answer" or "guide"
    pub kind: String,
    /// For "guide": the goal, as an imperative sentence.
    pub goal: String,
    pub answer: String,
    pub details: Vec<String>,
    pub app_name: String,
    /// The element the answer is about, if it is on screen (English).
    pub target: String,
    pub searches: Vec<SearchDone>,
    pub sources: Vec<Source>,
}

#[derive(Serialize)]
pub struct SearchDone {
    pub app_name: String,
    pub query: String,
    pub backend: String,
}

fn guide_tool() -> Value {
    json!({ "type": "function", "function": {
        "name": "guide",
        "description": "Start a guided tutorial: the learner wants to do something in an application now and \
            will be walked through it on their screen, one action at a time.",
        "parameters": { "type": "object",
            "properties": {
                "goal": { "type": "string", "description": "What the learner wants to achieve, as an imperative sentence in English" }
            },
            "required": ["goal"] }
    }})
}

fn reply_tool() -> Value {
    json!({ "type": "function", "function": {
        "name": "reply",
        "description": "Answer the learner's question.",
        "parameters": { "type": "object",
            "properties": {
                "answer": { "type": "string", "description": "One or two short spoken sentences (max 40 words) in the learner's language, read aloud. Plain text: no markdown, no lists (put lists in details)." },
                "details": { "type": "array", "items": { "type": "string" }, "maxItems": 6,
                    "description": "Short points shown under the answer (menu paths, shortcuts, steps, caveats), in the learner's language. Empty if not needed. No markdown." },
                "app_name": { "type": "string", "description": "The application the question is about" },
                "target": { "type": "string", "description": "English description of the on-screen element the answer is about, with its location, or empty if it is not visible" }
            },
            "required": ["answer", "details", "app_name", "target"] }
    }})
}

#[tauri::command]
pub async fn answer_question(
    question: String,
    lang: Option<String>,
    state: tauri::State<'_, crate::AppState>,
) -> Result<QaAnswer, String> {
    let holo: &Holo = &state.holo;
    let shot = tauri::async_runtime::spawn_blocking(capture_primary).await.map_err(|e| e.to_string())??;
    let language = lang.as_deref().and_then(crate::agent::language_name).unwrap_or("English");
    let tu = if language == "French" { ", using \"tu\"" } else { "" };

    let mut messages = vec![
        json!({ "role": "system", "content": format!(
            "You are Holo, a software tutor. The screenshot shows the learner's screen. Decide what they need:\n\
             - guide(goal): they want to do something in an application now (\"how do I…\", \"help me…\", \
             \"I want to…\", an imperative task) and it can be done on this computer. They learn best by doing, \
             so prefer guide for how-to requests about an app they can use now.\n\
             - reply(...): they want information: what something is, why, where it is, a comparison, an \
             opinion, a fact, or they explicitly ask to just be told. Also reply when the task cannot be done \
             on this computer.\n\
             If the answer depends on the application's version or you are not sure of a menu path or shortcut, \
             call search(app_name, query) first. Do not act on the screen. Learner language: {language}{tu}. \
             Never infer the learner's language from the language of the application on screen."
        ) }),
        json!({ "role": "user", "content": [
            { "type": "text", "text": "<observation>\n" },
            { "type": "image_url", "image_url": { "url": shot.data_uri } },
            { "type": "text", "text": format!("\n</observation>\nThe learner says: {question}") }
        ]}),
    ];

    let mut searches = Vec::new();
    let mut sources = Vec::new();
    for _ in 0..4 {
        let body = json!({
            "model": holo::smart_model(),
            "messages": messages,
            "tools": [search::tool(), reply_tool(), guide_tool()],
            "tool_choice": "required",
            "temperature": 0.6,
            "reasoning_effort": "low",
            "max_tokens": 3072,
        });
        let (msg, _, _) = holo.chat_stream(&body, &crate::emit_thinking).await?;
        let Some(call) = msg["tool_calls"].as_array().and_then(|c| c.first()).cloned() else { continue };
        let args: Value =
            call["function"]["arguments"].as_str().and_then(|a| serde_json::from_str(a).ok()).unwrap_or(json!({}));
        let s = |k: &str| args[k].as_str().unwrap_or("").to_string();

        if call["function"]["name"] == "search" && searches.len() < 2 {
            let (app_name, query) = (s("app_name"), s("query"));
            crate::emit_status(&format!("Searching {app_name} docs: {query}"));
            let r = search::run(holo, &app_name, &query).await;
            searches.push(SearchDone { app_name, query, backend: r.backend.clone() });
            sources.extend(r.sources.clone());
            messages.push(json!({ "role": "assistant", "content": "", "tool_calls": [call.clone()] }));
            messages.push(json!({ "role": "tool", "tool_call_id": call["id"], "content": r.text }));
            continue;
        }
        if call["function"]["name"] == "guide" {
            crate::journal::event("route", json!({ "to": "guide", "request": question, "goal": s("goal") }));
            return Ok(QaAnswer {
                kind: "guide".into(),
                goal: s("goal"),
                answer: String::new(),
                details: Vec::new(),
                app_name: String::new(),
                target: String::new(),
                searches,
                sources,
            });
        }
        if call["function"]["name"] == "reply" {
            let details = args["details"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|d| d.as_str().map(|d| d.replace("**", "").replace('`', "").trim().to_string()))
                .filter(|d| !d.is_empty())
                .collect();
            return Ok(QaAnswer {
                kind: "answer".into(),
                goal: String::new(),
                answer: s("answer").replace("**", "").replace('`', ""),
                details,
                app_name: s("app_name"),
                target: s("target"),
                searches,
                sources,
            });
        }
        // A search past the limit: ask for the reply now.
        messages.push(json!({ "role": "assistant", "content": "", "tool_calls": [call.clone()] }));
        messages.push(json!({ "role": "tool", "tool_call_id": call["id"],
            "content": "No more searches: reply now with what you know and what is on screen." }));
    }
    Err("Holo did not answer".into())
}
