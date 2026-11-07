# prep/

## Responsabilité
Pipeline de préparation Linux cloud.

## Entrées
tutoriel et version cible.

## Sorties
leçon prouvée ou rapport pending.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../docs/architecture/preparation.md) et [guide des agents](../AGENTS.md).

## État et validation
Sandbox Blender headless, cartes UI versionnées, preuves par différence, recherche Linkup et demandes de réparation locales disponibles. Validation : `ruff check .` et `pytest -q tests/ -m "not live"` ; réseau opt-in via marqueur `live`. Les étapes UI modifiées restent pending, sans preuve visuelle simulée.

## Usage
Installer `pip install -e '.[prep]'`, Blender et ffmpeg. Fournir GLADIA_API_KEY pour
l'audio/vidéo, HAI_API_KEY pour compiler et LINKUP_API_KEY pour rechercher après échec.

```sh
python -m prep tutoriel.mp3 --out lessons/demo/ --language fr --lesson-id demo
python -m prep tutoriel.md --out lessons/demo/ --source-version 4.5.9
```

Sans version source explicite, la version installée est supposée ; une autre version
nécessite sa carte exacte en cache, sinon les étapes restent pending. Options :
`--blender`, `--holo-model`, `--holo-fallback-model holo4-27b`. Sorties : transcript,
leçon, rapport de compilation, preuves/checkpoints, réparations et timings JSON mesurés.
Codes de sortie : 0 proven, 2 pending/failed, 1 erreur. Le rejeu UI Holo reste à intégrer.
