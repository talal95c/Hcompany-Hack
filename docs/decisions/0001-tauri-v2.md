# ADR 0001 — Application desktop native

Statut : accepté pour la conception ; implémentation et tests à venir.

## Contexte
Une interface transparente doit coexister avec Blender sans absorber les clics.

## Décision
Tauri v2, dossier desktop/, Rust pour fenêtres, capture, permissions, hotkey et enigo ; web pour pointer/pill/✓ ; Python sidecar. macOS d'abord, compatible Windows.

## Alternatives
Electron ; interface entièrement Python.

## Conséquences
Deux fenêtres et capture par exclusion explicite ; validation native indispensable.

Référence : [architecture](../architecture/vue-ensemble.md).
