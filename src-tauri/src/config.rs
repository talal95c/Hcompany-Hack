//! Where Rio reads its settings. In dev, `.env` in the working directory
//! (or a parent); for the installed app, launched from Finder with cwd `/`,
//! `~/Library/Application Support/ai.rio.desktop/.env` or `~/.rio/.env`.

use std::path::PathBuf;

/// The per-user `.env` files, in priority order.
pub fn user_env_files() -> Vec<PathBuf> {
    let Some(home) = std::env::var_os("HOME").map(PathBuf::from) else { return Vec::new() };
    vec![home.join("Library/Application Support/ai.rio.desktop/.env"), home.join(".rio/.env")]
}

/// Loads every `.env` (earlier ones win, the environment beats them all) and
/// adds the usual tool folders to `PATH`: Finder gives apps only `/usr/bin:/bin:...`.
pub fn load() {
    let _ = dotenvy::dotenv();
    for path in user_env_files() {
        let _ = dotenvy::from_path(path);
    }
    let mut dirs: Vec<PathBuf> = std::env::var_os("PATH").map(|p| std::env::split_paths(&p).collect()).unwrap_or_default();
    let mut extra: Vec<PathBuf> = vec!["/opt/homebrew/bin".into(), "/usr/local/bin".into()];
    if let Some(home) = std::env::var_os("HOME").map(PathBuf::from) {
        extra.extend([home.join(".npm-global/bin"), home.join(".local/bin"), home.join(".bun/bin")]);
    }
    for dir in extra {
        if !dirs.contains(&dir) {
            dirs.push(dir);
        }
    }
    if let Ok(path) = std::env::join_paths(dirs) {
        // SAFETY: called first thing in `run`, before any other thread starts.
        unsafe { std::env::set_var("PATH", path) };
    }
}

/// A setting read fresh from the `.env` files (same priority as `load`).
pub fn file_setting(key: &str) -> Option<String> {
    let find = |it: dotenvy::Iter<std::fs::File>| it.flatten().find(|(k, _)| k == key).map(|(_, v)| v);
    dotenvy::dotenv_iter()
        .ok()
        .and_then(find)
        .or_else(|| user_env_files().into_iter().find_map(|p| dotenvy::from_path_iter(p).ok().and_then(find)))
}

#[cfg(test)]
mod tests {
    #[test]
    fn user_env_files_live_under_home() {
        let files = super::user_env_files();
        let home = std::env::var("HOME").unwrap();
        assert!(files.iter().all(|p| p.starts_with(&home) && p.ends_with(".env")));
    }
}
