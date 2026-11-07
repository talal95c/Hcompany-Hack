# Benchmarks réels

Depuis la racine du dépôt, Python 3.11 :

```sh
uv python install 3.11
uv venv --python 3.11 ~/.venvs/hcompany-hack
uv pip install --python ~/.venvs/hcompany-hack/bin/python -e '.[holo,jev,gladia,bench]'
source ~/.venvs/hcompany-hack/bin/activate
python -m bench addon --operations 50 --out bench/results
pytest -q bench/tests
pytest -q -m live bench/tests -k addon
ruff check .
```

`live` est ignoré par défaut ; `-m live` ou `BENCH_LIVE=1` l'active.
Les sept suites sont disponibles ; `all` les exécute successivement avec leurs clés.
Options addon : `--blender /opt/blender/blender`, `--timeout 60`, `--operations 50`.

## Pointeurs Calc

```sh
python -m bench pointer
python -m bench pointer --models holo4-27b holo4-35b-a3b --repeats 3
pytest -q bench/tests -m live -k pointer
```

Même environnement privé et dépendances que `a11y`/`verify`, clé `HAI_API_KEY`.
Neuf contrôles exposés par Calc : Gras, Italique, Souligné, alignement horizontal
centré, tri ascendant, graphique, choix de fonction, retour à la ligne et fusion
sans centrage. Descriptions françaises/anglaises enregistrées, jamais le seul
nom accessible. Trois répétitions par défaut : 27 recherches AT-SPI et 27 appels
Holo, modèle `holo4-27b`. Client de localisation, schéma, thinking désactivé,
pacing et retries réutilisés de `bench.holo` sans modification.

Capture fraîche de la fenêtre par cible/répétition, utilisée pour les deux
méthodes ; géométrie et bounds relus avant toute évaluation/clic. Capture PNG
réduite, origine et dimensions physiques originales conservées : millièmes =
1000 × (point écran − origine fenêtre) / dimensions originales. Conversion
inverse et arrondi au pixel pour le clic ; aucune multiplication DPI.

Le hit géométrique seul est auto-référencé pour AT-SPI. Sur les trois contrôles
de formatage, **chaque méthode clique réellement** avec xdotool ; la lecture
AT-SPI doit montrer exactement l'inversion attendue sans changement des deux
autres contrôles. Les états initiaux sont ensuite restaurés et relus. Le taux
fonctionnel utilise tous ces essais, même un pointeur absent ; les six autres
contrôles ne sont pas cliqués (pas de prétendue validation fonctionnelle).

`pointer_assets/` conserve captures, SHA-256, géométries, noms et prompts ;
`pointer-calls.jsonl` conserve chaque point, bounds, preuves avant/après/restaurées,
requêtes HTTP et latences. Distances p50/p95 en pixels physiques. Latence AT-SPI :
recherche + conversion, IPC/client système inclus ; Holo : dernière tentative
HTTP, séparée du mur incluant pacing/retries. Capture et clic hors latence de
localisation. Miss/clic sans effet = résultat incorrect ; erreur HTTP/parse =
échec. Les limites du dataset synthétique et de l'auto-référence restent visibles.

## Assertions visuelles Holo

```sh
python -m bench verify
python -m bench verify --reuse-assets --models holo4-27b holo4-35b-a3b --repeats 2
pytest -q bench/tests -m live -k verify
```

Requiert `HAI_API_KEY` dans l'environnement et les extras `bench,holo`. Même
dépendances système que `a11y`, plus Blender graphique et ImageMagick. La première
commande crée vingt scènes réelles (dix Calc, dix Blender), quarante questions
fermées équilibrées par scène, puis deux répétitions : quatre-vingts appels par
modèle. Chaque lancement Calc utilise un profil vierge ; A1 est focalisée par son
rectangle AT-SPI, puis ne reçoit que `424242`. Les boutons Gras/Italique/Souligné
sont actionnés et leurs états AT-SPI lus avant **et après** capture. Les questions
portent sur l'état des boutons, pas sur une inférence du style du texte. Blender
écrit les faits bpy dans une session privée Xvfb ; les captures externes sont
acquittées avant de passer à la scène suivante. Aucun label n'est produit à l'œil.

`results/verify_assets/manifest.json` conserve faits, versions, questions, labels,
SHA-256 et dimensions ; les PNG sont réduits à 1280×900 maximum. Les questions Calc
emploient la région supérieure de la fenêtre en millièmes. `--reuse-assets`
vérifie intégrité, chemins, labels et équilibre sans relancer d'application.
Les labels ne sont jamais transmis au modèle. Le client SDK utilise `extra_body`
pour le schéma JSON et `chat_template_kwargs.enable_thinking=false`, un Pacer
commun à tous les appels du run, deux secondes initialement et dix tentatives
maximum avec les cooldowns existants. Une erreur d'authentification arrête le run.

`verify-calls.jsonl` conserve modèle/question/répétition, réponse structurée brute,
statut, détails des tentatives, waits et durées murales ; aucune clé ni image en
base64. Seuil de confiance 0,8 : les réponses sous ce seuil deviennent unknown.
Accuracy sur **tous** les appels ; unknown et erreurs comptent comme incorrects.
Précision/rappel yes : dénominateur nul représenté par null. Matrices de confusion,
latences p50/p95, échecs par app, modèle et global dans JSON/Markdown. La latence
principale inclut pacing et retries ; la dernière tentative HTTP est séparée.
Les répétitions ne sont pas indépendantes et ce petit dataset contrôlé ne mesure
ni l'exécution du moteur ni une capacité générale sur les applications. Le test
live court vérifie le protocole sur deux questions par application, pas un seuil
de qualité du modèle ; sans clé il est ignoré proprement.
Installation Blender 4.5.9 LTS : voir `docs/environnement-dev.md`.
Exécuter depuis la racine (bench n'est pas inclus dans les packages distribués du socle).

## Accessibilité Calc / AT-SPI

```sh
python -m bench a11y
python -m bench a11y --iterations 30 --max-nodes 1200 --max-depth 12 --timeout 15
pytest -q bench/tests -m live -k a11y
```

Dépendances Ubuntu : `libreoffice-calc`, **`libreoffice-gtk3`**, `at-spi2-core`,
`python3-pyatspi`, `xvfb`, `dbus-x11`, `xdotool`. Aucun secret cloud nécessaire.
La sonde utilise `/usr/bin/python3` (pyatspi système, Python 3.10 sur cette VM),
pas les bindings du venv Python 3.11. Elle émet des lignes JSON validées par
`a11y_session.parse_response`.

`A11ySession` expose une session réutilisable : contexte async, `launch_calc()`,
`find_element(name)` → rôle/nom/rectangle `[x,y,largeur,hauteur]` en pixels écran
et états. `request()` expose également snapshot, découverte des boutons,
écriture de la seule valeur de test et lecture d'A1. Aucun accès au bureau existant.
Chaque session lance `dbus-run-session`, un Xvfb sur display alloué par `-displayfd`
(1600 × 1000), un runtime privé 0700, le lanceur de bus AT-SPI et le registre,
puis `localc --norestore --nologo` avec un profil neuf. Environnement :
`GTK_MODULES=gail:atk-bridge`, `SAL_USE_VCLPLUGIN=gtk3`, `NO_AT_BRIDGE=0`,
`GNOME_ACCESSIBILITY=1`. Le display est propagé à l'activation D-Bus.

Le lancement poll jusqu'à 60 s : apparition sur le bus puis fenêtre exposée.
Un nouveau client système relit desktop/application à chaque poll et requête ;
aucun objet AT-SPI de l'application vide au démarrage n'est conservé. Les mesures
séparent le parcours/recherche/lecture AT-SPI de `ipc_ms` (processus Python,
connexion bus et transport JSON inclus). Les percentiles nearest-rank viennent
de `bench.common.statistics`, avec minimum ajouté localement.

Le snapshot parcourt en largeur sous limites de profondeur/nœuds ; la feuille
virtuelle ne peut pas être énumérée exhaustivement. Les comptes par rôle,
profondeur et troncature sont conservés à chaque itération. La recherche exacte
des boutons évite menus et cellules ; les noms réellement découverts, bounds et
états sont dans le rapport JSON. `Select Function`, si choisi à défaut de Sum,
désigne le choix de fonction, pas une validation de la commande AutoSum.
Chaque itération saisit uniquement `424242` via xdotool puis lit A1 via AT-SPI ;
seul le booléen de comparaison est enregistré, pas d'autres valeurs de cellules.
Aucune capture d'écran.

Sorties remplacées : `bench/results/a11y.json` et `a11y.md`. Échecs et raisons
sont conservés, sans les compter parmi les succès. RPC AT-SPI bornés à 1,5 s
(3 s au démarrage RPC), requêtes subprocess et parent également bornées.
Après crash/hang : nouvelle session et nouveau profil pour les itérations
suivantes ; trois échecs de lancement interrompent la suite. Option de diagnostic
`--restart-each-iteration`, et `--vcl-plugin gen` pour comparaison explicite
(le plugin gen ne garantit pas de pont AT-SPI). Tous les processus de la session
sont arrêtés à la sortie ou à l'annulation.

### Relevé conservé et limites de robustesse

Sur LibreOffice 7.3.7.2 / Ubuntu 22.04, le relevé par défaut a terminé **30/30**
itérations dans une seule instance Calc : zéro échec, 30 lectures A1 correctes,
210 recherches réussies. Noms exposés : `Bold`, `Italic`, `Underline`,
`Align Center`, `Sort Ascending`, `Select Function`, `Chart`.
Snapshot p50/p95 : 332,588 / 437,167 ms ; recherche : 53,828 / 82,076 ms ;
lecture A1 avec localisation de la table : 360,676 / 502,835 ms.
Les 30 arbres atteignent la limite de 1 200 nœuds (profondeur observée 9) :
il s'agit d'une taille tronquée, jamais d'une taille exhaustive.

La première tentative sans `libreoffice-gtk3` ne trouvait pas Calc sur le bus.
Avec gtk3 mais objets réutilisés au démarrage, l'application était visible avec
zéro enfant et l'attente de fenêtre expirait. La configuration fonctionnelle
ci-dessus combine `GNOME_ACCESSIBILITY=1`, attente jusqu'à 60 s et clients courts
qui rechargent desktop/application. Ce relevé ne permet pas d'attribuer le gain
à une variable isolée. Aucun abort après snapshot n'a été observé sur ces 30
itérations ; les redémarrages automatiques n'ont donc pas été nécessaires.
`gen` et la désactivation Java ne sont pas mesurés ni revendiqués comme correctifs.

## Méthode

La sonde `bench/blender/probe.py` est autonome, sans import de l'add-on ou du moteur.
Listener asyncio loopback, port éphémère, session UUID, JSON UTF-8 lignes validé
contre les schémas de `contracts/`. Ligne vide ignorée ; JSON malformé ou événement
invalide comptabilisé. Déconnexion incomplète, timeout et erreur Blender font échouer la suite.

Blender ajoute réellement un cube par opération et émet directement operator/scene/heartbeat.
Il traite ensuite request_snapshot et émet snapshot + command.result.
RTT applicatif inclut création du snapshot et validation côté listener.
Réception horodatée avant validation. One-way suppose Linux et CLOCK_MONOTONIC partagé
entre processus sur le même hôte, pas une synchronisation inter-hôtes.
Cela exclut les observateurs du véritable add-on : ce n'est pas la latence produit complète.
Startup : lancement du processus → hello (perf_counter).
Percentiles nearest-rank : rang ceil(n*p/100), entrée vide = null.

Les fichiers `<suite>.json` et `<suite>.md` sont remplacés à chaque exécution.
JSON conserve événements bruts, commandes, RTT bruts, compteurs, configuration,
commit avant mesure, UTC, CPU, hôte, Python et version Blender.
Aucune précision d'apprentissage n'est revendiquée pour cette sonde de transport.

## Capture UI réelle

```sh
xvfb-run -s '-screen 0 1920x1080x24' /opt/blender/blender --factory-startup --python-expr "import runpy; runpy.run_path('bench/blender/ui_smoke.py')"
```

La minuterie capture une fenêtre Blender non-background dans `bench/results/ui-smoke.png`,
conserve la géométrie area/region dans `bench/results/ui-geometry.json`, puis quitte.
Également disponible via `--python bench/blender/ui_smoke.py`.

Le screenshot bpy était noir sur cette VM. Les artefacts de ce smoke ont été retirés ;
utiliser les captures externes ci-dessous pour une preuve UI exploitable.

## Holo4 : localisation d'éléments

```sh
# HAI_API_KEY doit être présente dans l'environnement, jamais dans les fichiers.
python -m bench holo
python -m bench holo --models holo4-35b-a3b --concurrency 1 --timeout 30
pytest -q -s -m live bench/tests -k holo
```

La suite appelle réellement `https://api.hcompany.ai/v1/models`, puis chat/completions.
Les deux modèles Holo4 sont testés par défaut. Elle suit le format documenté par H :
<https://hub.hcompany.ai/models-api/element-localization> et
<https://hub.hcompany.ai/models-api/chat-completions> : message système stable,
image puis description bilingue, structured_outputs JSON x/y [0,1000], température 0,
thinking désactivé. Aucun raisonnement n'est utilisé pour déterminer la vérité terrain.

### Images et vérité terrain

`holo_assets.py` lance un Xvfb privé, Blender OpenGL avec rendu logiciel Mesa 4.5,
un XDG_RUNTIME_DIR privé, puis `bench/blender/render_holo.py`. La disposition factory
conserve toolbar, N panel et tool settings visibles. Le splash initial est désactivé.
Après plusieurs redraws, ImageMagick `import -window root` capture réellement le display.
Blender occupe exactement le display à (0,0), sans décorations ni redimensionnement :

| Échelle UI | Dimensions PNG |
|---|---|
| 1.0 | 1920 × 1080 |
| 2.0 | 3840 × 2160 |

Les PNG RGB optimisés sans perte et les géométries RNA sont conservés dans
`bench/results/holo_assets/scale-{1,2}.{png,json}` (~1,5 Mo de PNG au total).
Images et boîtes superposées ont été vérifiées visuellement. Les images debug ne sont
pas commitées. Les screenshots sont réutilisés ; supprimer les paires PNG/JSON pour
les régénérer. Dépendances système : Xvfb, ImageMagick, bibliothèques OpenGL Blender.

Le dump parcourt toutes les fenêtres et leurs `screen.areas`/`area.regions` exposées
par bpy ; les barres globales TOPBAR/STATUSBAR ne sont pas exposées dans cette collection
et ne servent pas de cibles. Douze régions distinctes sont ciblées : viewport header,
tool settings, toolbar, sidebar, fenêtre principale ; Outliner fenêtre et header ;
Properties navigation, fenêtre et header ; Timeline fenêtre et header.
Origine Blender bas-gauche convertie en boîtes pixels haut-gauche [x0,y0,x1,y1].
Le viewport WINDOW chevauche ses overlays selon les rectangles RNA de Blender.

Chaque modèle teste les 12 descriptions sur les deux échelles, en image entière puis
en crop du parent area avec marge 24 × scale pixels, bornée au PNG. Les coordonnées
normalisées sont projetées dans le crop puis décalées dans l'image entière.
Hit si le point est dans la région attendue (bords droit et bas exclus).

### Mesures et cache

Chaque paire utilise un nonce UUID unique au tout début du message système, avant
les instructions stables. Le passage `uncached` utilise ce préfixe inédit ; le passage
`cached` répète le corps identique immédiatement, sans autre requête intercalée.
Nonce et SHA-256 du corps sont conservés pour vérifier le protocole, et les vrais
cached_tokens servent de contrôle de cache. Cela représente 192 appels logiques.

La concurrence est fixée à 1. Le client partage un token bucket de capacité 1 avec
un intervalle initial de 2 s entre départs ; il ne permet aucune rafale. Retry-After
(secondes ou date HTTP) et les resets request/token avec quota épuisé sont respectés.
L'intervalle s'adapte aussi aux quotas restants et augmente de 50 % après un 429.
Sans en-têtes, on ne prétend pas connaître le plafond exact du fournisseur.
Backoff 429 : 15, 30 puis 60 s ; backoff serveur/transport : 5, 10, 20, 40 puis 60 s.
Les instructions serveur plus longues sont respectées sans troncature. Timeout par
tentative 30 s, garde de sécurité 20 tentatives ; 401/403 arrêtent immédiatement.

**Latence = durée perf_counter de la seule tentative HTTP 200.** Les attentes pacing,
cooldown, durées des tentatives échouées, temps total et nombre de 429 sont enregistrés
séparément. Les erreurs finales éventuelles restent des misses avec latence null,
jamais mélangées aux percentiles des succès. Les tableaux comparent les passages
uncached/cached dans chaque groupe modèle/échelle/full-crop, pas seulement un agrégat.

`holo-calls.jsonl` conserve chaque réponse mesurée et ses tentatives (latence, statut,
request id et usage) immédiatement pour ne pas perdre les mesures en cas d'arrêt.
`holo.json` et `holo.md` détaillent résultats par modèle/échelle/full-crop, passes 1/2,
tokens et tous les misses (point prédit contre boîte). Les coûts sont calculés depuis
les tokens à $0.30/M entrée, $0.03/M cache et $2/M sortie, pas une facture ; le catalogue
API annonce des tarifs supérieurs pour 27B. Aucune clé ni en-tête Authorization n'est loggé.

Les anciens relevés sans pacing ont été remplacés. Les en-têtes de quota reçus sont
conservés dans `attempts[].rate_headers` ; un objet vide signifie qu'aucun en-tête
Retry-After/rate-limit n'a été fourni, pas une limite supposée illimitée.

### Relevé avec pacing

192/192 appels logiques ont reçu HTTP 200, sans échec de parsing ; 136 hits.
193 tentatives de localisation, dont un 429, puis passage de 2 à 3 s entre départs.
Le 429 expose `x-ratelimit-limit: 30`, `x-ratelimit-remaining: 0`,
`x-ratelimit-reset: 2` et `retry-after: 2` ; la fenêtre du quota 30 n'est pas indiquée.
Les 192 succès n'exposent aucun en-tête de quota. Le cooldown a duré 15,075 s,
le pacing 348,310 s, exclus des latences. Ces observations ne déterminent pas un
plafond de débit garanti ; 3 s a suffi pour le reste de cette matrice.

Les 96 premiers passages ont zéro token caché ; les 96 répétitions ont un corps et
un nonce identiques à leur premier passage. 20 répétitions sur 96 ont réellement
utilisé du cache (76 832 tokens). Le cache fournisseur est best effort, sans garantie
de hit même pour un corps identique, selon
https://hub.hcompany.ai/models-api/build-an-agent/core-concepts.md#prompt-caching.
Les tableaux `uncached`/`cached` désignent donc les conditions du protocole, pas une
garantie de cache servi. Total : 717 040 tokens entrée + 2 622 sortie = 719 662 ; coût
calculé 0,19961136 USD, hors requêtes catalogue et probe préalable.

## Jev : intentions françaises via Codiv

```sh
export CODIV_API_KEY=... # uniquement dans l'environnement, jamais dans les rapports
python -m bench jev --timeout 60 --out bench/results
pytest -q -s -m live bench/tests -k jev
```

Découverte : `GET https://api.codiv.ai/v1/models` renvoie une liste `models` avec
`name` (pas la forme OpenAI `data/id`). Modèle retenu : `openjev-0.1` ; alias
`openjev-latest` annoncé comme pointant vers cette version. Autres IDs du catalogue :
`diffusiongemma-26b`, `laya-1.0`, `verdict-1.4`, `clm-v0.1`, `jevk5-0.3`,
`clef-flash-1.0`. Aucun de ces autres modèles n'est utilisé.

Vraie API Jev : `POST https://api.codiv.ai/v1/systemone`, Bearer provenant uniquement
de `CODIV_API_KEY`. Corps : `{model, state:[{id,text}], questions:{id:{type:"choice",
instructions,criteria:{label:definition}}}}`. Réponse :
`{model,answers:{id:{type:"choice",choice,probabilities,confidence}},usage}`.
Les IDs de questions ne sont pas montrés au modèle selon la documentation : chaque
instruction désigne donc explicitement l'ID de la phrase dans le state. Golds exclus
du corps envoyé. Le parser normalise les réponses en dictionnaire id → label, jamais
par ordre de retour ; IDs absents/labels invalides = échec de parsing et miss ; IDs
supplémentaires conservés séparément. Pas de génération chat, pas de system message
ni température dans cette API : instructions et critères stables remplacent ce prompt.
`/v1/chat/completions` existe mais utilise un autre modèle et n'est pas appelé.

Sources fournisseur consultées :
- https://codiv.ai/docs/api-reference/system-one.md
- https://codiv.ai/docs/api-reference/models.md
- https://codiv.ai/docs/guides/rate-limits.md
- https://codiv.ai/docs/api-reference/chat-completions.md

Les **1 200 req/min sont documentaires, non mesurées**. Nous imposons une limite
plus stricte : token bucket capacité 1, intervalle 1,05 s, appels séquentiels,
Retry-After/resets et backoff du pacer Holo réutilisé ; jusqu'à 20 tentatives pour
429/5xx/transport, sans retry des erreurs de quota épuisé. Le GET catalogue n'a
fourni aucun en-tête rate-limit. Les en-têtes observés sur les appels de décision
sont conservés dans `attempts[].rate_headers`, sans Authorization.

### Taxonomie et données

Huit labels de benchmark, pas une enum canonique importée du moteur :

| Label | Intention | Référence et dérivation |
|---|---|---|
| why | Raison pédagogique de l'action en cours | PRD.md F7/F12 ; docs/workflows/05-question-vocale.md |
| help | Indice, localisation, blocage/frustration sans délégation | PRD.md F6 ; docs/workflows/04-blocage-paliers.md ; docs/architecture/engine.md « Politique d'aide » |
| delegate | Faire à ma place, consentement explicite | docs/workflows/06-fais-le.md ; docs/architecture/engine.md « Mémoire apprenant » |
| stop | Arrêt, annulation, chut | docs/workflows/06-fais-le.md « Cas vide, erreur et arrêt » ; docs/architecture/engine.md « Politique d'aide » |
| repeat | Répéter/reformuler une consigne | Extension opérationnelle des consignes vocales PRD.md F7, pas un intent explicitement nommé dans les docs |
| next | Confirmer sa progression / demander la suite | docs/architecture/engine.md machine PASSED → READY ; docs/glossaire.md « Étape », « Check » |
| question | Question Blender hors étape | PRD.md F12 ; docs/workflows/05-question-vocale.md réponse hors script |
| other | Bruit et hors sujet | Extension négative du cas vide/silence de docs/workflows/05-question-vocale.md, pas un intent métier explicite |

`bench/data/jev_utterances.jsonl` : 32 phrases rédigées et étiquetées avant tout appel,
4 par label, style oral français, hésitations et termes Blender anglais. Aucun label
produit par le service ni corrigé après mesure. En cas d'ambiguïté, priorité explicite
stop > delegate > repeat > why > help > next > question > other ; confirmer une
délégation reste delegate. Pas de contexte réel d'étape : une question technique
générale est question, une demande d'indice immédiat help. Petit jeu synthétique,
pas une validation utilisateur ni un benchmark de transcription audio.

Deux passes single (64 appels), quatre groupes de 8 et un groupe complet (32),
soit 69 appels logiques / 128 décisions. Même AsyncClient persistant. Cold désigne
seulement la première requête connexion/TLS comprise, pas une preuve de GPU froid.
Latence = tentative HTTP 200 seule ; attente et retries séparés. Amorti batch =
durée/nombre de phrases, pas délai individuel. Les rapports conservent les tokens,
les confusions, les résultats par label, chaque durée batch et les deux passes de
stabilité. Aucun prix inventé : pas de tarif demandé pour ce service.

### Résultat conservé

69/69 réponses 200, zéro 429, zéro erreur de parsing, zéro ID supplémentaire.
Les 69 réponses confirment `model: openjev-0.1` ; aucune ne fournit d'en-tête
rate-limit/Retry-After. 45 886 tokens entrée, zéro sortie. Le test live ajoute un
appel de 372 tokens entrée ; découverte catalogue : un GET sans usage de tokens.
Le rapport courant combine les 64 singles originaux et cinq batches relancés.
Single : 62/64 (96,875 %), batches de 8 : 32/32, batch complet : 31/32.
Seule confusion, répétée aux deux passes single : « Tu peux juste me montrer où
est le modifier bevel ? », gold help, prédit delegate. Gold non modifié.
Première requête : 329,635 ms ; warm single p50/p95 : 203,975 / 232,997 ms.
Le gain batch est un amortissement ; les phrases voisines peuvent influencer les
décisions. Les batches utilisent une copie mélangée par `random.Random(20261107)` ;
la même permutation sert aux groupes de 8 et au batch complet. Reproduction :
`python -m bench jev --batches-only` conserve les singles et ne refait que cinq appels.
Ce relevé a ajouté cinq POST (sans erreurs) ; les singles conservés datent du relevé
précédent, leur connexion persistante n'est pas celle des nouveaux batches. Le batch
complet confond why1 avec stop ; les golds restent inchangés. 100 % sur quatre petits
batches n'établit pas une supériorité générale de ce mode.

## Gladia live STT

```sh
export GLADIA_API_KEY=... # environnement seulement
python -m bench gladia --timeout 30
pytest -q -s -m live bench/tests -k gladia
```

API v2 directe, sans SDK : `POST https://api.gladia.io/v2/live`, authentification
`x-gladia-key`, puis connexion au WebSocket retourné. Le modèle live documenté est
`solaria-1`, explicitement demandé. Configuration : `encoding: wav/pcm`, 16 000 Hz,
mono, 16 bits, `endpointing: 0.05`,
`language_config: {languages:["fr","en"],code_switching:true}`,
`messages_config` active partials, finals et événements de cycle de vie. Deux langues
autorisent l'anglais ; selon les docs, une seule langue ferait ignorer code_switching.
Pas de vocabulaire personnalisé ni de référence transmise au STT.

Sources consultées :
- https://docs.gladia.io/api-reference/v2/live/init
- https://docs.gladia.io/chapters/live-stt/quickstart.md
- https://docs.gladia.io/asyncapi.yaml

Chaque session envoie les samples PCM bruts (pas l'en-tête WAV) par blocs de 3 200
octets / 100 ms sur une échéance monotone absolue, dernier bloc éventuellement plus
court. Envoi et réception tournent simultanément. `stop_recording` est envoyé après
la durée audio ; on continue de lire jusqu'à `end_session`. Limite totale 30 s après
connexion, init HTTP et handshake également bornés. Une erreur/timeout arrête la
suite explicitement ; les sessions terminées restent dans `gladia-calls.jsonl`.
Pas de retry aveugle ni de session facturable dupliquée. URL WebSocket signée et
clé non conservées, seuls session_id, transcriptions, types d'événements et temps
locaux sont enregistrés.

### Clips et reproduction offline

Quatre clips français (références `bench/data/gladia_references.json`) synthétisés
localement avec **Piper 1.8.0, fr_FR-siwis-medium**, voix française 22 050 Hz, puis
ffmpeg vers PCM 16 kHz mono 16-bit. WAV commis : environ 300 Kio au total, pas de
modèle TTS commis. L'exécution du benchmark ne nécessite ni Piper ni téléchargement.
Pour régénérer (synthèse elle-même offline après téléchargement) :

```sh
uv pip install --python ~/.venvs/hcompany-hack/bin/python piper-tts==1.8.0
python -m piper.download_voices fr_FR-siwis-medium --download-dir ~/downloads
python -m bench.generate_speech --voice ~/downloads/fr_FR-siwis-medium.onnx
```

Attribution voix/données : projet Piper / rhasspy, corpus SIWIS (Université
d'Édimbourg), licence du dataset CC-BY 4.0 selon la model card :
https://huggingface.co/rhasspy/piper-voices/blob/main/fr/fr_FR/siwis/medium/MODEL_CARD
et https://datashare.is.ed.ac.uk/handle/10283/2353.
Piper prononce les termes anglais avec une voix française : ces clips ne valident
ni des accents humains variés ni les erreurs d'un vrai micro.

### Définitions des mesures

Chaque clip est joué trois fois dans trois sessions indépendantes ; client HTTP
persistant, nouveau WebSocket par session. Init HTTP et handshake sont séparés.
Début = premier send PCM ; onset = premier sample dont |amplitude| ≥ 500 sur 32 768,
dans la timeline audio ancrée au début (pas un VAD humain). Temps vers premier
partial non vide ; pas de substitution d'un final quand le partial manque.
Fin audio = retour du dernier send PCM, pas fin acoustique ni stop_recording. Temps
vers dernier final reçu (texte assemblé par ID d'utterance, finals répétés remplacés)
et vers end_session ; les temps négatifs éventuels restent visibles si un final
arrive avant la fin de l'envoi. Horodatages monotones bruts des envois/réceptions
conservés. Le streaming n'envoie jamais tout le clip à vitesse réseau.

WER implémentée localement par Levenshtein sur mots ; CER sur caractères, espaces
inclus. Normalisation NFC, minuscules, ponctuation/apostrophes remplacées par espaces,
accents conservés. Agrégats pondérés par le nombre de mots/caractères référence,
pas moyenne naïve des pourcentages. Les termes anglais ne bénéficient d'aucune
correction tolérante. Coût **calculé** : secondes audio × 0,68 €/3 600, hors éventuel
minimum de facturation et frais de session inconnus, pas une facture.

### Relevé conservé

12 sessions (4 clips × 3), toutes initialisées HTTP 201 et terminées par end_session,
zéro message malformé, aucun partial manquant. Écarts observés entre envois consécutifs :
96,69–103,63 ms. Total audio 27,620625 s, coût calculé 0,00521723 € ; WER corpus
15,625 %, CER 5,389 %. Les sorties sont identiques aux trois répétitions de chaque
clip : extrude et bevel exacts ; Shift A → Shifta ; Euh → Heure et viewport → vieux
pote. Les références ne sont pas adaptées aux erreurs observées.
Le test live ajoute une session torus de 1,8228125 s : 13 sessions au total,
29,4434375 s audio et 0,00556154 € calculés, test inclus. Tous les résultats mesurés
par session sont dans les rapports ; aucune mesure de robustesse aux accents/bruit.
