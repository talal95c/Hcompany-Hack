# desktop/

## Responsabilité
App Tauri v2 et cycle du sidecar.

> Le front principal est désormais [`h-tutor/`](../h-tutor/README.md). `desktop/` reste
> le client branché sur l'engine Python, en attendant que h-tutor y soit raccordé.

## Entrées
ordres engine et entrées utilisateur.

## Sorties
capture exclue, injection, pointer/pill/✓.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../docs/architecture/desktop-tauri.md) et [guide des agents](../AGENTS.md).

## Exécution
Depuis `desktop/src-tauri/`, `cargo run --locked`. Le moteur Python doit être installé dans
un environnement Python 3.11 avec l'extra `desktop`. Définir `HCOMPANY_PYTHON` sur son
exécutable et, si nécessaire, `HCOMPANY_ENGINE_DIR` sur la racine du dépôt. Aucun Node
ni serveur web n'est nécessaire. Linux nécessite les bibliothèques Tauri documentées
dans le guide d'environnement, plus `libasound2-dev` (cpal), `libxkbcommon-dev` et une
session X11. Wayland échoue explicitement, sans contournement du portail de sécurité.

Rust lance `python -u -m engine` avec `ENGINE_HOST=127.0.0.1`, un `ENGINE_PORT`
éphémère, `ENGINE_SESSION_ID` et `ENGINE_SESSION_TOKEN`. Il attend au plus 10 s la ligne
`ENGINE_READY {"ws_port":1234,"addon_port":1235}` avant la connexion WebSocket.
Le client natif utilise `Authorization: Bearer …` et `Origin: tauri://localhost`.
Le point d'entrée de production `engine/__main__.py` branche les adaptateurs cloud
selon les clés présentes dans l'environnement. `ENGINE_LESSON` sélectionne la leçon prouvée ;
`ENGINE_HOLO_MODEL` configure le modèle de pointage (défaut `holo4-27b`).
La fixture de test ci-dessous n'est jamais un fallback.
Le transport attend l'accusé `frontend_ready` des deux fenêtres, envoyé après
l'installation de leurs listeners : la première instruction ne dépend pas de la
vitesse de chargement des WebViews. Un échec de listener reste visible et ne lance
pas le moteur ; l'arrêt peut toujours annuler cette attente.
`ENGINE_WS_URL=ws://127.0.0.1:…/` permet de se connecter à un moteur déjà lancé ; les
adresses distantes sont refusées. Aucun jeton de transport ni clé cloud dans la WebView.

## Interface et garde-fous
- `guide` couvre le moniteur courant, transparent, always-on-top et toujours click-through.
  `pointer` affiche aussi la région capturée ; la cible expire au plus après 5 s.
  Rust masque la surface native quand elle est vide, arrêtée ou expirée : le masquage
  DOM seul laisse parfois des pixels sur X11 sans compositeur. Les expirations natives
  sont versionnées pour ne jamais masquer une cible plus récente.
  Un ✓ exige un ordre `success` engine avec révision de scène non nulle ; le desktop
  ne décide jamais de la réussite pédagogique.
- `pill` possède un suivi natif du curseur (cadence 25 ms, **paramètre**, non mesure de
  latence). La fenêtre reçoit les entrées seulement quand le curseur est dans ses limites.
  Le panneau propose permissions, région de capture explicite, texte, consentement et arrêt.
- Voix : maintenir `Ctrl+Shift+Space` ou le bouton micro. Le raccourci est configurable
  via `HCOMPANY_PTT_HOTKEY`. cpal capture le vrai périphérique ; conversion mono
  PCM signé 16 bits little-endian, 16 kHz, chunks de 100 ms avec dernier chunk partiel.
  La file est bornée ; saturation/interruption donne une erreur visible, jamais de faux audio.
- `Ctrl+Shift+Escape` arrête prioritairement, annule le consentement et invalide les
  captures. Aucun appui de touche maintenu n'est exposé ; enigo libère ses touches à la sortie.
- « Fais-le » exige une case de consentement explicite (60 s), une connexion active,
  une capture fraîche (au plus 10 s), un verrou exclusif et le focus de l'application
  ciblée au consentement. Chaque
  action consomme sa capture ; il faut en partager une nouvelle avant l'action suivante.
  Les seuls gestes acceptés sont move/click normalisés, navigation, caractères simples,
  libellés alphanumériques et scroll borné. Pas de modificateurs système, shell ni code.
- Une coupure invalide cible, capture et consentement. Reconnexion avec backoff borné,
  hello et permissions ; jamais de replay d'entrée. Un crash du processus impose un
  redémarrage explicite. Quitter envoie `shutdown\n`, SIGTERM sur Unix, puis attend 3 s
  (**délai de grâce configuré**) avant arrêt forcé.

## Capture et repères
La région demandée est entière, limitée à 1 Mpx et contenue dans un seul moniteur.
La transmission contient seulement un PNG recadré sous `data:image/png;base64,…`.
Pas de capture complète implicite, d'enregistrement disque ni de conservation par défaut.

- macOS 14+ : helper Swift compilé par `build.rs`, ScreenCaptureKit avec exclusion
  explicite de l'application/fenêtres du processus Rust (pas seulement content protection).
  Screen Recording / Accessibility / Microphone sont contrôlés séparément ; un refus
  n'empêche pas l'entrée texte. Les explications Microphone sont intégrées au helper.
- Linux : X11, lecture native de la région ; nos deux surfaces sont masquées durant
  la capture puis réaffichées dans l'ordre guide, puis pill, pour garder les commandes
  au-dessus du guide sans prendre le focus. La pill est aussi relevée nativement et
  un guide expiré n'est pas réaffiché. Le délai compositor de 80 ms est une **temporisation
  configurée**, pas une mesure ni une garantie d'exclusion sur tous les compositeurs.
- Windows : xcap, masquage des surfaces et protection du contenu en défense supplémentaire.
  Les tests Windows natifs et l'exclusion sous compositeur restent à réaliser.

Le point Holo [0,1000] est ramené au crop physique puis au bureau natif, borné au dernier
pixel. macOS tient compte de l'origine logique et du facteur Retina par moniteur ; X11
et Windows utilisent les coordonnées physiques d'injection natives. Le CSS utilise
le facteur de la fenêtre Tauri, séparément. Les crops transfrontières sont refusés.
Les conversions Blender (origine bas-gauche) résident dans `engine/platform/` et
inversent Y une seule fois.

## Contrat v1 et IPC
Tous les messages WebSocket entrants et sortants sont validés par les JSON Schema
embarqués de `contracts/` ; limites de taille, session, génération, déduplication et
expiration sont contrôlées côté Rust. Les tests Python utilisent aussi `jsonschema`.
IPC web → Rust : `permission_status`, `permission_request`, `capture_region`,
`user_intent`, `consent_grant`, `ptt`, `stop_actions`, `sidecar_start`, `sidecar_stop`.
Les commandes sensibles refusent une fenêtre autre que `pill`.

Conventions acceptées pour le contrat v1 (sans modifier ses schémas) :
1. Capture locale explicite `capture_region` ou demande engine `capture.request`.
   `scope="window"` avec `app` capture la fenêtre résolue ; la réponse est `capture.result`.
2. Consentement via `user.intent`, source `bouton`, dont `text` est la chaîne JSON
   `{"intent":"fais-le","consent_token":"<uuid>"}`. Le moteur doit réutiliser ce token
   dans `input.action`. Le token ne retourne pas dans la WebView.
3. Format d'action local strict, par exemple
   `{"type":"click","x":500,"y":500,"button":"left"}` ou `{"type":"key","key":"tab"}`.
4. L'image inline est l'unique buffer éphémère ; aucun serveur HTTP de captures.

## Tests
```sh
# Racine du dépôt, environnement Python 3.11 activé
ruff check engine/platform desktop/tests
pytest -q engine/platform desktop/tests -m 'not live'
node --test desktop/tests/frontend.test.cjs # tests UI unitaires, Node 18+ optionnel
DISPLAY=:0 HCOMPANY_LIVE=1 pytest -q -s desktop/tests -m live
# Depuis desktop/src-tauri/
cargo check --locked
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked
cargo build --locked
```
Le marqueur live lance les intégrations Rust réelles : capture native PNG, handshake
WebSocket authentifié et capteur Calc. Sous Linux, la fixture démarre son propre Xvfb
(affichage libre), bus D-Bus/AT-SPI et Calc avec profil/document jetables. Aucun chemin
personnel ni script extérieur au dépôt n'est requis. Dépendances : Xvfb, dbus-run-session,
at-spi2-core, LibreOffice Calc avec son plugin GTK3, xdotool, Python et Cargo.
Sans `HCOMPANY_LIVE=1` ou sans les exécutables requis, le test Calc est ignoré.

**Limite explicite :** le test Calc utilise le fallback Rust ignoré, pas l'application
Tauri connectée à une fixture engine. Les durées `*_handler_ms` mesurent les handlers
Rust, pas un aller-retour WebSocket inter-processus. La découverte `app.focus` et la
capture native sont vérifiées localement ; leur livraison par le vrai client Tauri
et la validation Python/jsonschema de ses messages restent à couvrir. Le test transport
distinct vérifie le handshake et les messages réels de son loopback.
Ces tests ne prétendent pas valider les
services cloud (aucun appel cloud dans ce client) ni une leçon complète. La CI existante
compile Linux et macOS ; Linux CI doit installer `libasound2-dev`.

`desktop/tests/ws_probe.py` est le petit serveur fixture explicitement réservé au test
de rendu natif sous Xvfb. Il valide le protocole, reçoit une vraie capture, renvoie une
cible et tente une action sans consentement pour vérifier son rejet. Il n'est jamais
choisi automatiquement en production et ne simule ni cours ni service cloud.
Le texte `probe-success` déclenche explicitement un ordre `success` de fixture
pour tester le rendu du ✓, sans prétendre prouver une opération Blender.
`HCOMPANY_ENGINE_DIR=desktop/tests/sidecar_fixture` (chemin absolu recommandé),
avec `HCOMPANY_PROBE_OUTPUT` fixé sur un dossier d'artefacts, permet de vérifier
le même serveur lancé comme subprocess `python -m engine` et son arrêt réel.
La compilation seule ne valide pas les permissions, la capture et l'injection macOS.

## Capteur d'accessibilité générique
Le client natif expose `a11y.request` / `a11y.result` : snapshot borné, recherche fraîche,
lecture d'une référence opaque et actions sémantiques gardées. Les références incluent
l'identifiant de snapshot ; quatre snapshots sont retenus pendant 30 s (limites
configurées). Les valeurs sécurisées sont exclues et les autres valeurs ne sont jamais
loguées. Un timeout avec des nœuds utilisables rend un résultat partiel, pas une preuve
d'absence ; voir les [détails du capteur](src-tauri/src/a11y/README.md).

Les tiers d'observation sont : état structuré de l'add-on quand disponible,
accessibilité native, puis vision sur capture minimale. Python garde les décisions
pédagogiques ; le natif ne conclut pas à la réussite. Linux AT-SPI/X11 est vérifié avec
Calc ; macOS AX et Windows UIA sont implémentés, mais leur exécution native reste à
valider. Le schéma protocole est préchauffé sur un thread au démarrage de l'application.
Les parcours ont un budget configuré de 3 s, 2 000 nœuds, profondeur par défaut 32 ;
les appels Linux d'observation sont bornés à 500 ms. Wayland et les arbres virtuels
non bornables ne sont pas présentés comme complètement observés.

Mesures Linux/Xvfb/GTK3 avec le test privé (5 snapshots, schéma préchauffé) :
snapshot p50 812,377 ms, p95 878,204 ms (nearest-rank) ; recherche A1 1 038,473 ms,
recherche Bold 853,854 ms, get 10,030 ms, capture fenêtre 366,734 ms.
Ce sont des durées locales Rust mesurées, non des latences engine/Tauri de bout en bout.
Le transport loopback distinct mesure 1 022,06 ms, initialisation comprise ; ces
mesures ne valident pas la livraison WebSocket des opérations d'accessibilité.

## Module vocal à venir
`src-tauri/src/tts.rs` définit `Speech` et `NoSpeech`. Le no-op retourne explicitement
« synthèse indisponible » et n'émet aucun son ; `say` affiche uniquement le texte.
TODO Gradium : implémenter `Speech` côté Rust, vérifier modèle, licence, dépendances,
annulation et lecture réelle avant activation. Aucun fallback audio factice ni appel
Gladia TTS. Les autres services IA cloud ne changent pas.
