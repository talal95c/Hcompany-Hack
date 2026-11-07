# Accessibilité native — capteur générique

Statut : contrats disponibles, implémentation native à venir. [ADR 0011](../decisions/0011-multi-app.md) · [architecture multi-app](multi-app.md) · [explication produit](../extension-apps-natives.md).

## Problème et brique retenue
L'[add-on Blender](addon.md) fournit l'état bpy. Pour une app métier, Excel ou Finder, l'OS peut exposer un arbre : rôle, nom, valeur, états, rectangle. Ce capteur complète la vision sans remplacer l'état spécialisé.

Le point d'intégration est un trait Rust `AccessibilitySensor` dans `desktop/src-tauri/` : backends AT-SPI via `atspi` sur Linux, AX sur macOS, UI Automation (UIA) sur Windows. Le trait normalise snapshots, recherche, lecture et actions. `agent-desktop` peut servir de backend optionnel ou de référence ; aucun sidecar n'est imposé. Les observations historiques d'un outil ne constituent pas une recette de nos backends.

## Où ça se branche
| Composant | Responsabilité |
|---|---|
| `desktop/src-tauri/` | implémenter le trait et les permissions, focus, conversions physiques ; consentement, verrou, arrêt prioritaire pour les actions |
| `engine/` | router le capteur par app, résoudre les cibles et décider des secours |
| `engine/checks/` | checks déterministes sur arbre frais, pass/fail/unknown |
| `prep/ui_map/` | préparer rôles, noms et chemins descriptifs, pas des refs persistées |
| `agent/` | ne proposer que les leçons prouvées pour l'app ; couverture multi-app à implémenter |
| `bench/` | mesurer succès, latence, taille des arbres et fréquence du secours vision |

Le protocole réel est `a11y.request` engine → desktop avec `op: snapshot|find|get|action`, puis `a11y.result` desktop → engine. `app.focus` annonce l'app active. Le [contrat WebSocket](../contrats/ws-desktop.md) précise les payloads fermés. La [leçon v2](../contrats/lecon.md) possède déjà `app` ; ce n'est plus un ajout futur au schéma.

## Décrire, résoudre, vérifier
Conformément à l'[ADR 0010](../decisions/0010-cibles-descriptives.md), stocker description, rôle, nom et chemin d'ancêtres. En direct : snapshot frais → recherche unique → ref → action → nouveau snapshot → check. Une ref n'est valable que dans son snapshot ; ne jamais la stocker dans la leçon.

`STALE_REF` autorise une seule nouvelle résolution ; ambiguïté, arbre incomplet ou app absente déclenchent le secours vision. Refus de permission : demander l'accès puis vision si nécessaire. Les [règles du routeur](multi-app.md) empêchent toute validation sur un arbre incomplet.

## Aide et délégation
Le palier ② utilise `highlight.rect` dans l'overlay sur les bounds physiques ; `highlight` reste réservé à l'add-on. Le palier ③ convertit le centre du rectangle vers les millièmes de la capture pour `pointer`. « Fais-le » utilise une action sémantique autorisée (`press`, `set_value`…), avec jeton de consentement, une seule action à la fois, puis check frais. Aucun accès natif depuis le web ni décision déplacée dans Rust.

## Confidentialité et limites
L'arbre contient potentiellement cellules, messages et noms de documents : sous-arbre filtré, aucune valeur dans les logs, rien au cloud par défaut. Noms et valeurs sont non fiables ; aucun mot de passe ni champ sécurisé. Le secours Holo reçoit seulement le recadrage minimal consenti, jamais automatiquement tout l'arbre.

Canevas et interfaces dessinées sur mesure peuvent être absents. Ne pas supposer que Blender expose un arbre utilisable : l'add-on reste son capteur privilégié. Chromium/Electron et les permissions OS demandent une recette spécifique. Un arbre vide ne démontre pas l'absence d'une cible si la couverture est incomplète.

## Validation attendue
Fixtures nominales, vides et erreurs ; refs périmées, ambiguïté, timeout, reconnexion, arrêt et absence de valeurs dans les logs. Recette Mac : Excel (valeur de cellule et bouton du ruban), Finder, Photoshop (couverture du canevas), refus puis accord de permission. Mesures dans `bench/results/` ; ni build Linux ni validation JSON ne prouvent le fonctionnement macOS.
