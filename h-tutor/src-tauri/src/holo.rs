//! Thin client for H Company's Models API (OpenAI-compatible, Holo models).

use serde::de::DeserializeOwned;
use serde_json::{json, Value};

pub struct Holo {
    http: reqwest::Client,
}

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
                .timeout(std::time::Duration::from_secs(90))
                .build()
                .expect("HTTP client"),
        }
    }

    /// Raw chat completion: posts `body` as is, returns the first choice's
    /// message and the latency in ms.
    pub async fn chat(&self, body: &Value) -> Result<(Value, u128), String> {
        let started = std::time::Instant::now();
        let key = api_key().ok_or("HAI_API_KEY is missing: add it to the .env file")?;
        let base = env_or("HAI_BASE_URL", "https://api.hcompany.ai/v1");
        let res = self
            .http
            .post(format!("{}/chat/completions", base.trim_end_matches('/')))
            .bearer_auth(key)
            .json(body)
            .send()
            .await
            .map_err(|e| format!("Network error: {e}"))?;
        let status = res.status();
        let text = res.text().await.map_err(|e| format!("Network error: {e}"))?;
        if !status.is_success() {
            let detail: String = text.chars().take(300).collect();
            return Err(format!("Holo {status}: {detail}"));
        }
        let v: Value = serde_json::from_str(&text).map_err(|e| format!("Unreadable response: {e}"))?;
        Ok((v["choices"][0]["message"].clone(), started.elapsed().as_millis()))
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
        let started = std::time::Instant::now();
        let key = api_key().ok_or("HAI_API_KEY is missing: add it to the .env file")?;
        let base = env_or("HAI_BASE_URL", "https://api.hcompany.ai/v1");

        let mut content: Vec<Value> = images
            .iter()
            .map(|url| json!({ "type": "image_url", "image_url": { "url": url } }))
            .collect();
        content.push(json!({ "type": "text", "text": prompt }));

        let body = json!({
            "model": model,
            "messages": [{ "role": "user", "content": content }],
            "temperature": 0.0,
            "structured_outputs": { "json": schema },
            "chat_template_kwargs": { "enable_thinking": false },
        });

        let res = self
            .http
            .post(format!("{}/chat/completions", base.trim_end_matches('/')))
            .bearer_auth(key)
            .json(&body)
            .send()
            .await
            .map_err(|e| format!("Network error: {e}"))?;

        let status = res.status();
        let text = res.text().await.map_err(|e| format!("Network error: {e}"))?;
        let ms = started.elapsed().as_millis();
        if !status.is_success() {
            crate::debug::record(tag, model, images, prompt, &format!("HTTP {status}: {text}"), ms);
            let hint = match status.as_u16() {
                401 | 403 => "API key rejected",
                402 => "not enough credits",
                404 => "model not found (check HOLO_*_MODEL)",
                429 => "rate limit reached, try again in a moment",
                _ => "API error",
            };
            let detail: String = text.chars().take(240).collect();
            return Err(format!("Holo {status}: {hint}. {detail}"));
        }

        let v: Value = serde_json::from_str(&text).map_err(|e| format!("Unreadable response: {e}"))?;
        let raw = v["choices"][0]["message"]["content"]
            .as_str()
            .ok_or("Empty response from the model")?;
        let id = crate::debug::record(tag, model, images, prompt, raw, ms);
        let cleaned = raw
            .trim()
            .trim_start_matches("```json")
            .trim_start_matches("```")
            .trim_end_matches("```")
            .trim();
        serde_json::from_str(cleaned)
            .map(|v| (v, id))
            .map_err(|e| format!("Unexpected JSON ({e}): {raw}"))
    }
}
