# desktop/src-tauri/

## Responsabilité
Backend Rust natif.

## Entrées
IPC WebView et commandes autorisées.

## Sorties
fenêtres, permissions, capture, hotkey, enigo et sidecar.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/desktop-tauri.md) et [guide des agents](../../AGENTS.md).

## État et validation
Scaffold Rust Tauri v2 : `cargo check --locked`. `build.rs` génère le contexte à partir de `tauri.conf.json`, qui active macOSPrivateApi et la fenêtre guide transparente. `src/main.rs` rend la fenêtre click-through. Les autres backends natifs restent à implémenter. Gradium TTS local côté Rust est seulement prévu : voir [desktop](../README.md).
