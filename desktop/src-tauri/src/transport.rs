use std::{
    process::Stdio,
    sync::{atomic::Ordering, Arc},
    time::{Duration, Instant},
};

use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    process::Child,
    sync::{mpsc, watch},
};
use tokio_tungstenite::tungstenite::{client::IntoClientRequest, http::HeaderValue, Message};

use crate::{input, protocol, Lifecycle, State};

struct Engine {
    child: Option<Child>,
    url: String,
    token: String,
}

async fn launch(state: &State) -> Result<Engine, String> {
    if let Ok(url) = std::env::var("ENGINE_WS_URL") {
        validate_url(&url)?;
        return Ok(Engine {
            child: None,
            url,
            token: state.token.clone(),
        });
    }
    let port = std::net::TcpListener::bind("127.0.0.1:0")
        .map_err(|e| e.to_string())?
        .local_addr()
        .map_err(|e| e.to_string())?
        .port();
    let python = std::env::var("HCOMPANY_PYTHON").unwrap_or_else(|_| "python3".into());
    let root = std::env::var("HCOMPANY_ENGINE_DIR").unwrap_or_else(|_| {
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .to_string_lossy()
            .into_owned()
    });
    let mut child = tokio::process::Command::new(python)
        .args(["-u", "-m", "engine"])
        .current_dir(root)
        .env("ENGINE_HOST", "127.0.0.1")
        .env("ENGINE_PORT", port.to_string())
        .env("ENGINE_SESSION_ID", &state.session)
        .env("ENGINE_SESSION_TOKEN", &state.token)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .kill_on_drop(true)
        .spawn()
        .map_err(|e| e.to_string())?;
    let started = Instant::now();
    let stdout = child.stdout.take().ok_or("sidecar stdout missing")?;
    let mut lines = BufReader::new(stdout).lines();
    let ready = tokio::time::timeout(Duration::from_secs(10), async {
        while let Some(line) = lines.next_line().await.map_err(|e| e.to_string())? {
            if let Some(json) = line.strip_prefix("ENGINE_READY ") {
                let value: Value = serde_json::from_str(json).map_err(|e| e.to_string())?;
                if value["ws_port"].as_u64() != Some(port.into()) {
                    return Err("sidecar port mismatch".into());
                }
                return Ok(());
            }
        }
        Err::<(), String>("sidecar exited before ready".into())
    })
    .await;
    match ready {
        Ok(Ok(())) => {}
        _ => {
            terminate(&mut child).await;
            return Err("Engine non prêt après lancement (délai maximal 10 s).".into());
        }
    }
    tokio::spawn(async move { while let Ok(Some(_)) = lines.next_line().await {} });
    eprintln!(
        "desktop latency sidecar_ready_ms={:.2}",
        started.elapsed().as_secs_f64() * 1000.
    );
    Ok(Engine {
        child: Some(child),
        url: format!("ws://127.0.0.1:{port}/"),
        token: state.token.clone(),
    })
}

fn validate_url(url: &str) -> Result<(), String> {
    let request = url.into_client_request().map_err(|e| e.to_string())?;
    if request.uri().scheme_str() != Some("ws")
        || !matches!(
            request.uri().host(),
            Some("127.0.0.1" | "localhost" | "[::1]")
        )
    {
        return Err("engine must use a loopback ws endpoint".into());
    }
    Ok(())
}

async fn terminate(child: &mut Child) {
    if let Some(mut stdin) = child.stdin.take() {
        let _ = stdin.write_all(b"shutdown\n").await;
    }
    #[cfg(unix)]
    if let Some(pid) = child.id() {
        let _ = tokio::process::Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .status()
            .await;
    }
    if tokio::time::timeout(Duration::from_secs(3), child.wait())
        .await
        .is_err()
    {
        let _ = child.kill().await;
        let _ = child.wait().await;
    }
}

pub async fn run(
    app: AppHandle,
    state: Arc<State>,
    mut rx: mpsc::Receiver<Value>,
    mut control: watch::Receiver<Lifecycle>,
) {
    loop {
        while *control.borrow() == Lifecycle::Stopped {
            if control.changed().await.is_err() {
                return;
            }
        }
        if *control.borrow() == Lifecycle::Shutdown {
            break;
        }
        let mut engine = match launch(&state).await {
            Ok(engine) => engine,
            Err(error) => {
                let _ = app.emit("native:error", error);
                let _ = state.lifecycle.send(Lifecycle::Stopped);
                continue;
            }
        };
        let mut attempts = 0_u32;
        while *control.borrow() == Lifecycle::Running {
            if engine
                .child
                .as_mut()
                .is_some_and(|c| !matches!(c.try_wait(), Ok(None)))
            {
                let _ = app.emit("native:error", "Engine arrêté ; redémarrez explicitement.");
                let _ = state.lifecycle.send(Lifecycle::Stopped);
                break;
            }
            while rx.try_recv().is_ok() {}
            let mut request = match engine.url.as_str().into_client_request() {
                Ok(r) => r,
                Err(_) => break,
            };
            let Ok(auth) = HeaderValue::from_str(&format!("Bearer {}", engine.token)) else {
                break;
            };
            request.headers_mut().insert("Authorization", auth);
            request
                .headers_mut()
                .insert("Origin", HeaderValue::from_static("tauri://localhost"));
            let started = Instant::now();
            let connected = tokio::select! {
                result = tokio::time::timeout(Duration::from_secs(5), tokio_tungstenite::connect_async(request)) => result,
                _ = control.changed() => break,
            };
            if let Ok(Ok((mut socket, _))) = connected {
                eprintln!(
                    "desktop latency ws_connect_ms={:.2}",
                    started.elapsed().as_secs_f64() * 1000.
                );
                let hello = protocol::envelope(
                    &state.session,
                    "hello",
                    json!({
                    "app_version":env!("CARGO_PKG_VERSION"), "platform":std::env::consts::OS,
                    "capabilities":["pointer","capture.region","pcm_s16le","input.action"]}),
                    None,
                );
                let permissions = protocol::envelope(
                    &state.session,
                    "permissions",
                    serde_json::to_value(crate::native::permissions()).unwrap(),
                    None,
                );
                for packet in [hello, permissions] {
                    if protocol::validate(&packet, &state.session).is_ok() {
                        let _ = socket.send(Message::Text(packet.to_string().into())).await;
                    }
                }
                state.connected.store(true, Ordering::SeqCst);
                let _ = app.emit("sidecar:status", "connected");
                attempts = 0;
                let mut tick = tokio::time::interval(Duration::from_secs(2));
                let mut last_rx = Instant::now();
                loop {
                    tokio::select! {
                        biased;
                        _ = control.changed() => break,
                        incoming = socket.next() => match incoming {
                            Some(Ok(Message::Text(text))) => {
                                last_rx = Instant::now();
                                match protocol::parse(&text, &state.session) {
                                    Ok(value) => crate::receive(&app, &state, value).await,
                                    Err(_) => { let _ = app.emit("native:error", "Message engine non conforme ignoré."); }
                                }
                            }
                            Some(Ok(Message::Ping(data))) => { let _ = socket.send(Message::Pong(data)).await; }
                            Some(Ok(Message::Pong(_))) => last_rx = Instant::now(),
                            Some(Ok(Message::Close(_))) | None | Some(Err(_)) => break,
                            _ => {}
                        },
                        packet = rx.recv() => {
                            let Some(packet) = packet else { break };
                            if protocol::validate(&packet, &state.session).is_err() {
                                let _ = app.emit("native:error", "Message sortant invalide bloqué."); continue;
                            }
                            if socket.send(Message::Text(packet.to_string().into())).await.is_err() { break; }
                        }
                        _ = tick.tick() => {
                            if last_rx.elapsed() > Duration::from_secs(10) { break; }
                            if engine.child.as_mut().is_some_and(|c| !matches!(c.try_wait(), Ok(None))) { break; }
                            if socket.send(Message::Ping(Vec::new().into())).await.is_err() { break; }
                        }
                    }
                }
                let _ = socket.close(None).await;
            }
            state.connected.store(false, Ordering::SeqCst);
            input::stop(&state);
            state.captures.lock().unwrap().clear();
            let _ = app.emit("guide:clear", ());
            let _ = app.emit("sidecar:status", "disconnected");
            if *control.borrow() != Lifecycle::Running {
                break;
            }
            attempts += 1;
            let delay = Duration::from_millis((250_u64 * 2_u64.pow(attempts.min(4))).min(4000));
            tokio::select! { _ = tokio::time::sleep(delay) => {}, _ = control.changed() => break }
        }
        state.connected.store(false, Ordering::SeqCst);
        input::stop(&state);
        state.captures.lock().unwrap().clear();
        if let Some(ref mut child) = engine.child {
            terminate(child).await;
        }
        let _ = app.emit("sidecar:status", "stopped");
    }
    state.shutdown_done.store(true, Ordering::SeqCst);
    app.exit(0);
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn no_remote_engine_or_plain_http() {
        assert!(validate_url("ws://127.0.0.1:9123/").is_ok());
        assert!(validate_url("ws://example.com/").is_err());
        assert!(validate_url("wss://127.0.0.1/").is_err());
        assert!(validate_url("http://localhost/").is_err());
    }

    #[tokio::test]
    #[allow(clippy::result_large_err)]
    #[ignore = "live loopback integration; run through pytest -m live"]
    async fn live_loopback_auth_and_protocol() {
        use tokio_tungstenite::{
            accept_hdr_async,
            tungstenite::handshake::server::{Request, Response},
        };
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let token = uuid::Uuid::new_v4().to_string();
        let server_token = token.clone();
        let task = tokio::spawn(async move {
            let (tcp, _) = listener.accept().await.unwrap();
            let mut socket = accept_hdr_async(tcp, |r: &Request, response: Response| {
                assert_eq!(
                    r.headers()["Authorization"],
                    format!("Bearer {server_token}")
                );
                assert_eq!(r.headers()["Origin"], "tauri://localhost");
                Ok(response)
            })
            .await
            .unwrap();
            let message = socket.next().await.unwrap().unwrap();
            let value = protocol::parse(message.to_text().unwrap(), "live").unwrap();
            assert_eq!(value["type"], "ping");
            let pong = protocol::envelope(
                "live",
                "pong",
                value["payload"].clone(),
                value["message_id"].as_str(),
            );
            socket
                .send(Message::Text(pong.to_string().into()))
                .await
                .unwrap();
        });
        let mut request = format!("ws://127.0.0.1:{port}/")
            .into_client_request()
            .unwrap();
        request.headers_mut().insert(
            "Authorization",
            HeaderValue::from_str(&format!("Bearer {token}")).unwrap(),
        );
        request
            .headers_mut()
            .insert("Origin", HeaderValue::from_static("tauri://localhost"));
        let start = Instant::now();
        let (mut socket, _) = tokio_tungstenite::connect_async(request).await.unwrap();
        let ping = protocol::envelope("live", "ping", json!({"nonce":"probe"}), None);
        socket
            .send(Message::Text(ping.to_string().into()))
            .await
            .unwrap();
        let message = socket.next().await.unwrap().unwrap();
        let value = protocol::parse(message.to_text().unwrap(), "live").unwrap();
        assert_eq!(value["type"], "pong");
        println!(
            "live websocket_handshake_roundtrip_ms={:.2}",
            start.elapsed().as_secs_f64() * 1000.
        );
        task.await.unwrap();
    }
}
