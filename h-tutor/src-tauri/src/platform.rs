//! Client for the Rio platform (`platform/`, a Cloudflare Worker): the
//! organization's knowledge base, built from ReStep's graph of tutorials, docs
//! and community answers, re-targeted to each version of the software.
//!
//! - `search(app, query)`: proven paths for a goal, used first by the
//!   `search` tool and before planning a tutorial.
//! - `tutorials()` / `tutorial(id)`: the organization's tutorials, shown in
//!   the ⌘K palette next to the local ones (ids start with `rio:`).
//!
//! Configured with `RIO_API_URL` and `RIO_API_TOKEN`; without them Rio works
//! as before, from its local library and its other search backends.

use crate::search::{SearchResult, Source};
use crate::tutorial::{Summary, Tutorial};
use serde_json::Value;
use std::sync::{LazyLock, Mutex};
use std::time::{Duration, Instant};

pub const ID_PREFIX: &str = "rio:";

static HTTP: LazyLock<reqwest::Client> = LazyLock::new(|| {
    reqwest::Client::builder()
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(10))
        .build()
        .expect("http client")
});

/// A setting from `.env`, read fresh each time (a new token works without
/// restarting Rio), else from the environment.
fn setting(key: &str) -> Option<String> {
    let from_file = dotenvy::dotenv_iter()
        .ok()
        .and_then(|it| it.flatten().find(|(k, _)| k == key).map(|(_, v)| v));
    from_file.or_else(|| std::env::var(key).ok()).filter(|v| !v.trim().is_empty())
}

fn config() -> Option<(String, String)> {
    let url = setting("RIO_API_URL")?;
    let token = setting("RIO_API_TOKEN")?;
    Some((url.trim().trim_end_matches('/').to_string(), token.trim().to_string()))
}

pub fn enabled() -> bool {
    config().is_some()
}

async fn get(path: &str, query: &[(&str, &str)]) -> Result<Value, String> {
    let (base, token) = config().ok_or("Rio platform not configured (RIO_API_URL, RIO_API_TOKEN)")?;
    let r = HTTP
        .get(format!("{base}{path}"))
        .bearer_auth(token)
        .query(query)
        .send()
        .await
        .map_err(|e| format!("Rio platform unreachable: {e}"))?;
    let status = r.status();
    let v: Value = r.json().await.map_err(|e| format!("Rio platform: bad response ({e})"))?;
    if !status.is_success() {
        return Err(format!("Rio platform: {} ({status})", v["error"].as_str().unwrap_or("error")));
    }
    Ok(v)
}

/// The organization's knowledge for a goal, as text for Holo. `Ok(None)`
/// when the platform is not configured or has nothing on it.
pub async fn search(app_name: &str, query: &str) -> Result<Option<SearchResult>, String> {
    if !enabled() {
        return Ok(None);
    }
    let v = get("/v1/search", &[("q", query), ("app", app_name), ("limit", "3")]).await?;
    let results = v["results"].as_array().cloned().unwrap_or_default();
    // Weak matches share a word or two with the query: noise for Holo.
    let results: Vec<&Value> = results.iter().filter(|r| r["score"].as_f64().unwrap_or(0.0) >= 2.0).collect();
    if results.is_empty() {
        return Ok(None);
    }
    let mut text = format!(
        "Organization knowledge base (Rio platform) for \"{app_name}: {query}\". These paths come from the \
         organization's tutorials and docs, re-targeted to the learner's version. Prefer them over your own \
         knowledge; the screen wins if they disagree.\n"
    );
    let mut sources = Vec::new();
    for (i, r) in results.iter().enumerate() {
        let ver = &r["version"];
        let served = ver["id"].as_str().unwrap_or("?");
        let note = match (ver["requested"].as_str(), ver["exact"].as_bool().unwrap_or(false)) {
            (Some(req), false) => format!(" (learner has {req}; closest version covered)"),
            _ => String::new(),
        };
        let proof = match r["proof"].as_str() {
            Some("PASS") => format!(", proven on {served}"),
            Some("FAIL") => format!(", failed when tested on {served}"),
            _ => String::new(),
        };
        // Platform-made tutorials are not tied to a version ("any").
        let version = if served == "any" { String::new() } else { format!(" {served}") };
        text += &format!("\n{}. \"{}\" in {}{version}{note}{proof}:\n", i + 1, s(&r["intent"]), s(&r["app_name"]));
        for st in r["steps"].as_array().into_iter().flatten() {
            if st["missing"].as_bool().unwrap_or(false) {
                continue;
            }
            text += &format!("   - {}", s(&st["do"]));
            if st["changed"].as_bool().unwrap_or(false) {
                if let (Some(l), Some(v)) = (st["was"]["label"].as_str(), st["was"]["version"].as_str()) {
                    text += &format!(" (changed: it was \"{l}\" in {v})");
                }
            }
            text.push('\n');
        }
        for src in r["sources"].as_array().into_iter().flatten().take(2) {
            if let (Some(title), Some(url)) = (src["title"].as_str(), src["url"].as_str()) {
                sources.push(Source { title: title.into(), url: url.into() });
            }
        }
    }
    sources.dedup_by(|a, b| a.url == b.url);
    Ok(Some(SearchResult { backend: "rio".into(), text, sources }))
}

/// Reports a tutorial event to the organization's usage page (fire and
/// forget; nothing when the platform is not configured).
pub fn event(kind: &'static str, tutorial: &Tutorial, milestone: Option<&str>) {
    let Some((base, token)) = config() else { return };
    let body = serde_json::json!({
        "kind": kind,
        "tutorial_id": tutorial.id,
        "tutorial_title": tutorial.title,
        "milestone": milestone,
        "goal": tutorial.goal,
        "app": tutorial.app.name,
    });
    tauri::async_runtime::spawn(async move {
        if let Err(e) = HTTP.post(format!("{base}/v1/events")).bearer_auth(token).json(&body).send().await {
            eprintln!("[platform] event: {e}");
        }
    });
}

fn s(v: &Value) -> &str {
    v.as_str().unwrap_or("")
}

static TUTORIALS: Mutex<Option<(Instant, Vec<Summary>)>> = Mutex::new(None);

/// The organization's tutorials (cached a minute; the last list if offline).
pub async fn tutorials() -> Vec<Summary> {
    if !enabled() {
        return Vec::new();
    }
    if let Some((at, list)) = TUTORIALS.lock().unwrap().as_ref() {
        if at.elapsed() < Duration::from_secs(60) {
            return list.clone();
        }
    }
    match get("/v1/tutorials", &[]).await.and_then(|v| {
        serde_json::from_value::<Vec<Summary>>(v["tutorials"].clone()).map_err(|e| e.to_string())
    }) {
        Ok(list) => {
            *TUTORIALS.lock().unwrap() = Some((Instant::now(), list.clone()));
            list
        }
        Err(e) => {
            eprintln!("[platform] {e}");
            TUTORIALS.lock().unwrap().as_ref().map(|(_, l)| l.clone()).unwrap_or_default()
        }
    }
}

/// A platform tutorial in Rio's format, its hints for the installed version.
pub async fn tutorial(id: &str) -> Result<Tutorial, String> {
    let bundle_id = TUTORIALS
        .lock()
        .unwrap()
        .as_ref()
        .and_then(|(_, l)| l.iter().find(|t| t.id == id).and_then(|t| t.bundle_id.clone()));
    let version = match bundle_id {
        Some(b) => tauri::async_runtime::spawn_blocking(move || installed_version(&b)).await.ok().flatten(),
        None => None,
    };
    let v = get(&format!("/v1/tutorials/{}", urlencode(id)), &[("version", version.as_deref().unwrap_or(""))]).await?;
    let t: Tutorial = serde_json::from_value(v).map_err(|e| format!("{id}: invalid tutorial ({e})"))?;
    t.validate()?;
    Ok(t)
}

fn urlencode(s: &str) -> String {
    s.bytes()
        .map(|b| match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => (b as char).to_string(),
            _ => format!("%{b:02X}"),
        })
        .collect()
}

/// The installed version of an app (CFBundleShortVersionString), from its bundle id.
pub fn installed_version(bundle_id: &str) -> Option<String> {
    use std::process::Command;
    let out = Command::new("mdfind").arg(format!("kMDItemCFBundleIdentifier == '{bundle_id}'")).output().ok()?;
    let app = String::from_utf8_lossy(&out.stdout).lines().find(|l| l.ends_with(".app"))?.to_string();
    let out = Command::new("defaults")
        .args(["read", &format!("{app}/Contents/Info"), "CFBundleShortVersionString"])
        .output()
        .ok()?;
    let v = String::from_utf8_lossy(&out.stdout).trim().to_string();
    (!v.is_empty()).then_some(v)
}

#[cfg(test)]
mod tests {
    #[test]
    fn reads_an_installed_version() {
        // Finder is always installed.
        let v = super::installed_version("com.apple.finder");
        println!("Finder {v:?}");
        assert!(v.is_some_and(|v| v.chars().next().is_some_and(|c| c.is_ascii_digit())));
    }

    /// Against a running platform (local `wrangler dev` or deployed):
    /// `RIO_API_URL=… RIO_API_TOKEN=… cargo test --lib platform -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn talks_to_the_platform() {
        tauri::async_runtime::block_on(async {
            let r = super::search("Blender 4.2", "remove doubles").await.unwrap().expect("a match");
            println!("{}\nsources: {:?}", r.text, r.sources);
            assert_eq!(r.backend, "rio");
            assert!(super::search("Figma", "remove doubles").await.unwrap().is_none());
            let list = super::tutorials().await;
            println!("{} tutorials: {:?}", list.len(), list.iter().map(|t| &t.id).collect::<Vec<_>>());
            let t = super::tutorial(&list[0].id).await.unwrap();
            println!("{}: {} milestones, first hints {:?}", t.title, t.milestones.len(), t.milestones[0].hints);
            assert!(!t.milestones.is_empty());
        });
    }

    #[test]
    fn encodes_ids() {
        assert_eq!(super::urlencode("rio:blender:t_yt_a"), "rio%3Ablender%3At_yt_a");
    }
}
