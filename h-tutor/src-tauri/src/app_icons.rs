//! Extracts application icons (and their dominant colour) from the installed
//! apps through NSWorkspace. Used once, by `export_icons`, to write the icons
//! the palette ships in `src/assets/apps/`; the app never runs this.

use serde::Serialize;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Mutex;

#[derive(Serialize, Clone)]
pub struct AppIcon {
    /// `data:image/png;base64,...`, 128 px.
    pub data_uri: String,
    /// Dominant colour of the icon, `#rrggbb`.
    pub color: String,
}

static CACHE: Mutex<Option<HashMap<String, Option<AppIcon>>>> = Mutex::new(None);

fn mdfind(query: &str) -> Option<PathBuf> {
    let out = Command::new("mdfind").arg(query).output().ok()?;
    String::from_utf8_lossy(&out.stdout)
        .lines()
        .find(|l| l.ends_with(".app"))
        .map(PathBuf::from)
}

/// Finds an installed app by bundle id, then by name ("Docker Desktop" also
/// tries "Docker").
fn find_app(name: &str, bundle_id: Option<&str>) -> Option<PathBuf> {
    if let Some(id) = bundle_id.filter(|id| !id.contains('\'')) {
        if let Some(p) = mdfind(&format!("kMDItemCFBundleIdentifier == '{id}'")) {
            return Some(p);
        }
    }
    let mut names = vec![name.trim().to_string()];
    if let Some(first) = name.split_whitespace().next().filter(|f| *f != name.trim()) {
        names.push(first.to_string());
    }
    let home = std::env::var("HOME").unwrap_or_default();
    let dirs = [
        "/Applications".to_string(),
        "/System/Applications".to_string(),
        "/System/Applications/Utilities".to_string(),
        "/Applications/Utilities".to_string(),
        "/System/Library/CoreServices".to_string(),
        format!("{home}/Applications"),
    ];
    for n in &names {
        for d in &dirs {
            let p = Path::new(d).join(format!("{n}.app"));
            if p.exists() {
                return Some(p);
            }
        }
    }
    names.iter().filter(|n| !n.contains('\'')).find_map(|n| {
        mdfind(&format!(
            "kMDItemContentType == 'com.apple.application-bundle' && kMDItemDisplayName == '{n}'cd"
        ))
    })
}

/// The app's icon as PNG bytes, from the representation closest to 256 px.
#[cfg(target_os = "macos")]
fn icon_png(path: &Path) -> Option<Vec<u8>> {
    use objc2::rc::autoreleasepool;
    use objc2::runtime::AnyObject;
    use objc2::{class, msg_send};
    use std::ffi::{c_void, CString};

    let cpath = CString::new(path.to_str()?).ok()?;
    autoreleasepool(|_| unsafe {
        let ns_path: *mut AnyObject = msg_send![class!(NSString), stringWithUTF8String: cpath.as_ptr()];
        let ws: *mut AnyObject = msg_send![class!(NSWorkspace), sharedWorkspace];
        let img: *mut AnyObject = msg_send![ws, iconForFile: ns_path];
        if img.is_null() {
            return None;
        }
        let tiff: *mut AnyObject = msg_send![img, TIFFRepresentation];
        let reps: *mut AnyObject = msg_send![class!(NSBitmapImageRep), imageRepsWithData: tiff];
        if reps.is_null() {
            return None;
        }
        let count: usize = msg_send![reps, count];
        let mut best: (*mut AnyObject, isize) = (std::ptr::null_mut(), 0);
        for i in 0..count {
            let rep: *mut AnyObject = msg_send![reps, objectAtIndex: i];
            let w: isize = msg_send![rep, pixelsWide];
            // Prefer the smallest one that is at least 256 px, else the largest.
            let better = best.0.is_null()
                || (w >= 256 && (best.1 < 256 || w < best.1))
                || (w < 256 && best.1 < 256 && w > best.1);
            if better {
                best = (rep, w);
            }
        }
        if best.0.is_null() {
            return None;
        }
        let props: *mut AnyObject = msg_send![class!(NSDictionary), dictionary];
        // NSBitmapImageFileTypePNG = 4
        let png: *mut AnyObject = msg_send![best.0, representationUsingType: 4usize, properties: props];
        if png.is_null() {
            return None;
        }
        let len: usize = msg_send![png, length];
        let bytes: *const c_void = msg_send![png, bytes];
        Some(std::slice::from_raw_parts(bytes as *const u8, len).to_vec())
    })
}

#[cfg(not(target_os = "macos"))]
fn icon_png(_path: &Path) -> Option<Vec<u8>> {
    None
}

/// Mean colour of the icon's opaque, saturated pixels (its "brand" colour).
fn dominant(img: &image::RgbaImage) -> String {
    let (mut r, mut g, mut b, mut n) = (0u64, 0u64, 0u64, 0u64);
    let (mut ar, mut ag, mut ab, mut an) = (0u64, 0u64, 0u64, 0u64);
    for p in img.pixels() {
        let [pr, pg, pb, pa] = p.0;
        if pa < 200 {
            continue;
        }
        let max = pr.max(pg).max(pb) as i32;
        let min = pr.min(pg).min(pb) as i32;
        ar += pr as u64;
        ag += pg as u64;
        ab += pb as u64;
        an += 1;
        if max - min > 60 && max > 70 {
            r += pr as u64;
            g += pg as u64;
            b += pb as u64;
            n += 1;
        }
    }
    let (r, g, b, n) = if n > an / 20 { (r, g, b, n) } else { (ar, ag, ab, an.max(1)) };
    format!("#{:02x}{:02x}{:02x}", r / n, g / n, b / n)
}

fn load(name: &str, bundle_id: Option<&str>) -> Option<AppIcon> {
    use base64::{engine::general_purpose::STANDARD, Engine};
    let path = find_app(name, bundle_id)?;
    let png = icon_png(&path)?;
    let img = image::load_from_memory(&png).ok()?;
    let small = img.resize(128, 128, image::imageops::FilterType::Lanczos3).to_rgba8();
    let color = dominant(&small);
    let mut out = std::io::Cursor::new(Vec::new());
    small.write_to(&mut out, image::ImageFormat::Png).ok()?;
    Some(AppIcon { data_uri: format!("data:image/png;base64,{}", STANDARD.encode(out.into_inner())), color })
}

#[allow(dead_code)]
pub async fn app_icons(apps: Vec<(String, Option<String>)>) -> HashMap<String, AppIcon> {
    tauri::async_runtime::spawn_blocking(move || {
        let mut out = HashMap::new();
        for (name, bundle) in apps {
            let cached = CACHE.lock().unwrap().get_or_insert_with(HashMap::new).get(&name).cloned();
            let icon = match cached {
                Some(c) => c,
                None => {
                    let icon = load(&name, bundle.as_deref());
                    CACHE.lock().unwrap().get_or_insert_with(HashMap::new).insert(name.clone(), icon.clone());
                    icon
                }
            };
            if let Some(i) = icon {
                out.insert(name, i);
            }
        }
        out
    })
    .await
    .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    /// One-off export of the apps' icons into the frontend (`src/assets/apps/`),
    /// so the palette ships them and never reads the computer:
    /// `cargo test --lib app_icons -- --ignored --nocapture`
    #[test]
    #[ignore]
    fn export_icons() {
        use base64::{engine::general_purpose::STANDARD, Engine};
        let dir = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../src/assets/apps");
        std::fs::create_dir_all(&dir).unwrap();
        let apps = [
            ("Blender", Some("org.blenderfoundation.blender")),
            ("Docker Desktop", Some("com.docker.docker")),
            ("Finder", Some("com.apple.finder")),
            ("Google Chrome", Some("com.google.Chrome")),
            ("Safari", Some("com.apple.Safari")),
            ("Visual Studio Code", Some("com.microsoft.VSCode")),
            ("Mail", Some("com.apple.mail")),
            ("Notes", Some("com.apple.Notes")),
            ("Calendar", Some("com.apple.iCal")),
            ("Preview", Some("com.apple.Preview")),
            ("Terminal", Some("com.apple.Terminal")),
            ("System Settings", Some("com.apple.systempreferences")),
        ];
        let mut colors = serde_json::Map::new();
        for (name, id) in apps {
            let Some(icon) = super::load(name, id) else {
                println!("{name}: not installed, skipped");
                continue;
            };
            let slug = crate::tutorial::slug(name);
            let png = STANDARD.decode(icon.data_uri.trim_start_matches("data:image/png;base64,")).unwrap();
            std::fs::write(dir.join(format!("{slug}.png")), &png).unwrap();
            println!("{name}: {slug}.png {} KB {}", png.len() / 1024, icon.color);
            colors.insert(slug, icon.color.into());
        }
        std::fs::write(dir.join("colors.json"), serde_json::to_string_pretty(&colors).unwrap()).unwrap();
    }
}
