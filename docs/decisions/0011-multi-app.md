# ADR 0011 — Leçons multi-app et capteur d'accessibilité

Statut : accepté pour la conception ; contrats disponibles, routeur et backends à implémenter.

## Contexte
L'add-on Blender donne un état exact mais ne couvre pas les autres applications. La vision localise les commandes sans garantir à elle seule une preuve d'état. Pourquoi généraliser : enseigner une procédure dans toute application sans déplacer les décisions dans les clients.

## Décision
La leçon v2 exige `app` (`id`, `name`, `version`, `sensor`). Trois niveaux : add-on dédié, arbre d'accessibilité OS, puis vision Holo. Le routeur reste dans l'unique engine Python asyncio ; desktop fournit un trait Rust `AccessibilitySensor` dans `desktop/src-tauri/`, avec backends AT-SPI (`atspi`) Linux, AX macOS et UIA Windows. Pourquoi ce trait : isoler les différences OS, garder les accès natifs dans Rust et tester le moteur sur des résultats normalisés.

Le protocole additif reste en version 1.0 : `a11y.request` / `a11y.result`, `app.focus`, `highlight.rect`. Les actions exigent consentement, verrou, arrêt prioritaire et check frais après action. `agent-desktop` est seulement un backend optionnel ou une référence d'intégration, pas une dépendance imposée. Notre code existant porté garde les garde-fous communs.

## Alternatives
- Tout en vision : portable mais confiance moindre et coût cloud ; un ✓ exige encore un check frais.
- Un add-on par application : état précis, coût d'intégration trop élevé pour une couverture générale.
- Un sidecar obligatoire : ajoute packaging et permissions ; ne doit pas figer notre interface interne.
- Accès natifs depuis Python ou le web : contredit la séparation engine / desktop.

## Conséquences
Les leçons v1 Blender restent acceptées sans migration silencieuse. Les cibles persistées sont descriptives, jamais des refs ni des pixels. L'arbre est privé et non fiable ; filtrage local et aucun champ de mot de passe. Un arbre vide, incomplet ou ambigu ne prouve pas une réussite. La disponibilité réelle et la recette macOS restent à mesurer ; le schéma ne livre pas les backends.

Références : [architecture multi-app](../architecture/multi-app.md), [accessibilité native](../architecture/accessibilite-native.md), [contrat leçon](../contrats/lecon.md).
