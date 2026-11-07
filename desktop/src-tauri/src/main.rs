#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let guide = app.get_webview_window("guide").ok_or("fenêtre guide absente")?;
            guide.set_ignore_cursor_events(true)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("échec du lancement desktop");
}
