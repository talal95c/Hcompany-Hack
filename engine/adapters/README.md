# Adaptateurs d'application

Le cœur de l'engine (runtime, policy, cache, checks génériques) ne connaît que l'interface
`AppAdapter` (`base.py`). Chaque capteur fournit : état (`snapshot`/`refresh`), faits de
préconditions (`facts`), zone (`zone`), dévoilement (`reveal`/`reveal_target`), démo
(`replay`/`undo_replay`) et zone attendue d'une cible (`expected_rect`).

| Adaptateur | Capteur | Source | Checks lisibles |
|---|---|---|---|
| `BlenderAdapter` | `addon` | canal TCP add-on (événements de scène, régions) | `blender.*` et noms v1 |
| `AccessibilityAdapter` | `accessibility` | `a11y.request`/`a11y.result` du desktop (AX, UIA, AT-SPI) | `element_*`, `window_title` |
| `VisionAdapter` | `vision` | capture fenêtre (`capture.request` scope `window`) + `HoloVerifier` | `visual_assert`, `window_title` |

- `router.py` : ordre `auto` = addon → accessibilité → vision ; `accessibility` replie vers
  la vision sur `APP_NOT_FOUND`, `PERMISSION_DENIED`, `TIMEOUT`, `AMBIGUOUS_TARGET`
  ou arbre incomplet ; `STALE_REF` refait une seule résolution avant ce repli, jusqu'au prochain
  `app.focus`. Un check exact lu en vision reste `unknown` : aucun ✓ inventé.
- `profiles/*.json` : vocabulaire STT, contexte Jev, domaines de documentation et noms de
  processus par `lesson.app.id` ; une application inconnue reçoit un profil neutre.
- Leçons v1 : `engine.lesson.lesson_app` projette `blender_version` en
  `{id: blender, version, sensor: addon}` sans réécrire la leçon ni sa preuve.
- Aide générique : zone = commandes de l'adaptateur (`highlight` add-on ou `highlight.rect`
  desktop depuis les bornes a11y) ; pointeur = centre des bornes a11y sur la capture
  fenêtre, sinon Holo, point rejeté hors de la zone attendue ; démo = `replay` de
  l'adaptateur ou action consentie (`fais-le`).
- Cache de cibles : clé `app_id × app_version × taille de région × échelle UI × cible`.
