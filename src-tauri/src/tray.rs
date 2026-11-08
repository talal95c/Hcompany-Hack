//! Where the app lives: a notch at the top center of the monitor work area,
//! toggled from a menu bar icon or a global shortcut. The menu bar title
//! mirrors tutorial progress.

use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};
use tauri::{
    AppHandle, LogicalPosition, LogicalSize, Manager,
    image::Image,
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
};

const TRAY_ID: &str = "holo-tutor";
const ICON_PX: u32 = 36; // 18pt @2x
pub const BAR_WIDTH: f64 = 560.0;
/// Current window width: wider while the tutorial palette is open.
static WIDTH: Mutex<f64> = Mutex::new(BAR_WIDTH);

/// While a tutorial runs the bar stays put; otherwise it hides on blur.
static STICKY: AtomicBool = AtomicBool::new(false);

/// When the panel last hid itself on blur. A click on the tray icon right
/// after that is the same gesture that caused the blur: don't reopen.
static LAST_BLUR_HIDE: Mutex<Option<Instant>> = Mutex::new(None);

/// Monochrome Rio "R" mark, drawn at runtime and used as a template image so
/// macOS tints it for light/dark menu bars.
fn icon() -> Image<'static> {
    // Mark on its 96x84 grid (bowl + leg), scaled by 0.15 and centred in a 0..18 box.
    let fit = |pts: &[(f64, f64)]| -> Vec<(f64, f64)> {
        pts.iter().map(|&(x, y)| (1.8 + x * 0.15, 2.7 + y * 0.15)).collect()
    };
    let bowl = fit(&[
        (24.0, 0.0),
        (84.0, 0.0),
        (84.0, 40.0),
        (64.0, 60.0),
        (64.0, 20.0),
        (24.0, 20.0),
        (24.0, 60.0),
        (0.0, 84.0),
        (0.0, 24.0),
    ]);
    let leg = fit(&[(24.0, 60.0), (64.0, 60.0), (96.0, 84.0), (48.0, 84.0)]);
    let s = ICON_PX as f64 / 18.0;
    let mut rgba = vec![0u8; (ICON_PX * ICON_PX * 4) as usize];
    for py in 0..ICON_PX {
        for px in 0..ICON_PX {
            // 4x4 supersampling for smooth edges.
            let mut cover = 0;
            for sy in 0..4 {
                for sx in 0..4 {
                    let x = (px as f64 + (sx as f64 + 0.5) / 4.0) / s;
                    let y = (py as f64 + (sy as f64 + 0.5) / 4.0) / s;
                    if inside(&bowl, x, y) || inside(&leg, x, y) {
                        cover += 1;
                    }
                }
            }
            let i = ((py * ICON_PX + px) * 4) as usize;
            rgba[i + 3] = (cover * 255 / 16) as u8;
        }
    }
    Image::new_owned(rgba, ICON_PX, ICON_PX)
}

fn inside(poly: &[(f64, f64)], x: f64, y: f64) -> bool {
    let mut c = false;
    let mut j = poly.len() - 1;
    for i in 0..poly.len() {
        let (xi, yi) = poly[i];
        let (xj, yj) = poly[j];
        if (yi > y) != (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi {
            c = !c;
        }
        j = i;
    }
    c
}

pub fn setup(app: &tauri::App) -> tauri::Result<()> {
    let quit = MenuItem::with_id(app, "quit", "Quitter Rio", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&quit])?;

    TrayIconBuilder::with_id(TRAY_ID)
        .icon(icon())
        .icon_as_template(true)
        .tooltip("Rio  ⌥⇧Space")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, e| {
            if e.id() == "quit" {
                app.exit(0);
            }
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                toggle_bar(tray.app_handle());
            }
        })
        .build(app)?;

    let handle = app.handle().clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(500));
        show_bar(&handle);
    });
    Ok(())
}

pub fn toggle_bar(app: &AppHandle) {
    let Some(bar) = app.get_webview_window("main") else { return };
    if bar.is_visible().unwrap_or(false) {
        let _ = bar.hide();
        return;
    }
    let just_hid = LAST_BLUR_HIDE.lock().unwrap().is_some_and(|t| t.elapsed() < Duration::from_millis(300));
    if !just_hid {
        show_bar(app);
    }
}

pub fn show_bar(app: &AppHandle) {
    if crate::autopilot::is_running() {
        return;
    }
    let Some(bar) = app.get_webview_window("main") else { return };
    let height = bar.inner_size().ok().zip(bar.scale_factor().ok()).map_or(64.0, |(s, f)| s.height as f64 / f);
    place_bar(app, height, *WIDTH.lock().unwrap());
    crate::panel::show(&bar, true, crate::panel::LEVEL_BAR);
}

/// Sizes the window to the content, flush with the work area's top edge
/// (below the menu bar). A window exactly the size of the bar never blocks clicks
/// on the app underneath.
fn place_bar(app: &AppHandle, height: f64, width: f64) {
    let Some(bar) = app.get_webview_window("main") else { return };
    let monitor = bar.current_monitor().ok().flatten().or_else(|| bar.primary_monitor().ok().flatten());
    let Some(m) = monitor else { return };
    let f = m.scale_factor();
    let wa = m.work_area();
    let (wx, wy) = (wa.position.x as f64 / f, wa.position.y as f64 / f);
    let ww = wa.size.width as f64 / f;
    let _ = bar.set_size(LogicalSize::new(width, height));
    let _ = bar.set_position(LogicalPosition::new(wx + (ww - width) / 2.0, wy));
}

#[tauri::command]
pub fn resize_bar(app: AppHandle, height: f64, width: Option<f64>) {
    let width = width.unwrap_or(BAR_WIDTH).clamp(BAR_WIDTH, 1000.0);
    *WIDTH.lock().unwrap() = width;
    place_bar(&app, height.clamp(40.0, 760.0), width);
}

#[tauri::command]
pub fn set_bar_sticky(sticky: bool) {
    STICKY.store(sticky, Ordering::SeqCst);
}

/// Bar lost focus (user clicked elsewhere): tuck it away unless a tutorial runs.
pub fn on_bar_blur(app: &AppHandle) {
    if STICKY.load(Ordering::SeqCst) {
        return;
    }
    if let Some(bar) = app.get_webview_window("main") {
        *LAST_BLUR_HIDE.lock().unwrap() = Some(Instant::now());
        let _ = bar.hide();
    }
}

/// Text next to the menu bar icon, e.g. "2/5 · Open the File menu".
#[tauri::command]
pub fn set_tray_status(app: AppHandle, text: Option<String>) {
    if let Some(tray) = app.tray_by_id(TRAY_ID) {
        let title = text.map(|t| {
            let t = t.trim().to_string();
            if t.chars().count() > 42 { format!("{}…", t.chars().take(41).collect::<String>().trim_end()) } else { t }
        });
        let _ = tray.set_title(title.filter(|t| !t.is_empty()));
    }
}

#[tauri::command]
pub fn hide_bar(app: AppHandle) {
    if let Some(bar) = app.get_webview_window("main") {
        let _ = bar.hide();
    }
}
