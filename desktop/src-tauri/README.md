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
Client Tauri v2 natif : fenêtres guide/pill, suivi natif du survol, raccourcis globaux,
microphone cpal, capture régionale X11/ScreenCaptureKit/xcap, injection enigo gardée et
cycle de vie Python. `protocol.rs` embarque les schémas canoniques ; le web n'accède
à aucune clé ni socket réseau. `build.rs` compile aussi le helper Swift sur macOS.

Vérifications : `cargo check --locked`, `cargo clippy --locked --all-targets -- -D warnings`,
`cargo test --locked`. Les tests live natifs sont opt-in via pytest dans `desktop/tests/`.
Gradium est une frontière `Speech` avec implémentation explicitement sans audio.
Configuration, garde-fous et limites par OS : voir [desktop](../README.md).
