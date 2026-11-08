use crate::{autopilot, devin, journal};
use std::path::Path;
use std::time::Duration;
use tokio::process::Command;

#[derive(Debug)]
pub enum Failure {
    NotEligible,
    Failed(String),
    TimedOut,
    Stopped,
}

impl std::fmt::Display for Failure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NotEligible => f.write_str("No eligible script"),
            Self::Failed(message) => f.write_str(message),
            Self::TimedOut => f.write_str("The script timed out"),
            Self::Stopped => f.write_str("Stop requested"),
        }
    }
}

pub fn eligible(skill: &crate::skills::Skill) -> Option<devin::Compiled> {
    devin::selected(skill)
}

fn interpreter(language: &str) -> Option<&'static str> {
    match language {
        "bash" => Some("bash"),
        "python" => Some("python3"),
        "osascript" => Some("osascript"),
        _ => None,
    }
}

fn env_for_script() -> Vec<(String, String)> {
    [
        "HOME",
        "PATH",
        "LANG",
        "LC_ALL",
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "XDG_RUNTIME_DIR",
        "TMPDIR",
    ]
    .into_iter()
    .filter_map(|key| std::env::var(key).ok().map(|v| (key.into(), v)))
    .collect()
}

pub async fn run(artifact: &devin::Compiled) -> Result<(), Failure> {
    let interpreter = interpreter(&artifact.output.language).ok_or(Failure::NotEligible)?;
    if !artifact
        .output
        .script
        .is_char_boundary(artifact.output.script.len())
    {
        return Err(Failure::Failed("Script non UTF-8".into()));
    }
    let dir = tempfile::tempdir()
        .map_err(|e| Failure::Failed(format!("Dossier temporaire indisponible : {e}")))?;
    let extension = match artifact.output.language.as_str() {
        "bash" => "sh",
        "python" => "py",
        _ => "applescript",
    };
    let path = dir.path().join(format!("run.{extension}"));
    std::fs::write(&path, &artifact.output.script)
        .map_err(|e| Failure::Failed(format!("Script non lisible : {e}")))?;
    let mut command = Command::new(interpreter);
    command.arg(&path);
    command.args(default_params(artifact));
    command
        .current_dir(Path::new(
            &std::env::var("HOME").unwrap_or_else(|_| "/".into()),
        ))
        .env_clear()
        .envs(env_for_script())
        .kill_on_drop(true);
    #[cfg(unix)]
    command.process_group(0);
    journal::event(
        "script_start",
        serde_json::json!({ "sha256": artifact.sha256, "language": artifact.output.language }),
    );
    let mut child = command
        .spawn()
        .map_err(|e| Failure::Failed(format!("Could not start the script: {e}")))?;
    let pid = child.id();
    let result = tokio::select! {
        _ = wait_stop() => { kill_process(&mut child, pid).await; Err(Failure::Stopped) },
        result = tokio::time::timeout(Duration::from_secs(std::env::var("RIO_SCRIPT_TIMEOUT_SECONDS").ok().and_then(|v| v.parse().ok()).unwrap_or(300)), child.wait()) => match result {
            Ok(Ok(status)) if status.success() => Ok(()),
            Ok(Ok(status)) => Err(Failure::Failed(format!("The script exited with {status}"))),
            Ok(Err(e)) => Err(Failure::Failed(format!("Script error: {e}"))),
            Err(_) => { kill_process(&mut child, pid).await; Err(Failure::TimedOut) },
        }
    };
    if let Err(error) = &result {
        journal::event(
            "script_failure",
            serde_json::json!({ "error": error.to_string() }),
        );
    }
    result
}

async fn wait_stop() {
    while !autopilot::stop_requested() {
        tokio::time::sleep(Duration::from_millis(40)).await;
    }
}

async fn kill_process(child: &mut tokio::process::Child, pid: Option<u32>) {
    #[cfg(unix)]
    if let Some(pid) = pid {
        unsafe {
            libc::kill(-(pid as i32), libc::SIGKILL);
        }
    }
    let _ = child.kill().await;
}

pub fn default_params(artifact: &devin::Compiled) -> Vec<String> {
    artifact
        .output
        .params
        .iter()
        .flat_map(|p| [format!("--{}", p.name), p.default.clone()])
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn script_default_params_are_not_shell_expanded_here() {
        let mut o = devin::Output {
            language: "bash".into(),
            script: "echo ok".into(),
            params: vec![],
            test_command: "true".into(),
            tested: true,
            test_platform: std::env::consts::OS.into(),
            test_evidence: "ok".into(),
            notes: String::new(),
        };
        o.params.push(devin::Param {
            name: "path".into(),
            description: "chemin".into(),
            default: "$HOME/Projet".into(),
        });
        let c = devin::Compiled {
            graph_version: 1,
            session_id: "s".into(),
            url: "u".into(),
            status: "completed".into(),
            date: 0,
            sha256: devin::hash(&o.script),
            target_os: std::env::consts::OS.into(),
            acus_consumed: 0.0,
            output: o,
        };
        assert_eq!(default_params(&c), ["--path", "$HOME/Projet"]);
    }
}
