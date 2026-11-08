//! Thin client for H Company's Models API (OpenAI-compatible, Holo models).

use serde::de::DeserializeOwned;
use serde_json::{Value, json};

pub struct Holo {
    http: reqwest::Client,
    /// No connection reuse: hedged copies must not share a stalled
    /// connection with the request they back up.
    fresh: reqwest::Client,
}

/// Why a streamed request failed: over quota (with the server's wait), or
/// anything else.
#[derive(Debug)]
enum Failure {
    RateLimited(Option<std::time::Duration>),
    Other(String),
}

impl From<String> for Failure {
    fn from(e: String) -> Self {
        Failure::Other(e)
    }
}

impl std::fmt::Display for Failure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Failure::RateLimited(_) => write!(f, "Holo 429 Too Many Requests (rate limit)"),
            Failure::Other(e) => f.write_str(e),
        }
    }
}

/// Streamed attempts on fresh connections before a step fails (the
/// simulator saw a stream stay silent twice in a row).
const STREAM_ATTEMPTS: u32 = 3;

/// Waits honored on a 429 before giving up (the account's tier allows a
/// fixed number of requests per minute: 30 on tier 1 for holo4-27b).
const RATE_LIMIT_RETRIES: u32 = 4;
const RATE_LIMIT_WAIT: std::time::Duration = std::time::Duration::from_secs(5);
const RATE_LIMIT_WAIT_MAX: std::time::Duration = std::time::Duration::from_secs(20);

/// Shown in the bar while Holo is retried or hedged, so a slow answer is
/// never silent.
const SLOW: &str = "Holo is slow to answer, trying again…";
/// A stream with no data at all for this long is abandoned and retried on
/// a fresh connection (est.: the server's first byte usually comes in ~1.5 s,
/// and the simulator saw ~7 % of streams stall for good).
const STALL_FIRST: std::time::Duration = std::time::Duration::from_secs(10);
/// Once tokens flow they come every fraction of a second; a gap this long
/// means the stream is stuck (est.).
const STALL_GAP: std::time::Duration = std::time::Duration::from_secs(12);

fn env_or(key: &str, default: &str) -> String {
    std::env::var(key).ok().filter(|v| !v.trim().is_empty()).unwrap_or_else(|| default.to_string())
}

pub fn api_key() -> Option<String> {
    std::env::var("HAI_API_KEY").ok().filter(|k| !k.trim().is_empty())
}

/// Model used for grounding and step checks (latency matters most).
pub fn fast_model() -> String {
    env_or("HOLO_FAST_MODEL", "holo4-35b-a3b")
}

/// Model used to turn a goal or a pasted tutorial into steps.
pub fn smart_model() -> String {
    env_or("HOLO_SMART_MODEL", "holo4-27b")
}

impl Holo {
    pub fn new() -> Self {
        Self {
            http: reqwest::Client::builder()
                .connect_timeout(std::time::Duration::from_secs(10))
                .build()
                .expect("HTTP client"),
            fresh: reqwest::Client::builder()
                .connect_timeout(std::time::Duration::from_secs(10))
                .pool_max_idle_per_host(0)
                .build()
                .expect("HTTP client"),
        }
    }

    /// Posts a chat completion, retrying what H's error guide marks as
    /// transient (a stalled request or reset connection, 408, 429 and 5xx)
    /// with backoff, honoring `Retry-After`. Other API errors (bad key,
    /// credits, bad request) are returned at once. Returns the status, the
    /// body and the total latency in ms.
    async fn post(&self, body: &Value) -> Result<(reqwest::StatusCode, String, u128), String> {
        const ATTEMPTS: usize = 2;
        let started = std::time::Instant::now();
        let key = api_key().ok_or("HAI_API_KEY is missing: add it to the .env file")?;
        let base = env_or("HAI_BASE_URL", "https://api.hcompany.ai/v1");
        let url = format!("{}/chat/completions", base.trim_end_matches('/'));
        let mut last = String::new();
        for attempt in 1..=ATTEMPTS {
            let (result, retry_after) = match self.hedged(&url, &key, body).await {
                Ok((status, text, retry_after)) => (Ok((status, text)), retry_after),
                Err(e) => (Err(e), None),
            };
            match result {
                Ok((status, text))
                    if !(status.as_u16() == 408 || status.as_u16() == 429 || status.is_server_error()) =>
                {
                    return Ok((status, text, started.elapsed().as_millis()));
                }
                Ok((status, text)) => {
                    let detail: String = text.chars().take(160).collect();
                    last = format!("{status} {detail}");
                    // Last attempt: hand the API error back as is.
                    if attempt == ATTEMPTS {
                        return Ok((status, text, started.elapsed().as_millis()));
                    }
                }
                Err(e) => last = e,
            }
            eprintln!("[holo] attempt {attempt}/{ATTEMPTS} failed: {last}");
            crate::journal::event("holo_retry", json!({ "attempt": attempt, "error": last }));
            if attempt < ATTEMPTS {
                let wait = retry_after.map(|s| s.min(20) * 1000).unwrap_or(800 * 2u64.pow(attempt as u32 - 1));
                tokio::time::sleep(std::time::Duration::from_millis(wait)).await;
            }
        }
        Err(format!("Can't reach Holo after {ATTEMPTS} attempts: {last}"))
    }

    /// One request, backed up by copies on fresh connections if it has not
    /// answered after 10 s, then 20 s (H's API occasionally leaves a request
    /// hanging while the next one answers in under a second). The first
    /// successful answer wins and the others are dropped, which cancels them;
    /// a failed copy does not end the race while others are still running.
    async fn hedged(
        &self,
        url: &str,
        key: &str,
        body: &Value,
    ) -> Result<(reqwest::StatusCode, String, Option<u64>), String> {
        use futures_util::future::{Either, select};
        use futures_util::stream::{FuturesUnordered, StreamExt};
        const LAUNCH_AT_S: [u64; 3] = [0, 10, 20];
        let start = tokio::time::Instant::now();
        let mut pending = FuturesUnordered::new();
        let mut launched = 0;
        let mut last = String::from("no answer");
        loop {
            let due = launched < LAUNCH_AT_S.len()
                && (start.elapsed().as_secs() >= LAUNCH_AT_S[launched] || pending.is_empty());
            if due {
                if launched > 0 {
                    eprintln!(
                        "[holo] no answer after {:.0}s, sending a copy on a fresh connection",
                        start.elapsed().as_secs_f32()
                    );
                    crate::emit_status(SLOW);
                    crate::journal::event(
                        "holo_hedge",
                        json!({ "after_s": start.elapsed().as_secs(), "copy": launched }),
                    );
                }
                let client = if launched == 0 { &self.http } else { &self.fresh };
                pending.push(self.send_once(client, url, key, body));
                launched += 1;
                continue;
            }
            if pending.is_empty() {
                return Err(last);
            }
            let wait = LAUNCH_AT_S
                .get(launched)
                .map(|&s| std::time::Duration::from_secs(s).saturating_sub(start.elapsed()))
                .unwrap_or(std::time::Duration::from_secs(3600));
            let outcome = {
                let next = pending.next();
                let tick = Box::pin(tokio::time::sleep(wait));
                match select(next, tick).await {
                    Either::Left((r, _)) => r,
                    Either::Right(_) => continue,
                }
            };
            match outcome {
                Some(Ok(r)) => return Ok(r),
                Some(Err(e)) => last = e,
                None => {}
            }
        }
    }

    async fn send_once(
        &self,
        client: &reqwest::Client,
        url: &str,
        key: &str,
        body: &Value,
    ) -> Result<(reqwest::StatusCode, String, Option<u64>), String> {
        const TIMEOUT: std::time::Duration = std::time::Duration::from_secs(40);
        let res =
            client.post(url).bearer_auth(key).json(body).timeout(TIMEOUT).send().await.map_err(|e| describe(&e))?;
        let status = res.status();
        let retry_after = res
            .headers()
            .get(reqwest::header::RETRY_AFTER)
            .and_then(|v| v.to_str().ok())
            .and_then(|v| v.trim().parse::<u64>().ok());
        let text = res.text().await.map_err(|e| describe(&e))?;
        Ok((status, text, retry_after))
    }

    /// Raw chat completion: posts `body` as is, returns the first choice's
    /// message and the latency in ms.
    pub async fn chat(&self, body: &Value) -> Result<(Value, u128), String> {
        self.chat_usage(body).await.map(|(m, ms, _)| (m, ms))
    }

    /// A chat completion streamed as server-sent events: `on_reasoning`
    /// receives the thinking trace as it grows, so the UI can show what Holo
    /// is looking at. Returns the same message, latency and usage as
    /// `chat_usage`. The request is hedged like the others on its time to
    /// first byte; a stream that goes silent is abandoned (`STALL_FIRST`
    /// before any data, `STALL_GAP` once data flows) and retried once on a
    /// fresh connection, since the pooled one may be the one that stalled.
    pub async fn chat_stream(
        &self,
        body: &Value,
        on_reasoning: &(dyn Fn(&str) + Sync),
    ) -> Result<(Value, u128, Value), String> {
        let mut body = body.clone();
        body["stream"] = json!(true);
        body["stream_options"] = json!({ "include_usage": true });
        let key = api_key().ok_or("HAI_API_KEY is missing: add it to the .env file")?;
        let base = env_or("HAI_BASE_URL", "https://api.hcompany.ai/v1");
        let url = format!("{}/chat/completions", base.trim_end_matches('/'));
        let started = std::time::Instant::now();
        let (mut failures, mut rate_limited) = (0, 0);
        loop {
            match self.stream_once(&url, &key, &body, on_reasoning, failures > 0).await {
                Ok((message, usage)) => return Ok((message, started.elapsed().as_millis(), usage)),
                // Over the account's requests-per-minute quota: wait as told
                // and try again, instead of failing the learner's step.
                Err(Failure::RateLimited(wait)) if rate_limited < RATE_LIMIT_RETRIES => {
                    rate_limited += 1;
                    let wait = wait.unwrap_or(RATE_LIMIT_WAIT).min(RATE_LIMIT_WAIT_MAX);
                    eprintln!("[holo] rate limited, waiting {} s", wait.as_secs());
                    crate::journal::event(
                        "holo_rate_limited",
                        json!({ "wait_s": wait.as_secs(), "retry": rate_limited }),
                    );
                    crate::emit_status("Holo is busy, waiting a few seconds…");
                    tokio::time::sleep(wait).await;
                }
                Err(e) => {
                    failures += 1;
                    let e = e.to_string();
                    eprintln!("[holo] stream attempt {failures}/{STREAM_ATTEMPTS} failed: {e}");
                    crate::journal::event("holo_retry", json!({ "attempt": failures, "error": e, "stream": true }));
                    if failures == STREAM_ATTEMPTS {
                        return Err(format!("Can't reach Holo: {e}"));
                    }
                    crate::emit_status(SLOW);
                }
            }
        }
    }

    async fn stream_once(
        &self,
        url: &str,
        key: &str,
        body: &Value,
        on_reasoning: &(dyn Fn(&str) + Sync),
        fresh: bool,
    ) -> Result<(Value, Value), Failure> {
        use futures_util::StreamExt;
        let res = self.hedged_response(url, key, body, fresh).await?;
        let status = res.status();
        if status == reqwest::StatusCode::TOO_MANY_REQUESTS {
            let wait = res
                .headers()
                .get(reqwest::header::RETRY_AFTER)
                .and_then(|v| v.to_str().ok())
                .and_then(|v| v.trim().parse::<u64>().ok())
                .map(std::time::Duration::from_secs);
            return Err(Failure::RateLimited(wait));
        }
        if !status.is_success() {
            let text = res.text().await.unwrap_or_default();
            let detail: String = text.chars().take(300).collect();
            return Err(format!("Holo {status}: {detail}").into());
        }
        let mut stream = res.bytes_stream();
        let mut sse = Sse::default();
        let mut flowing = false;
        let opened = std::time::Instant::now();
        loop {
            let limit = if flowing { STALL_GAP } else { STALL_FIRST };
            let chunk = match tokio::time::timeout(limit, stream.next()).await {
                Err(_) => return Err(format!("stream stalled (no data for {} s)", limit.as_secs()).into()),
                Ok(None) => break,
                Ok(Some(Err(e))) => return Err(describe(&e).into()),
                Ok(Some(Ok(bytes))) => bytes,
            };
            if !flowing {
                // Time to first data, to calibrate STALL_FIRST on measures.
                crate::journal::event("holo_first_chunk", json!({ "ms": opened.elapsed().as_millis() }));
            }
            flowing = true;
            if sse.push(&chunk, on_reasoning) {
                break;
            }
        }
        Ok(sse.finish()?)
    }

    /// Like `hedged`, but returns the response as soon as its headers
    /// arrive (for streaming): copies on fresh connections at 10 s and 20 s.
    async fn hedged_response(
        &self,
        url: &str,
        key: &str,
        body: &Value,
        fresh: bool,
    ) -> Result<reqwest::Response, String> {
        use futures_util::future::{Either, select};
        use futures_util::stream::{FuturesUnordered, StreamExt};
        const LAUNCH_AT_S: [u64; 3] = [0, 10, 20];
        let start = tokio::time::Instant::now();
        let mut pending = FuturesUnordered::new();
        let mut launched = 0;
        let mut last = String::from("no answer");
        loop {
            let due = launched < LAUNCH_AT_S.len()
                && (start.elapsed().as_secs() >= LAUNCH_AT_S[launched] || pending.is_empty());
            if due {
                if launched > 0 {
                    eprintln!(
                        "[holo] no answer after {:.0}s, sending a copy on a fresh connection",
                        start.elapsed().as_secs_f32()
                    );
                    crate::emit_status(SLOW);
                    crate::journal::event(
                        "holo_hedge",
                        json!({ "after_s": start.elapsed().as_secs(), "copy": launched, "stream": true }),
                    );
                }
                let client = if launched == 0 && !fresh { &self.http } else { &self.fresh };
                pending.push(client.post(url).bearer_auth(key).json(body).send());
                launched += 1;
                continue;
            }
            if pending.is_empty() {
                return Err(last);
            }
            let wait = LAUNCH_AT_S
                .get(launched)
                .map(|&s| std::time::Duration::from_secs(s).saturating_sub(start.elapsed()))
                .unwrap_or(std::time::Duration::from_secs(40));
            let outcome = {
                let next = pending.next();
                let tick = Box::pin(tokio::time::sleep(wait));
                match select(next, tick).await {
                    Either::Left((r, _)) => r,
                    Either::Right(_) if launched < LAUNCH_AT_S.len() => continue,
                    Either::Right(_) => return Err("Timed out (no answer within 40 s)".into()),
                }
            };
            match outcome {
                Some(Ok(r)) => return Ok(r),
                Some(Err(e)) => last = describe(&e),
                None => {}
            }
        }
    }

    /// Same, also returning `usage` (prompt, cached and reasoning tokens).
    pub async fn chat_usage(&self, body: &Value) -> Result<(Value, u128, Value), String> {
        let (status, text, ms) = self.post(body).await?;
        if !status.is_success() {
            let detail: String = text.chars().take(300).collect();
            return Err(format!("Holo {status} : {detail}"));
        }
        let v: Value = serde_json::from_str(&text).map_err(|e| format!("Unreadable response: {e}"))?;
        let mut message = v["choices"][0]["message"].clone();
        message["finish_reason"] = v["choices"][0]["finish_reason"].clone();
        Ok((message, ms, v["usage"].clone()))
    }

    /// One chat completion constrained to `schema`, thinking off, parsed into `T`.
    pub async fn structured<T: DeserializeOwned>(
        &self,
        tag: &str,
        model: &str,
        images: &[&str],
        prompt: &str,
        schema: Value,
    ) -> Result<T, String> {
        self.structured_logged(tag, model, images, prompt, schema).await.map(|(v, _)| v)
    }

    /// Same, also returning the debug journal id of the call.
    pub async fn structured_logged<T: DeserializeOwned>(
        &self,
        tag: &str,
        model: &str,
        images: &[&str],
        prompt: &str,
        schema: Value,
    ) -> Result<(T, Option<String>), String> {
        let mut content: Vec<Value> =
            images.iter().map(|url| json!({ "type": "image_url", "image_url": { "url": url } })).collect();
        content.push(json!({ "type": "text", "text": prompt }));

        let body = json!({
            "model": model,
            "messages": [{ "role": "user", "content": content }],
            "temperature": 0.0,
            "structured_outputs": { "json": schema },
            "chat_template_kwargs": { "enable_thinking": false },
        });

        let (status, text, ms) = self.post(&body).await?;
        if !status.is_success() {
            crate::debug::record(tag, model, images, prompt, &format!("HTTP {status}: {text}"), ms);
            let hint = match status.as_u16() {
                401 | 403 => "API key refused",
                402 => "Not enough credits",
                404 => "Model not found (check HOLO_*_MODEL)",
                429 => "Rate limit reached, try again in a moment",
                _ => "Erreur API",
            };
            let detail: String = text.chars().take(240).collect();
            return Err(format!("Holo {status} : {hint}. {detail}"));
        }

        let v: Value = serde_json::from_str(&text).map_err(|e| format!("Unreadable response: {e}"))?;
        let raw = v["choices"][0]["message"]["content"].as_str().ok_or("Empty response from the model")?;
        let id = crate::debug::record(tag, model, images, prompt, raw, ms);
        let cleaned = raw.trim().trim_start_matches("```json").trim_start_matches("```").trim_end_matches("```").trim();
        serde_json::from_str(cleaned).map(|v| (v, id)).map_err(|e| format!("Unexpected JSON ({e}): {raw}"))
    }
}

/// A reqwest error with its real cause ("timed out", "connection reset"…),
/// which its own message hides behind "error sending request".
fn describe(e: &reqwest::Error) -> String {
    if e.is_timeout() {
        return "Timed out (no answer within 40 s)".into();
    }
    let mut msg = if e.is_connect() { "connexion impossible".to_string() } else { "network error".to_string() };
    let mut source = std::error::Error::source(e);
    let mut last = String::new();
    while let Some(s) = source {
        last = s.to_string();
        source = s.source();
    }
    if !last.is_empty() {
        msg += &format!(": {last}");
    }
    msg
}

/// Assembles a streamed chat completion. Bytes are buffered until a full
/// line is in, so a multibyte character split across network chunks is
/// decoded intact.
#[derive(Default)]
struct Sse {
    buf: Vec<u8>,
    reasoning: String,
    content: String,
    /// id, name, arguments
    calls: Vec<(String, String, String)>,
    finish: Value,
    usage: Value,
    done: bool,
}

impl Sse {
    /// Feeds one network chunk. Returns true once the `[DONE]` marker is in.
    fn push(&mut self, chunk: &[u8], on_reasoning: &(dyn Fn(&str) + Sync)) -> bool {
        self.buf.extend_from_slice(chunk);
        while let Some(nl) = self.buf.iter().position(|&b| b == b'\n') {
            let raw: Vec<u8> = self.buf.drain(..=nl).collect();
            let line = String::from_utf8_lossy(&raw);
            let Some(data) = line.trim().strip_prefix("data:").map(str::trim) else { continue };
            if data == "[DONE]" {
                self.done = true;
                return true;
            }
            let Ok(v) = serde_json::from_str::<Value>(data) else { continue };
            if v["usage"].is_object() {
                self.usage = v["usage"].clone();
            }
            let Some(choice) = v["choices"].get(0) else { continue };
            let delta = &choice["delta"];
            if let Some(r) = delta["reasoning"].as_str().or(delta["reasoning_content"].as_str()) {
                self.reasoning.push_str(r);
                on_reasoning(&self.reasoning);
            }
            if let Some(c) = delta["content"].as_str() {
                self.content.push_str(c);
            }
            for tc in delta["tool_calls"].as_array().into_iter().flatten() {
                let i = tc["index"].as_u64().unwrap_or(0) as usize;
                while self.calls.len() <= i {
                    self.calls.push(Default::default());
                }
                if let Some(id) = tc["id"].as_str() {
                    self.calls[i].0 = id.to_string();
                }
                if let Some(n) = tc["function"]["name"].as_str() {
                    self.calls[i].1.push_str(n);
                }
                if let Some(a) = tc["function"]["arguments"].as_str() {
                    self.calls[i].2.push_str(a);
                }
            }
            if !choice["finish_reason"].is_null() {
                self.finish = choice["finish_reason"].clone();
            }
        }
        false
    }

    /// The assembled message. A stream that ended before `[DONE]` and
    /// without a finish reason was cut: it is an error (retried), never a
    /// partial answer.
    fn finish(self) -> Result<(Value, Value), String> {
        if !self.done && self.finish.is_null() {
            return Err("stream ended before the response was complete".into());
        }
        let tool_calls: Vec<Value> = self
            .calls
            .into_iter()
            .filter(|(_, name, _)| !name.is_empty())
            .map(|(id, name, args)| json!({ "id": id, "type": "function", "function": { "name": name, "arguments": args } }))
            .collect();
        let message = json!({
            "role": "assistant",
            "content": if self.content.is_empty() { Value::Null } else { json!(self.content) },
            "reasoning": self.reasoning,
            "tool_calls": if tool_calls.is_empty() { Value::Null } else { json!(tool_calls) },
            "finish_reason": self.finish,
        });
        Ok((message, self.usage))
    }
}

#[cfg(test)]
mod tests {
    /// A 429 is reported as a rate limit with the server's wait, so the
    /// caller waits instead of failing the step.
    #[test]
    fn rate_limit_carries_the_server_wait() {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            if let Some(Ok(mut conn)) = listener.incoming().next() {
                let mut buf = [0u8; 65536];
                let _ = conn.read(&mut buf);
                let body = r#"{"error":{"code":"rate_limit_exceeded"}}"#;
                let _ = write!(
                    conn,
                    "HTTP/1.1 429 Too Many Requests\r\nRetry-After: 3\r\nContent-Type: application/json\r\n\
                     Content-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
            }
        });
        let holo = super::Holo::new();
        let r = tauri::async_runtime::block_on(holo.stream_once(
            &format!("http://127.0.0.1:{port}/v1/chat/completions"),
            "test",
            &serde_json::json!({ "model": "x" }),
            &|_| {},
            false,
        ));
        match r {
            Err(super::Failure::RateLimited(wait)) => assert_eq!(wait, Some(std::time::Duration::from_secs(3))),
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn sse_keeps_a_character_split_across_chunks() {
        let line = "data: {\"choices\":[{\"delta\":{\"content\":\"café\"},\"finish_reason\":\"stop\"}]}\n".as_bytes();
        let cut = line.iter().position(|&b| b == 0xC3).unwrap() + 1; // inside "é"
        let mut sse = super::Sse::default();
        assert!(!sse.push(&line[..cut], &|_| {}));
        assert!(!sse.push(&line[cut..], &|_| {}));
        let (msg, _) = sse.finish().unwrap();
        assert_eq!(msg["content"], "café");
    }

    #[test]
    fn sse_stops_on_done_marker() {
        let mut sse = super::Sse::default();
        let body = "data: {\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"id\":\"c1\",\"function\":{\"name\":\"answer\",\"arguments\":\"{}\"}}]},\"finish_reason\":\"tool_calls\"}]}\n\ndata: [DONE]\n\n";
        assert!(sse.push(body.as_bytes(), &|_| {}));
        let (msg, _) = sse.finish().unwrap();
        assert_eq!(msg["tool_calls"][0]["function"]["name"], "answer");
    }

    #[test]
    fn sse_cut_before_the_end_is_an_error() {
        let mut sse = super::Sse::default();
        sse.push(
            b"data: {\"choices\":[{\"delta\":{\"tool_calls\":[{\"index\":0,\"id\":\"c1\",\"function\":{\"name\":\"answer\",\"arguments\":\"{\\\"content\\\":\\\"The object is\"}}]}}]}\n",
            &|_| {},
        );
        assert!(sse.finish().is_err());
    }
    /// A real streamed agent step: live reasoning, then a parsed tool call.
    /// `cargo test --lib streams_a_step -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn streams_a_step() {
        use base64::{Engine, engine::general_purpose::STANDARD};
        let _ = dotenvy::from_path(concat!(env!("CARGO_MANIFEST_DIR"), "/../.env"));
        let shot = std::fs::read(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../sessions/1794062885-make-your-first-donut/shots/0004.jpg"
        ))
        .unwrap();
        let body = serde_json::json!({
            "model": "holo4-27b",
            "messages": [
                { "role": "user", "content": "Task: Guide the learner until this is actually done on their screen: \"Add a torus\"" },
                { "role": "user", "content": [
                    { "type": "text", "text": "<observation>\n" },
                    { "type": "image_url", "image_url": { "url": format!("data:image/jpeg;base64,{}", STANDARD.encode(shot)) } },
                    { "type": "text", "text": "\n</observation>" }
                ]}
            ],
            "tools": [{ "type": "function", "function": { "name": "click", "parameters": { "type": "object",
                "properties": { "element": { "type": "string" }, "x": { "type": "integer" }, "y": { "type": "integer" } },
                "required": ["element", "x", "y"] } } }],
            "tool_choice": "required",
            "temperature": 0.8,
            "reasoning_effort": "low",
            "max_tokens": 3072,
        });
        let updates = std::sync::Mutex::new(Vec::<(f32, usize)>::new());
        let started = std::time::Instant::now();
        let holo = super::Holo::new();
        let (msg, ms, usage) = tauri::async_runtime::block_on(holo.chat_stream(&body, &|r: &str| {
            updates.lock().unwrap().push((started.elapsed().as_secs_f32(), r.len()));
        }))
        .unwrap();
        let u = updates.lock().unwrap();
        println!(
            "{} reasoning updates, first at {:.2}s, done at {ms} ms",
            u.len(),
            u.first().map(|x| x.0).unwrap_or(0.0)
        );
        println!("reasoning: {}", msg["reasoning"].as_str().unwrap_or("").chars().take(160).collect::<String>());
        println!("tool call: {}", msg["tool_calls"][0]["function"]);
        println!("usage: {usage}");
        assert_eq!(msg["tool_calls"][0]["function"]["name"], "click");
        let args: serde_json::Value =
            serde_json::from_str(msg["tool_calls"][0]["function"]["arguments"].as_str().unwrap()).unwrap();
        assert!(args["x"].is_number());
    }

    /// A server that hangs on its first connection and answers the next
    /// ones: the hedged copy (fresh connection, after 10 s) must win.
    #[test]
    fn hedged_copy_rescues_a_hanging_request() {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = listener.local_addr().unwrap().port();
        std::thread::spawn(move || {
            let mut held = Vec::new();
            for (i, conn) in listener.incoming().enumerate() {
                let mut conn = conn.unwrap();
                if i == 0 {
                    held.push(conn); // never answer
                    continue;
                }
                let mut buf = [0u8; 65536];
                let _ = conn.read(&mut buf);
                let body = r#"{"choices":[{"message":{"content":"hi"},"finish_reason":"stop"}],"usage":{}}"#;
                let _ = write!(
                    conn,
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
            }
        });
        let holo = super::Holo::new();
        let started = std::time::Instant::now();
        let r = tauri::async_runtime::block_on(holo.hedged(
            &format!("http://127.0.0.1:{port}/v1/chat/completions"),
            "test",
            &serde_json::json!({ "model": "x" }),
        ));
        let took = started.elapsed().as_secs_f32();
        println!("hedged answer after {took:.1}s: {:?}", r.as_ref().map(|(s, _, _)| *s));
        assert!(r.is_ok() && (9.5..15.0).contains(&took), "{r:?} after {took}s");
    }

    /// Latency of small calls through retries + hedging (needs the API key):
    /// `cargo test --lib holo -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn small_calls_never_hang() {
        let _ = dotenvy::from_path(concat!(env!("CARGO_MANIFEST_DIR"), "/../.env"));
        let holo = super::Holo::new();
        let body = serde_json::json!({
            "model": "holo4-27b",
            "messages": [{ "role": "user", "content": "Say hi" }],
            "max_tokens": 10,
            "reasoning_effort": "none",
        });
        tauri::async_runtime::block_on(async {
            for i in 0..20 {
                let t = std::time::Instant::now();
                let r = holo.chat(&body).await;
                println!("call {i}: {:.1}s {}", t.elapsed().as_secs_f32(), if r.is_ok() { "ok" } else { "FAIL" });
                assert!(r.is_ok(), "{r:?}");
            }
        });
    }
}
