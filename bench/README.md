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
`jev`, `gladia` et `all` signalent les suites encore indisponibles.
Options addon : `--blender /opt/blender/blender`, `--timeout 60`, `--operations 50`.
Installation Blender 4.5.9 LTS : voir `docs/environnement-dev.md`.
Exécuter depuis la racine (bench n'est pas inclus dans les packages distribués du socle).

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

Chaque paire envoie exactement le même corps deux fois de suite, sans historique ;
au maximum deux paires en parallèle. Cela représente 192 appels de localisation,
hors retries et test live. Timeout par requête 30 s ; 429/5xx et erreurs transport
retentés jusqu'à trois fois, attente exponentielle 1 puis 2 s. Parse invalide ou HTTP
en erreur = miss ; 401/403 arrêtent la suite. Latences perf_counter mesurées de bout
en bout, retries/backoff inclus. Un passage 1 peut déjà être caché ; le passage 2
n'est pas supposé caché sans cached_tokens réellement renvoyés.

`holo-calls.jsonl` conserve chaque réponse mesurée et ses tentatives (latence, statut,
request id et usage) immédiatement pour ne pas perdre les mesures en cas d'arrêt.
`holo.json` et `holo.md` détaillent résultats par modèle/échelle/full-crop, passes 1/2,
tokens et tous les misses (point prédit contre boîte). Les coûts sont calculés depuis
les tokens à $0.30/M entrée, $0.03/M cache et $2/M sortie, pas une facture ; le catalogue
API annonce des tarifs supérieurs pour 27B. Aucune clé ni en-tête Authorization n'est loggé.

### Limite du relevé conservé

La matrice entière a été exécutée : 192 requêtes logiques, 354 tentatives HTTP,
117 réponses 200 et 75 erreurs finales 429 malgré les retries. Ces erreurs restent
des misses, pas des points inventés. Les 117 réponses 200 sont toutes parsées ;
87 hits, soit 74,36 % conditionnellement aux réponses 200 (45,31 % sur toute la matrice).
Les tableaux indiquent séparément les erreurs HTTP : ne pas interpréter ces taux bruts
comme une comparaison isolée de précision des deux modèles. Le relevé n'a pas été
relancé pour masquer les limites du service ni engager des appels supplémentaires.
Le cache a été réellement observé ; la comparaison cache/non-cache mélange modèles,
échelles et conditions, elle n'établit pas une accélération causale.
