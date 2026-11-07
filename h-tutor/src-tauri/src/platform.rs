//! Client for the Rio platform (`platform/`, a Cloudflare Worker): the
//! organization's knowledge base, built from ReStep's graph of tutorials, docs
//! and community answers, re-targeted to each version of the software.
//!
//! - `search(app, query)`: proven paths for a goal, used first by the
//!   `search` tool and before planning a tutorial.
//! - `tutorials()` / `tutorial(id)`: the organization's tutorials, shown in
//!   the ⌘K palette next to the local ones (ids start with `rio:`).
//! - `apps()`: the apps the organization's knowledge covers (shared ones like
//!   Blender, and its own tools), named to Holo in the `search` tool.
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
    let from_file = dotenvy::dotenv_iter().ok().and_then(|it| it.flatten().find(|(k, _)| k == key).map(|(_, v)| v));
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

/// A search can wake the knowledge worker (measured 3.6 s cold, 0.14 s warm);
/// past the client's 10 s default it was silently lost.
const SEARCH_TIMEOUT: Duration = Duration::from_secs(25);

async fn get(path: &str, query: &[(&str, &str)]) -> Result<Value, String> {
    let (base, token) = config().ok_or("Rio platform not configured (RIO_API_URL, RIO_API_TOKEN)")?;
    let mut req = HTTP.get(format!("{base}{path}")).bearer_auth(token).query(query);
    if path == "/v1/search" {
        req = req.timeout(SEARCH_TIMEOUT);
    }
    let r = req.send().await.map_err(|e| format!("Rio platform unreachable: {e}"))?;
    let status = r.status();
    let v: Value = r.json().await.map_err(|e| format!("Rio platform: bad response ({e})"))?;
    if !status.is_success() {
        return Err(format!("Rio platform: {} ({status})", v["error"].as_str().unwrap_or("error")));
    }
    Ok(v)
}

static APPS: Mutex<Option<(Instant, Vec<String>)>> = Mutex::new(None);
const APPS_TTL: Duration = Duration::from_secs(300);

/// The apps the organization's knowledge covers: the shared ones and the tools
/// its teams added from their docs (cached five minutes; the last list if offline).
pub async fn apps() -> Vec<String> {
    if !enabled() {
        return Vec::new();
    }
    if let Some((at, list)) = APPS.lock().unwrap().as_ref()
        && at.elapsed() < APPS_TTL
    {
        return list.clone();
    }
    match get("/v1/apps", &[]).await {
        Ok(v) => {
            let list: Vec<String> = v["apps"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|a| a["name"].as_str().map(String::from))
                .collect();
            *APPS.lock().unwrap() = Some((Instant::now(), list.clone()));
            list
        }
        Err(e) => {
            eprintln!("[platform] {e}");
            known_apps()
        }
    }
}

/// The last list `apps()` fetched, without waiting (for the search tool's description).
pub fn known_apps() -> Vec<String> {
    APPS.lock().unwrap().as_ref().map(|(_, l)| l.clone()).unwrap_or_default()
}

/// Web browsers: an internal tool often runs in one, so the browser's name says nothing about the tool.
const BROWSERS: [&str; 8] = ["chrome", "chromium", "safari", "firefox", "arc", "edge", "brave", "opera"];

/// The `app` filter for a search, given what Holo or the tutorial named:
/// - one of the organization's apps (any case, with a version): itself;
/// - nothing, or a web browser: "" (every app the organization sees);
/// - another app: `None`, the knowledge base has nothing on it (Blender's answers must not come back for Figma).
fn scope(app_name: &str, apps: &[String]) -> Option<String> {
    let a = app_name.trim().to_lowercase();
    if a.is_empty() {
        return Some(String::new());
    }
    let known = apps.iter().map(|n| n.to_lowercase()).any(|n| a.contains(&n) || (a.len() > 2 && n.contains(&a)));
    if known || apps.is_empty() {
        // Unknown list (offline, or not fetched yet): the platform decides.
        return Some(app_name.trim().to_string());
    }
    if a.split(|c: char| !c.is_alphanumeric()).any(|w| BROWSERS.contains(&w)) {
        return Some(String::new());
    }
    None
}

/// Wakes the platform and its knowledge worker at startup, so the learner's
/// first request does not pay the cold start.
pub async fn warm_up() {
    if !enabled() {
        return;
    }
    let started = Instant::now();
    let apps = apps().await;
    let r = search("", "warm up").await;
    eprintln!(
        "[platform] warm-up: {} apps, search {} in {} ms",
        apps.len(),
        if r.is_ok() { "ok" } else { "failed" },
        started.elapsed().as_millis()
    );
}

/// Smallest meaning similarity (cosine, 0..1) for a result to count.
/// Measured on 16 milestone goals (Blender, DaVinci Resolve): 0.54 keeps
/// "Add edge loops" for "Add loop cuts" (0.549) and drops off-topic hits
/// such as "Set Bevel Segments" (0.39) or a constraint for "Apply a
/// material" (0.526).
const MIN_COSINE: f64 = 0.54;

/// A question in another language than the (English) docs: words rarely
/// match, and meaning is a little lower. Measured in French: "faire une
/// coupe en boucle" → "Add edge loops" at 0.469 with words; "supprimer les
/// sommets en double" → "Remove duplicate vertices" at 0.576 without.
const FOREIGN_MIN_COSINE: f64 = 0.55;
const FOREIGN_MIN_COSINE_WITH_WORDS: f64 = 0.45;

/// Same hint as the platform: non-ASCII letters or common French words.
fn looks_foreign(q: &str) -> bool {
    const HINTS: [&str; 24] = [
        "comment",
        "pour",
        "les",
        "des",
        "une",
        "mon",
        "mes",
        "dans",
        "faire",
        "veux",
        "est",
        "que",
        "sur",
        "avec",
        "supprimer",
        "ajouter",
        "couper",
        "mettre",
        "trouver",
        "quoi",
        "créer",
        "creer",
        "aide",
        "rendre",
    ];
    !q.is_ascii() || q.to_lowercase().split(|c: char| !c.is_alphabetic()).any(|w| HINTS.contains(&w))
}

/// Keeps only real matches. In English: the query's words are found AND the
/// meaning is close (meaning alone let "Make the tree more realistic" bring
/// back "Enable Realize Instances"). In another language: close meaning, or
/// words with a fair meaning. Without vectors (no cosine anywhere), the best
/// word match alone is kept.
fn relevant<'a>(results: &'a [Value], query: &str) -> Vec<&'a Value> {
    let words = |r: &Value| r["match"]["words"].as_bool() == Some(true);
    let cos = |r: &Value| r["match"]["cos"].as_f64();
    if results.iter().all(|r| cos(r).is_none()) {
        return results.iter().filter(|r| words(r)).take(1).collect();
    }
    let foreign = looks_foreign(query);
    results
        .iter()
        .filter(|r| match (foreign, cos(r)) {
            (_, None) => false,
            (false, Some(c)) => words(r) && c >= MIN_COSINE,
            (true, Some(c)) => c >= FOREIGN_MIN_COSINE || (words(r) && c >= FOREIGN_MIN_COSINE_WITH_WORDS),
        })
        .collect()
}

/// The organization's knowledge for a goal, as text for Holo. `Ok(None)`
/// when the platform is not configured or has nothing on it.
pub async fn search(app_name: &str, query: &str) -> Result<Option<SearchResult>, String> {
    lookup(app_name, query).await.map(|o| o.map(|(r, _)| r))
}

/// Like `search`, with the matched skills' names (for the journal).
pub async fn lookup(app_name: &str, query: &str) -> Result<Option<(SearchResult, Vec<String>)>, String> {
    if !enabled() {
        return Ok(None);
    }
    let Some(app) = scope(app_name, &apps().await) else {
        return Ok(None);
    };
    let v = match get("/v1/search", &[("q", query), ("app", &app), ("limit", "3")]).await {
        // An app the organization cannot see (the list changed since it was fetched): nothing on it.
        Err(e) if e.ends_with("(404 Not Found)") => return Ok(None),
        r => r?,
    };
    let all = v["results"].as_array().cloned().unwrap_or_default();
    let results = relevant(&all, query);
    if results.is_empty() {
        return Ok(None);
    }
    let matches: Vec<String> = results.iter().map(|r| s(&r["intent"]).to_string()).collect();
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
            // The shortcut the docs give, when the instruction does not already say it.
            if let Some(k) = st["keys"].as_array().and_then(|k| k.first()).and_then(|k| k.as_str())
                && !s(&st["do"]).contains(k)
            {
                text += &format!(" (shortcut {k})");
            }
            if st["changed"].as_bool().unwrap_or(false)
                && let (Some(l), Some(v)) = (st["was"]["label"].as_str(), st["was"]["version"].as_str())
            {
                text += &format!(" (changed: it was \"{l}\" in {v})");
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
    Ok(Some((SearchResult { backend: "rio".into(), text, sources }, matches)))
}

/// Reports a tutorial event to the organization's usage page (fire and
/// forget; nothing when the platform is not configured).
pub fn event(kind: &'static str, tutorial: &Tutorial, milestone: Option<&str>) {
    // Unit tests drive sessions through milestones: never report them.
    if cfg!(test) {
        return;
    }
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
    if let Some((at, list)) = TUTORIALS.lock().unwrap().as_ref()
        && at.elapsed() < Duration::from_secs(60)
    {
        return list.clone();
    }
    match get("/v1/tutorials", &[])
        .await
        .and_then(|v| serde_json::from_value::<Vec<Summary>>(v["tutorials"].clone()).map_err(|e| e.to_string()))
    {
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
    fn hit(intent: &str, words: bool, cos: Option<f64>) -> serde_json::Value {
        serde_json::json!({ "intent": intent, "match": { "words": words, "cos": cos } })
    }

    /// Cases measured on the local knowledge base (see `MIN_COSINE`).
    #[test]
    fn keeps_only_real_matches() {
        let names = |v: Vec<&serde_json::Value>| {
            v.iter().map(|r| r["intent"].as_str().unwrap().to_string()).collect::<Vec<_>>()
        };
        let loop_cuts = [
            hit("Add edge loops", true, Some(0.549)),
            hit("Set Bevel Segments", true, Some(0.39)),
            hit("Change Bevel Segments", true, Some(0.392)),
        ];
        assert_eq!(names(super::relevant(&loop_cuts, "Add loop cuts to the cylinder")), ["Add edge loops"]);
        let tree = [
            hit("Enable Realize Instances", false, Some(0.443)),
            hit("Shade object auto smooth", false, Some(0.441)),
            hit("Make Duplicate Real", false, Some(0.425)),
        ];
        assert!(super::relevant(&tree, "Make the tree more realistic").is_empty());
        let material =
            [hit("Change object color", true, Some(0.579)), hit("Apply the result of a constraint", true, Some(0.526))];
        assert_eq!(names(super::relevant(&material, "Apply a material to the object")), ["Change object color"]);
        // No vectors: the best word match only.
        let plain = [hit("Scale an object", true, None), hit("Apply Scale", true, None)];
        assert_eq!(names(super::relevant(&plain, "Scale the object")), ["Scale an object"]);
        // French, measured: the right skill stays, the off-topic one goes.
        let coupe = [hit("Add edge loops", true, Some(0.469)), hit("Enable or disable clip", true, Some(0.40))];
        assert_eq!(names(super::relevant(&coupe, "faire une coupe en boucle")), ["Add edge loops"]);
        let doubles = [hit("Remove duplicate vertices", false, Some(0.576))];
        assert_eq!(
            names(super::relevant(&doubles, "comment supprimer les sommets en double")),
            ["Remove duplicate vertices"]
        );
        let arbre =
            [hit("Set collection to indirect only", true, None), hit("Enable Realize Instances", false, Some(0.502))];
        assert!(super::relevant(&arbre, "aide moi à rendre l'arbre plus réaliste").is_empty());
    }

    /// Retrieval quality on milestone-like goals, against a running platform:
    /// `cargo test --lib platform::tests::retrieval_quality -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn retrieval_quality() {
        let _ = dotenvy::from_path(concat!(env!("CARGO_MANIFEST_DIR"), "/../.env"));
        // (app, goal, expected skill words, or "" when nothing relevant exists)
        let cases = [
            ("Blender", "Add loop cuts to the cylinder", "edge loop"),
            ("Blender", "Add subdivision surface modifier", "subdivision"),
            ("Blender", "Remove duplicate vertices", "duplicate"),
            ("Blender", "Scale the object", "scale"),
            ("Blender", "Rotate the cube 90 degrees", "rotate"),
            ("Blender", "Bevel the edges", "bevel"),
            ("Blender", "Extrude the top face", "extrude"),
            ("DaVinci Resolve", "Split the clip at the playhead", "split"),
            ("DaVinci Resolve", "Add a transition between clips", "transition"),
            ("DaVinci Resolve", "Export the video for YouTube", "export"),
            ("Blender", "Make the tree more realistic", ""),
            ("Blender", "Deform the cylinder into a tree shape", ""),
            ("Blender", "Apply bark texture", ""),
            ("Blender", "Add a torus", ""),
            // The learner's own words (the planner's lookup).
            ("Blender", "comment supprimer les sommets en double", "duplicate"),
            ("Blender", "faire une coupe en boucle", "edge loop"),
            ("DaVinci Resolve", "couper le clip à la tête de lecture", "cut"),
            ("", "aide moi à rendre l'arbre plus réaliste", ""),
            ("Blender", "ajouter un tore", ""),
        ];
        let (mut right, mut wrong) = (0, 0);
        tauri::async_runtime::block_on(async {
            for (app, goal, expected) in cases {
                let found = super::lookup(app, goal).await.unwrap().map(|(_, m)| m).unwrap_or_default();
                let ok = if expected.is_empty() {
                    found.is_empty()
                } else {
                    found.first().is_some_and(|m| m.to_lowercase().contains(expected))
                };
                if ok {
                    right += 1
                } else {
                    wrong += 1
                }
                println!("{} {app}: {goal} → {found:?}", if ok { "OK  " } else { "MISS" });
            }
        });
        println!("{right}/{} right", right + wrong);
        assert!(wrong <= 2, "{wrong} misses");
    }

    #[test]
    fn scopes_a_search_to_the_organizations_apps() {
        let apps = ["Blender".to_string(), "DaVinci Resolve".to_string(), "Facturo".to_string()];
        let scope = |a: &str| super::scope(a, &apps);
        assert_eq!(scope("Blender 4.2"), Some("Blender 4.2".into()));
        assert_eq!(scope("facturo"), Some("facturo".into()));
        assert_eq!(scope("davinci"), Some("davinci".into()));
        // An internal tool in a browser: every app the organization sees.
        assert_eq!(scope("Google Chrome"), Some(String::new()));
        assert_eq!(scope("Safari"), Some(String::new()));
        assert_eq!(scope(""), Some(String::new()));
        // Not in the knowledge base: Blender's answers must not come back for Figma.
        assert_eq!(scope("Figma"), None);
        // The list is not known yet: the platform decides.
        assert_eq!(super::scope("Figma", &[]), Some("Figma".into()));
    }

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

    /// An internal tool in a browser (needs a running platform where the organization has a tool "Facturo"):
    /// `cargo test --lib platform::tests::finds_a_web_tool -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn finds_a_web_tool() {
        tauri::async_runtime::block_on(async {
            let apps = super::apps().await;
            println!("apps: {apps:?}");
            assert!(apps.iter().any(|a| a == "Facturo"));
            let tool = crate::search::tool();
            println!("search tool: {}", tool["function"]["description"]);
            assert!(tool["function"]["description"].as_str().unwrap().contains("Facturo"));
            for app in ["Facturo", "Google Chrome"] {
                let r = super::search(app, "rembourser une commande").await.unwrap().expect("Facturo's docs answer");
                println!("--- {app}\n{}", r.text);
                assert!(r.text.contains("Facturo"));
            }
            assert!(super::search("Figma", "rembourser une commande").await.unwrap().is_none());
        });
    }

    /// What Holo gets from an internal tool's docs ingested on the platform (needs a running platform):
    /// `cargo test --lib platform::tests::finds_internal_docs -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn finds_internal_docs() {
        tauri::async_runtime::block_on(async {
            for (app, q) in
                [("Comptoir", "how do I refund an order"), ("", "comment marquer une commande comme expédiée")]
            {
                let r = super::search(app, q).await.unwrap().expect("the organization's docs answer");
                println!("--- {app:?} {q:?}\n{}", r.text);
                assert!(r.text.contains("Comptoir"));
            }
        });
    }

    #[test]
    fn encodes_ids() {
        assert_eq!(super::urlencode("rio:blender:t_yt_a"), "rio%3Ablender%3At_yt_a");
    }
}
