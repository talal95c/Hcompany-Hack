use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    sync::{Mutex, OnceLock},
};

#[derive(Clone)]
pub struct Metadata {
    pub id: String,
    pub name: String,
    pub version: Option<String>,
}

fn desktop_name(contents: &str) -> Option<String> {
    let section = contents.split("[Desktop Entry]").nth(1)?;
    let section = section.split("\n[").next()?;
    section.lines().find_map(|line| {
        line.strip_prefix("Name=")
            .filter(|value| !value.trim().is_empty())
            .map(str::to_owned)
    })
}

fn numeric_version(value: &str) -> Option<String> {
    let upstream = value.trim().rsplit(':').next()?;
    let version: String = upstream
        .chars()
        .take_while(|c| c.is_ascii_digit() || *c == '.')
        .collect();
    (!version.is_empty() && version.split('.').all(|part| !part.is_empty())).then_some(version)
}

fn installed_version(path: &Path) -> Option<String> {
    let owner = std::process::Command::new("dpkg-query")
        .arg("-S")
        .arg(path)
        .output()
        .ok()?;
    if !owner.status.success() {
        return None;
    }
    let owner = String::from_utf8(owner.stdout).ok()?;
    let package = owner.lines().next()?.split(": ").next()?;
    let output = std::process::Command::new("dpkg-query")
        .args(["-W", "-f=${Version}", package])
        .output()
        .ok()?;
    output.status.success().then_some(())?;
    numeric_version(std::str::from_utf8(&output.stdout).ok()?)
}

pub fn lookup(id: &str) -> Option<Metadata> {
    if id.is_empty()
        || !id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || "._-".contains(c))
    {
        return None;
    }
    static CACHE: OnceLock<Mutex<HashMap<String, Option<Metadata>>>> = OnceLock::new();
    let mut cache = CACHE.get_or_init(Mutex::default).lock().unwrap();
    cache
        .entry(id.into())
        .or_insert_with(|| {
            let home = std::env::var_os("XDG_DATA_HOME")
                .map(PathBuf::from)
                .or_else(|| {
                    std::env::var_os("HOME").map(|p| PathBuf::from(p).join(".local/share"))
                });
            let dirs = std::env::var("XDG_DATA_DIRS")
                .unwrap_or_else(|_| "/usr/local/share:/usr/share".into());
            home.into_iter()
                .chain(std::env::split_paths(&dirs))
                .find_map(|directory| {
                    let path = directory.join("applications").join(format!("{id}.desktop"));
                    let name = desktop_name(&std::fs::read_to_string(&path).ok()?)?;
                    Some(Metadata {
                        id: id.into(),
                        name,
                        version: installed_version(&path),
                    })
                })
        })
        .clone()
}

pub fn for_class(value: &[u8]) -> Option<Metadata> {
    value
        .split(|b| *b == 0)
        .rev()
        .filter_map(|part| std::str::from_utf8(part).ok())
        .find_map(lookup)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn names_come_only_from_desktop_entry() {
        assert_eq!(
            desktop_name("[Desktop Entry]\nName=Editor\n[Desktop Action edit]\nName=Other"),
            Some("Editor".into())
        );
        assert_eq!(
            desktop_name("[Desktop Entry]\nName=\n[Desktop Action edit]\nName=Other"),
            None
        );
        assert_eq!(desktop_name("Name=Unscoped"), None);
        assert!(lookup("../../unsafe").is_none());
    }

    #[test]
    fn package_versions_do_not_guess_unknown_values() {
        assert_eq!(
            numeric_version("1:7.3.7-0ubuntu0.22.04.13\n"),
            Some("7.3.7".into())
        );
        assert_eq!(numeric_version("2.4.1+dfsg-1"), Some("2.4.1".into()));
        assert_eq!(numeric_version("unknown"), None);
        assert_eq!(numeric_version(""), None);
        assert_eq!(numeric_version("1..2"), None);
    }
}
