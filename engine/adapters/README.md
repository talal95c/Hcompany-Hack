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
- `services.py` : les clients génériques transmettent les domaines et un schéma de
  documentation neutre à Linkup, ainsi que le profil complet à Jev (intentions et aide).
  Les clients du plugin conservent leurs paramètres et prompts existants.
- Leçons v1 : `engine.lesson.lesson_app` projette `blender_version` en
  `{id: blender, version, sensor: addon}` sans réécrire la leçon ni sa preuve.
- Aide générique : zone = commandes de l'adaptateur (`highlight` add-on ou `highlight.rect`
  desktop depuis les bornes a11y) ; pointeur = centre des bornes a11y sur la capture
  fenêtre, sinon Holo, point rejeté hors de la zone attendue ; démo = `replay` de
  l'adaptateur ou action consentie (`fais-le`).
- Cache de cibles : clé `app_id × app_version × taille de région × échelle UI × cible`.

## Démonstrations génériques

Le niveau 4 demande un consentement explicite par `user.intent` (source `bouton`,
intent `fais-le`, token natif). `demo_plan` sélectionne une action autorisée depuis
le check de la leçon : valeur exacte, focus ou sélection a11y ; sinon le capteur
vision localise un clic sur une capture fenêtre fraîche. Une localisation hors des
bounds disponibles ou de `visual_assert.region` est rejetée.

Le runtime sérialise les actions, annule l'attente au stop et invalide l'état avant
le check post-action. Un acquittement seul ne donne jamais de réussite. Après un
stop pendant une action, `reprends` autorise à nouveau l'observation. Une valeur
précédente a11y peut être restaurée avec un nouveau consentement (`intent: annule`),
tant que la fenêtre n'a pas changé ; les clics n'ont pas d'inverse implicite.

Le pont de recette Calc exécute ces transports avec AT-SPI et xdotool. Le desktop
natif reste distinct : `input.rs` exige encore le focus du plugin historique et
aucun dispatcher `a11y.request` n'est branché dans Rust. La recette du pont ne
valide pas cette intégration native.
