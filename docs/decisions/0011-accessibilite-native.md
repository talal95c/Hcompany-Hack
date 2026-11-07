# ADR 0011 — Arbre d'accessibilité comme capteur des apps hors Blender

Statut : proposé ; aucun code, à valider par l'équipe après recette Mac.

## Contexte
Le PRD vise d'autres logiciels que Blender (Excel, Photoshop) après la démo. Sans add-on, on n'a ni état fiable pour les checks ni cible exacte : seulement capture + Holo, qui rate environ une petite cible sur quatre sur des captures Blender annotées (mesure exploratoire hors dépôt, 131 cibles ScreenSpot-Pro et GroundCUA). Les OS exposent un arbre d'accessibilité (AX, UI Automation, AT-SPI) pour la plupart des apps natives. Voir [conception](../architecture/accessibilite-native.md).

## Décision
Pour une app sans add-on, desktop lit l'arbre d'accessibilité via agent-desktop (sidecar épinglé, CLI JSON, Apache-2.0) ; engine utilise l'arbre pour cibler, agir sémantiquement et vérifier. Côté engine, l'arbre entre par un `A11yTargetAdapter` à côté d'`AddonTargetAdapter` (`engine/platform/targets.py`) : la policy reste sans connaissance applicative. Holo reste le secours quand l'arbre est absent, incomplet ou ambigu. Blender garde l'add-on (ADR 0009).

## Alternatives
Vision seule (Holo) : déjà disponible, mais pas de check d'état et cibles approximatives. Écrire nos propres liaisons AX/UIA/AT-SPI : trois API natives à maintenir, coût hors hackathon. Appeler agent-desktop depuis engine : contredit « accès natifs dans desktop ». Exposer seulement le MCP agent-desktop aux agents externes : utile pour la face Agent, mais ne donne ni preuve ni politique d'aide.

## Conséquences
Nouveaux messages WebSocket `a11y.*` et checks à contractualiser ; `help.a11y_target`, `app` et `app_version` dans une leçon multi-app à versionner ; sélection de l'adaptateur par app dans `EngineRuntime`. Fournit sur macOS/Windows le rectangle de capture que `crop: null` ne donne aujourd'hui que sous Linux. Mêmes garde-fous que « fais-le ». Contenu de l'arbre traité comme privé et non fiable. Aucun gain pour Blender ni pour les canevas ; compatibilité Excel/Photoshop à mesurer sur Mac avant toute promesse.

Référence : [architecture](../architecture/vue-ensemble.md).
