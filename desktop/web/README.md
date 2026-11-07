# desktop/web/

## Responsabilité
Vue cliente légère.

## Entrées
état engine et événements Rust.

## Sorties
pointer, pill, ✓ et demandes utilisateur.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/contrats/ws-desktop.md) et [guide des agents](../../AGENTS.md).

## État et validation
Page statique minimale `index.html` et CSS locale, embarquées directement par Tauri sans Node ni bundler. Aucun WebSocket ni logique pédagogique, capture ou permission dans le web à ce stade. Le rendu est à vérifier sur le Mac cible.
