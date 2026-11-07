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
`holo`, `jev`, `gladia` et `all` signalent les suites encore indisponibles.
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

Limite observée sur cette VM : le PNG est entièrement noir malgré quatre areas et
des regions renseignées. Capture UI exploitable non validée pour l'étape suivante.
Le message `GHOST/Wayland: error: XDG_RUNTIME_DIR not set in the environment.`
disparaît avec un répertoire privé mode 700 et `XDG_RUNTIME_DIR` défini ; même avec
`LIBGL_ALWAYS_SOFTWARE=1` et dix secondes d'attente, le PNG reste noir sous Xvfb.
