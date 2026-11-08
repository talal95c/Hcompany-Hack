//! A headless Chrome driven over the DevTools protocol: the learner
//! simulator's screen and hands. Nothing touches the real desktop.

use base64::{Engine, engine::general_purpose::STANDARD};
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::Duration;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::{MaybeTlsStream, WebSocketStream, connect_async};

/// Viewport, in CSS pixels; screenshots have exactly this size.
pub const WIDTH: f64 = 1440.0;
pub const HEIGHT: f64 = 900.0;
const CALL_TIMEOUT: Duration = Duration::from_secs(30);

type Socket = WebSocketStream<MaybeTlsStream<tokio::net::TcpStream>>;

pub struct Browser {
    child: Child,
    ws: Socket,
    next: u64,
    profile: PathBuf,
}

fn chrome_path() -> String {
    std::env::var("SIM_CHROME")
        .unwrap_or_else(|_| "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome".into())
}

impl Browser {
    /// Starts a fresh headless Chrome (throwaway profile) on `url`.
    pub async fn launch(url: &str) -> Result<Self, String> {
        let stamp =
            std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
        let profile = std::env::temp_dir().join(format!("rio-sim-{}-{stamp}", std::process::id()));
        let mut child = Command::new(chrome_path())
            .args([
                "--headless=new",
                "--remote-debugging-port=0",
                &format!("--user-data-dir={}", profile.display()),
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--hide-scrollbars",
                "--mute-audio",
                "--force-device-scale-factor=1",
                &format!("--window-size={WIDTH},{HEIGHT}"),
                "about:blank",
            ])
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("Chrome failed to start ({}): {e}", chrome_path()))?;

        // Chrome prints its DevTools endpoint on stderr.
        let stderr = child.stderr.take().ok_or("no Chrome stderr")?;
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                if let Some(ws) = line.strip_prefix("DevTools listening on ") {
                    let _ = tx.send(ws.trim().to_string());
                }
            }
        });
        let endpoint = tauri::async_runtime::spawn_blocking(move || rx.recv_timeout(Duration::from_secs(20)))
            .await
            .map_err(|e| e.to_string())?
            .map_err(|_| "Chrome did not open its DevTools endpoint".to_string())?;
        let port = endpoint
            .trim_start_matches("ws://")
            .split(['/', ':'])
            .nth(1)
            .ok_or_else(|| format!("unexpected DevTools endpoint {endpoint}"))?
            .to_string();

        let targets: Value = reqwest::get(format!("http://127.0.0.1:{port}/json/list"))
            .await
            .map_err(|e| e.to_string())?
            .json()
            .await
            .map_err(|e| e.to_string())?;
        let page = targets
            .as_array()
            .into_iter()
            .flatten()
            .find(|t| t["type"] == "page")
            .and_then(|t| t["webSocketDebuggerUrl"].as_str())
            .ok_or("no Chrome page target")?;
        let (ws, _) = connect_async(page).await.map_err(|e| e.to_string())?;

        let mut browser = Self { child, ws, next: 0, profile };
        browser
            .call(
                "Emulation.setDeviceMetricsOverride",
                json!({ "width": WIDTH as u32, "height": HEIGHT as u32, "deviceScaleFactor": 1, "mobile": false }),
            )
            .await?;
        browser.navigate(url).await?;
        Ok(browser)
    }

    /// One DevTools command; events received meanwhile are ignored.
    async fn call(&mut self, method: &str, params: Value) -> Result<Value, String> {
        self.next += 1;
        let id = self.next;
        let msg = json!({ "id": id, "method": method, "params": params }).to_string();
        self.ws.send(Message::text(msg)).await.map_err(|e| e.to_string())?;
        loop {
            let frame = tokio::time::timeout(CALL_TIMEOUT, self.ws.next())
                .await
                .map_err(|_| format!("Chrome did not answer {method}"))?
                .ok_or("Chrome closed the connection")?
                .map_err(|e| e.to_string())?;
            let Message::Text(text) = frame else { continue };
            let v: Value = serde_json::from_str(&text).map_err(|e| e.to_string())?;
            if v["id"].as_u64() != Some(id) {
                continue;
            }
            if let Some(err) = v.get("error") {
                return Err(format!("{method}: {err}"));
            }
            return Ok(v["result"].clone());
        }
    }

    pub async fn navigate(&mut self, url: &str) -> Result<(), String> {
        self.call("Page.navigate", json!({ "url": url })).await?;
        for _ in 0..80 {
            if self.eval("document.readyState").await? == "complete" {
                break;
            }
            tokio::time::sleep(Duration::from_millis(250)).await;
        }
        self.settle().await;
        Ok(())
    }

    /// Lets the page react (animations, re-render) before the next look.
    pub async fn settle(&self) {
        tokio::time::sleep(Duration::from_millis(700)).await;
    }

    /// The viewport as JPEG bytes.
    pub async fn screenshot(&mut self) -> Result<Vec<u8>, String> {
        let r = self.call("Page.captureScreenshot", json!({ "format": "jpeg", "quality": 82 })).await?;
        STANDARD.decode(r["data"].as_str().ok_or("empty screenshot")?).map_err(|e| e.to_string())
    }

    /// Evaluates a JavaScript expression in the page and returns its value.
    pub async fn eval(&mut self, expression: &str) -> Result<Value, String> {
        let r = self
            .call("Runtime.evaluate", json!({ "expression": expression, "returnByValue": true, "awaitPromise": true }))
            .await?;
        if let Some(e) = r.get("exceptionDetails") {
            return Err(format!("page error: {}", e["exception"]["description"].as_str().unwrap_or("?")));
        }
        Ok(r["result"]["value"].clone())
    }

    fn px(nx: f64, ny: f64) -> (f64, f64) {
        (nx / 1000.0 * WIDTH, ny / 1000.0 * HEIGHT)
    }

    /// Clicks at a normalized (0..1000) point.
    pub async fn click(&mut self, nx: f64, ny: f64) -> Result<(), String> {
        let (x, y) = Self::px(nx, ny);
        self.call("Input.dispatchMouseEvent", json!({ "type": "mouseMoved", "x": x, "y": y })).await?;
        for kind in ["mousePressed", "mouseReleased"] {
            self.call(
                "Input.dispatchMouseEvent",
                json!({ "type": kind, "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1 }),
            )
            .await?;
        }
        Ok(())
    }

    /// True when the element at a normalized point already has the focus
    /// (typing there must not click first: that would drop a selection).
    pub async fn focused_at(&mut self, nx: f64, ny: f64) -> Result<bool, String> {
        let (x, y) = Self::px(nx, ny);
        let v = self
            .eval(&format!(
                "(() => {{ const e = document.elementFromPoint({x}, {y}); const a = document.activeElement; \
                 return !!e && !!a && a !== document.body && (e === a || a.contains(e) || e.contains(a)); }})()"
            ))
            .await?;
        Ok(v == serde_json::Value::Bool(true))
    }

    /// Types text into the focused element.
    pub async fn type_text(&mut self, text: &str) -> Result<(), String> {
        self.call("Input.insertText", json!({ "text": text })).await.map(|_| ())
    }

    pub async fn scroll(&mut self, nx: f64, ny: f64, direction: &str) -> Result<(), String> {
        let (x, y) = Self::px(nx, ny);
        let (dx, dy) = match direction {
            "up" => (0, -400),
            "left" => (-400, 0),
            "right" => (400, 0),
            _ => (0, 400),
        };
        self.call(
            "Input.dispatchMouseEvent",
            json!({ "type": "mouseWheel", "x": x, "y": y, "deltaX": dx, "deltaY": dy }),
        )
        .await
        .map(|_| ())
    }

    /// Presses a key or shortcut such as "enter", "escape" or "cmd+a".
    pub async fn press(&mut self, keys: &str) -> Result<(), String> {
        let (modifiers, key) = parse_keys(keys);
        let (key_name, code, vk, text) = key_info(&key);
        // Editing shortcuts are browser commands in headless Chrome on macOS.
        let commands: Vec<&str> = match (modifiers & (META | CTRL) != 0, key.as_str()) {
            (true, "a") => vec!["selectAll"],
            (true, "c") => vec!["copy"],
            (true, "v") => vec!["paste"],
            (true, "x") => vec!["cut"],
            (true, "z") => vec!["undo"],
            _ => vec![],
        };
        let typed = if modifiers & (META | CTRL) == 0 { text } else { String::new() };
        self.call(
            "Input.dispatchKeyEvent",
            json!({ "type": if typed.is_empty() { "rawKeyDown" } else { "keyDown" }, "modifiers": modifiers,
                    "key": key_name, "code": code, "windowsVirtualKeyCode": vk, "text": typed, "commands": commands }),
        )
        .await?;
        self.call(
            "Input.dispatchKeyEvent",
            json!({ "type": "keyUp", "modifiers": modifiers, "key": key_name, "code": code, "windowsVirtualKeyCode": vk }),
        )
        .await
        .map(|_| ())
    }
}

impl Drop for Browser {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = std::fs::remove_dir_all(&self.profile);
    }
}

const ALT: u32 = 1;
const CTRL: u32 = 2;
const META: u32 = 4;
const SHIFT: u32 = 8;

/// "cmd+shift+n" → (META | SHIFT, "n").
fn parse_keys(keys: &str) -> (u32, String) {
    let mut modifiers = 0;
    let mut key = String::new();
    for part in keys.split('+').map(|p| p.trim().to_lowercase()) {
        match part.as_str() {
            "cmd" | "command" | "meta" | "⌘" => modifiers |= META,
            "ctrl" | "control" => modifiers |= CTRL,
            "alt" | "option" | "opt" => modifiers |= ALT,
            "shift" => modifiers |= SHIFT,
            _ => key = part,
        }
    }
    (modifiers, key)
}

/// DevTools key name, code, Windows virtual key code, and typed text.
fn key_info(key: &str) -> (String, String, u32, String) {
    let named = |name: &str, code: &str, vk: u32, text: &str| (name.into(), code.into(), vk, text.into());
    match key {
        "enter" | "return" => named("Enter", "Enter", 13, "\r"),
        "tab" => named("Tab", "Tab", 9, ""),
        "escape" | "esc" => named("Escape", "Escape", 27, ""),
        "backspace" | "delete" => named("Backspace", "Backspace", 8, ""),
        "space" => named(" ", "Space", 32, " "),
        "up" | "arrowup" => named("ArrowUp", "ArrowUp", 38, ""),
        "down" | "arrowdown" => named("ArrowDown", "ArrowDown", 40, ""),
        "left" | "arrowleft" => named("ArrowLeft", "ArrowLeft", 37, ""),
        "right" | "arrowright" => named("ArrowRight", "ArrowRight", 39, ""),
        k if k.chars().count() == 1 => {
            let c = k.chars().next().unwrap_or('a');
            let upper = c.to_ascii_uppercase();
            let code = if c.is_ascii_digit() { format!("Digit{c}") } else { format!("Key{upper}") };
            (c.to_string(), code, upper as u32, c.to_string())
        }
        other => (other.into(), other.into(), 0, String::new()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shortcuts_parse() {
        assert_eq!(parse_keys("cmd+shift+N"), (META | SHIFT, "n".into()));
        assert_eq!(parse_keys("enter"), (0, "enter".into()));
        assert_eq!(key_info("enter").2, 13);
        assert_eq!(key_info("a").1, "KeyA");
    }
}
