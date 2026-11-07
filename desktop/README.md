# desktop/

## Responsabilité
App Tauri v2 et cycle du sidecar.

## Entrées
ordres engine et entrées utilisateur.

## Sorties
capture exclue, injection, pointer/pill/✓.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../docs/architecture/desktop-tauri.md) et [guide des agents](../AGENTS.md).

## État et validation
Scaffold Tauri v2 disponible : fenêtre guide transparente, always-on-top et click-through ; page HTML locale sans moteur connecté. Vérification : `cargo check --locked` dans `desktop/src-tauri/`. Le packaging est désactivé ; aucune permission native, capture, injection, pill ou sidecar n'est encore implémenté. La compilation Linux ne valide pas le comportement macOS.

## Module vocal à venir
Gradium TTS sera intégré ultérieurement côté Rust, localement dans desktop. Ce jalon ne contient ni module exécutable, ni modèle, ni appel TTS ; ce choix remplace la question ouverte du fournisseur dans le design initial. Aucun changement aux autres services IA cloud. Les détails de fonctionnement et dépendances de Gradium devront être validés avant intégration.
