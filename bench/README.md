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
