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

Les tests live audio nécessitent aussi `espeak-ng` (`apt-get install espeak-ng` sur
Ubuntu). Lancer `pytest -q tests/prep -m live -rP` avec les trois clés ci-dessus :
l'absence d'un outil requis échoue explicitement au lieu de sauter le test.
Sans clé, les tests correspondants restent ignorés pour la CI hors réseau.

Sans `--language`, la langue est celle détectée par Gladia, non vérifiée
sémantiquement (un avertissement est émis). La détection peut être erronée sur
une courte narration synthétique ; préciser `--language fr` ou `--language en`
pour une leçon dont la langue est connue.

## Applications génériques (`--app`)
`--app blender` (défaut) garde le chemin Blender (add-on, checks `blender.*`). Tout autre
profil de `prep/apps` (ex. `libreoffice-calc`, `libreoffice-writer`) passe par le chemin
générique : carte UI depuis un instantané d'accessibilité (AT-SPI via `pyatspi`, même JSON
normalisé `{ref, role, name, value?, states, bounds, parent_ref}` pour AX/UIA), checks
`element_exists/value/state`, `window_title`, `visual_assert`, leçon v2 (`app.sensor`).

```sh
sudo apt-get install -y libreoffice-calc libreoffice-gtk3 at-spi2-core python3-pyatspi \
  xvfb openbox xdotool imagemagick dbus-x11
python -m prep tutoriel.txt --app libreoffice-calc --fixture donnees.csv \
  --out lessons/libreoffice-calc/ --language en
```

Le prouveur lance l'app dans un bac à sable (Xvfb + D-Bus + bus AT-SPI privés, HOME
jetable, variables secrètes filtrées), rejoue chaque étape avec Holo computer use et
vérifie le check sur un instantané frais (ou par vision pour `visual_assert`), enregistre
un checkpoint, revérifie après sauvegarde et écrit preuves, captures et SHA256.
Un arbre incomplet ou perdu donne `unknown`, jamais `pass`.

Limite AT-SPI observée (LibreOffice 7.3.7.2, VCL gtk3) : après « Terminer » de l'assistant
graphique, l'application reste enregistrée avec un nom vide et toute requête AT-SPI la
fige (écran noir, sauvegarde impossible). Les objets dessinés (graphique, image) sont donc
compilés en `visual_assert`, et une étape visuelle ne fait aucune requête d'accessibilité :
la détection de boîte de dialogue passe aussi par Holo.
