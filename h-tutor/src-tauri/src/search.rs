//! `search(app_name, query)`: up-to-date information about a piece of
//! software (where a feature lives in the current version, shortcuts,
//! changes between versions), callable by Holo as a tool.
//!
//! Backends, in order:
//! - The organization's knowledge base on the Rio platform, when
//!   `RIO_API_URL` and `RIO_API_TOKEN` are set (see platform.rs).
//! - Linkup web search, when `LINKUP_API_KEY` is set (real, sourced).
//! - Otherwise a simulated search: Holo answers as a documentation search
//!   engine from its own knowledge. Results are labelled as simulated so
//!   nobody mistakes them for live sources.

use crate::holo::{self, Holo};
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::HashMap;
use std::sync::{LazyLock, Mutex};
use std::time::{Duration, Instant};

/// One HTTP client for every Linkup call (keeps connections warm).
static HTTP: LazyLock<reqwest::Client> = LazyLock::new(reqwest::Client::new);

/// Documentation answers rarely change within a session (est.).
const CACHE_TTL: Duration = Duration::from_secs(3600);
const CACHE_MAX: usize = 200;

/// Recent results by normalized "app|query".
static CACHE: LazyLock<Mutex<HashMap<String, (Instant, SearchResult)>>> = LazyLock::new(Default::default);

fn cache_key(app_name: &str, query: &str) -> String {
    let norm = |s: &str| s.split_whitespace().collect::<Vec<_>>().join(" ").to_lowercase();
    format!("{}|{}", norm(app_name), norm(query))
}

fn cached(key: &str, now: Instant) -> Option<SearchResult> {
    let cache = CACHE.lock().unwrap();
    cache.get(key).filter(|(at, _)| now.duration_since(*at) < CACHE_TTL).map(|(_, r)| r.clone())
}

fn remember(key: String, r: &SearchResult, now: Instant) {
    let mut cache = CACHE.lock().unwrap();
    cache.retain(|_, (at, _)| now.duration_since(*at) < CACHE_TTL);
    if cache.len() >= CACHE_MAX
        && let Some(oldest) = cache.iter().min_by_key(|(_, (at, _))| *at).map(|(k, _)| k.clone())
    {
        cache.remove(&oldest);
    }
    cache.insert(key, (now, r.clone()));
}

#[derive(Serialize, Clone, Debug)]
pub struct Source {
    pub title: String,
    pub url: String,
}

#[derive(Serialize, Clone, Debug)]
pub struct SearchResult {
    /// "rio", "linkup", "simulated", or "unavailable" (not cached)
    pub backend: String,
    /// Text handed to Holo as the tool result.
    pub text: String,
    pub sources: Vec<Source>,
}

/// Runs the search (cached per app and query), falling back to the
/// simulated backend if the others fail. Failures are never cached.
pub async fn run(holo: &Holo, app_name: &str, query: &str) -> SearchResult {
    let key = cache_key(app_name, query);
    if let Some(r) = cached(&key, Instant::now()) {
        crate::journal::event("search_cached", json!({ "app": app_name, "query": query, "backend": r.backend }));
        return r;
    }
    let r = search(holo, app_name, query).await;
    if r.backend != "unavailable" {
        remember(key, &r, Instant::now());
    }
    r
}

async fn search(holo: &Holo, app_name: &str, query: &str) -> SearchResult {
    match crate::platform::search(app_name, query).await {
        Ok(Some(r)) => return log(app_name, query, r),
        Ok(None) => {}
        Err(e) => eprintln!("[search] {e}, using the other backends"),
    }
    if let Some(key) = std::env::var("LINKUP_API_KEY").ok().filter(|k| !k.trim().is_empty()) {
        match linkup(&key, app_name, query).await {
            Ok(r) => return log(app_name, query, r),
            Err(e) => eprintln!("[search] Linkup failed ({e}), using the simulated search"),
        }
    }
    let r = simulated(holo, app_name, query).await.unwrap_or_else(|e| SearchResult {
        backend: "unavailable".into(),
        text: format!("Search unavailable ({e}). Rely on what is visible on screen."),
        sources: Vec::new(),
    });
    log(app_name, query, r)
}

fn log(app_name: &str, query: &str, r: SearchResult) -> SearchResult {
    crate::journal::event(
        "search",
        json!({ "app": app_name, "query": query, "backend": r.backend, "chars": r.text.len(), "sources": r.sources.len() }),
    );
    r
}

/// Linkup sourced answer (https://docs.linkup.so).
async fn linkup(key: &str, app_name: &str, query: &str) -> Result<SearchResult, String> {
    let v: Value = HTTP
        .post("https://api.linkup.so/v1/search")
        .bearer_auth(key)
        .timeout(std::time::Duration::from_secs(25))
        .json(&json!({
            "q": format!("{app_name}: {query}"),
            "depth": "standard",
            "outputType": "sourcedAnswer",
        }))
        .send()
        .await
        .map_err(|e| e.to_string())?
        .error_for_status()
        .map_err(|e| e.to_string())?
        .json()
        .await
        .map_err(|e| e.to_string())?;
    let answer = v["answer"].as_str().ok_or("no answer")?.to_string();
    let sources: Vec<Source> = v["sources"]
        .as_array()
        .into_iter()
        .flatten()
        .take(5)
        .filter_map(|s| Some(Source { title: s["name"].as_str()?.to_string(), url: s["url"].as_str()?.to_string() }))
        .collect();
    let mut text = format!("Live web search for \"{app_name}: {query}\":\n{answer}");
    for s in &sources {
        text += &format!("\n- {} ({})", s.title, s.url);
    }
    Ok(SearchResult { backend: "linkup".into(), text, sources })
}

/// Holo plays a documentation search engine (no live web access).
async fn simulated(holo: &Holo, app_name: &str, query: &str) -> Result<SearchResult, String> {
    let prompt = format!(
        "You are a documentation search engine for the software \"{app_name}\". Return the 3 most relevant, \
         up-to-date results for the query below, as short numbered entries. Each entry: a title, the exact menu \
         path or shortcut, and which versions it applies to (say when it changed between versions). If you are \
         not sure about something, say so instead of guessing. No introduction, no markdown headings.\n\n\
         Query: {query}"
    );
    let body = json!({
        "model": holo::smart_model(),
        "messages": [{ "role": "user", "content": prompt }],
        "temperature": 0.2,
        "max_tokens": 700,
        "reasoning_effort": "none",
    });
    let (msg, _) = holo.chat(&body).await?;
    let results = msg["content"].as_str().unwrap_or("").trim().to_string();
    if results.is_empty() {
        return Err("empty search result".into());
    }
    Ok(SearchResult {
        backend: "simulated".into(),
        text: format!(
            "[Simulated search: from the model's knowledge, not the live web; the screen wins if they disagree]\n\
             Results for \"{app_name}: {query}\":\n{results}"
        ),
        sources: Vec::new(),
    })
}

/// The tool, as declared to Holo.
pub fn tool() -> Value {
    // The tools the organization's knowledge covers, its own internal ones included: Holo cannot guess their names.
    let apps = crate::platform::known_apps();
    let covered = if apps.is_empty() {
        String::new()
    } else {
        format!(
            " The organization's knowledge base covers: {}. When the screen shows one of these tools, even inside a \
             web browser, use that name as app_name.",
            apps.join(", ")
        )
    };
    json!({ "type": "function", "function": {
        "name": "search",
        "description": format!("Search the organization's knowledge base and up-to-date documentation and tutorials about a piece of software: where a feature \
            lives in the current version, menu paths, shortcuts, changes between versions. Use it when you are \
            unsure how to do the task in this app or version, or when the known path did not work. The learner \
            does nothing during a search.{covered}"),
        "parameters": { "type": "object",
            "properties": {
                "app_name": { "type": "string", "description": "The software, with its version if visible (e.g. \"Blender 4.2\"); for a web tool, the tool's name, not the browser's" },
                "query": { "type": "string", "description": "What to find, in English, e.g. \"add a subdivision surface modifier\"" }
            },
            "required": ["app_name", "query"] }
    }})
}

#[cfg(test)]
mod tests {
    use super::*;

    fn result(text: &str) -> SearchResult {
        SearchResult { backend: "linkup".into(), text: text.into(), sources: Vec::new() }
    }

    #[test]
    fn cache_normalizes_and_expires() {
        let key = cache_key("Blender  4.2", " Add   Torus ");
        assert_eq!(key, cache_key("blender 4.2", "add torus"));
        let t0 = Instant::now();
        remember(key.clone(), &result("menu Add > Mesh > Torus"), t0);
        assert_eq!(cached(&key, t0 + Duration::from_secs(60)).unwrap().text, "menu Add > Mesh > Torus");
        assert!(cached(&key, t0 + CACHE_TTL + Duration::from_secs(1)).is_none());
    }
    /// `cargo test --lib search -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn simulated_search() {
        let _ = dotenvy::from_path(concat!(env!("CARGO_MANIFEST_DIR"), "/../.env"));
        let holo = crate::holo::Holo::new();
        let t = std::time::Instant::now();
        let r = tauri::async_runtime::block_on(super::run(&holo, "Blender 4.2", "add a subdivision surface modifier"));
        println!("[{}] in {:.1}s\n{}", r.backend, t.elapsed().as_secs_f32(), r.text);
        assert!(r.text.len() > 50);
    }
}
