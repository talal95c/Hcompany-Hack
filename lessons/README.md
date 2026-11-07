# Leçons prouvées sur Blender 4.5.9

Deux leçons originales en français : [donut](donut/README.md) (9 étapes) et
mini-cube (ajout, biseau, lissage). `lesson.json` respecte le contrat v2 ;
`steps.json` porte objectifs, quatre paliers d'aide et procédures ordonnées.
Son schéma strict est `steps.schema.json` (draft 2020-12).
La migration explicite porte les deux leçons à la révision 2, avec
`app={id: blender, name: Blender, version: 4.5.9, sensor: addon}` et conserve
`blender_version`. Chaque révision est à nouveau prouvée sur cette version.
Les noms de checks historiques sont conservés : le registre actuel du moteur
(`engine/checks/__init__.py`) ne reconnaît pas encore les alias `blender.*`.

Une leçon multi-app séparée, [tableur-somme](tableur-somme/README.md), enseigne
une somme dans LibreOffice Calc 7.3.7 avec AT-SPI et Holo. Son compagnon strict
est `generic-steps.schema.json` ; sa reproduction utilise `build_generic.py`
et `tests/lessons/prove_generic.py`, sans modifier les parcours ci-dessous.
Elle reste brouillon pendant l'indisponibilité cloud. La leçon
[texte-titre](texte-titre/README.md) réutilise ce compagnon et ce pilote pour
Writer : titre structuré et enregistrement ODT, vérifiés sans vision cloud.

## Reproduction depuis la racine

```sh
source ~/.venvs/hcompany-hack/bin/activate
python lessons/build_artifacts.py
python tests/lessons/prove.py lessons/donut lessons/donut/proof-run.json
python tests/lessons/prove.py lessons/mini-cube lessons/mini-cube/proof-run.json
ruff check .
pytest -q
pytest -q -m blender tests/lessons -v
```

Le générateur ne produit pas de preuves : rejouer Blender après toute modification.
Le lanceur utilise `blender -b --factory-startup --python-exit-code 1 --python
tests/lessons/blender_runner.py -- <dossier> <résultat.json>` avec un délai maximal
de 120 secondes. Il mesure aussi la durée murale du processus, démarrage inclus.
Les tests travaillent sur des copies, sans modifier les preuves versionnées.
`proof/manifest.json` empreinte chaque preuve, la leçon, le compagnon et la source.

## Sémantique des checks locaux

Chaque résultat vaut `pass`, `fail` ou `unknown` ; seul `pass` valide.
Les checks d'une étape doivent **tous** passer et ne doivent pas déjà tous passer
avant le geste. Les erreurs connues ne doivent jamais passer sur le chemin correct.

- `object_exists` : scène sans MESH → `fail` ; primitive reconnue par provenance
  enregistrée lors de l'opérateur créateur **et** géométrie suffisante → `pass` ;
  MESH non prouvé → `unknown`. Tore : quadrilatères, degré 4, caractéristique
  d'Euler 0, une composante, sommets = segments majeurs × mineurs. Cube : 8 sommets,
  6 quadrilatères. Aucun nom d'objet ne prouve son identité.
- `torus_dimensions` : rayons majeur et mineur mesurés à partir des distances
  radiales extrêmes, tolérance explicite ; segments de provenance, nombre de sommets
  et niveaux Z géométriques concordants. Mesure avant déformation uniquement.
- `modifier` : présence du type demandé, niveau exact ou intervalle d'épaisseur.
- `shade_smooth` : toutes les faces du maillage de base sont lissées.
- `mesh_deformed` : distance maximale à la surface idéale du tore supérieure au
  seuil pour au moins deux sommets, avec topologie intacte et provenance conservée.
  Une pointe isolée ne valide donc pas une déformation proportionnelle.
- `vertex_spike` : exactement un sommet dépasse le seuil de distance à la surface
  idéale, topologie intacte ; signale une translation sans influence des voisins.
- `flat_faces` : au moins une face du sujet garde un ombrage plat.
- `torus_extra_faces` : l'unique objet de provenance tore contient plus de faces
  que segments majeurs × mineurs. La provenance permet ici d'examiner un tore
  abîmé, même si sa topologie ne valide plus `object_exists`.
- `derived_part` : autre MESH, sommets en coordonnées monde coïncidant avec ceux
  du tore à epsilon près, arêtes de bord, fraction de faces dans l'intervalle.
- `material_color` : toutes les faces utilisent un matériau à nœuds dont un
  Principled BSDF porte la couleur RGBA linéaire demandée à tolérance près.

Les rôles `torus` et `cube` sont résolus par provenance + géométrie ; `icing` par
`derived_part`. Une résolution ambiguë ne passe pas. Les noms sont ignorés.
Les vérifications portent sur les maillages de base, avant modificateurs évalués.

Chaque erreur du compagnon possède des `mistake_actions` autorisées. Pour chaque
essai, le lanceur reconstruit le checkpoint avant l'étape en rejouant les étapes
précédentes depuis la scène vide. Il vérifie l'égalité des résumés d'état avant
l'essai et avant le chemin correct. La faute doit faire passer son check d'erreur
et empêcher la validation complète de l'étape. Les preuves conservent les actions,
états et résultats des deux chemins. Les temps par étape incluent ces essais et
la reconstruction des checkpoints, pas uniquement le geste réussi.

## Limites

Les leçons utilisent `object_exists` dans le contrat et conservent leurs checks
géométriques riches dans le compagnon. Le moteur charge ce compagnon pour les
vérifications prises en charge ; la preuve complète est rejouée par le lanceur
Blender local aux tests. Aucune preuve UI :
`ui_path_verified=false`, menus français descriptifs, pas de recette macOS.
La sélection géométrique déterministe remplace la sélection manuelle dans le viewport.
`redo` supprime la sortie du dernier opérateur créateur puis le réexécute avec les
nouvelles propriétés : sémantique du panneau, sans prétendre tester son interface.
Les paliers suivent ADR 0006 : ① voix ② surlignage et menu ③ pointeur ④ démo ;
ils sont du contenu pédagogique, pas une implémentation de l'overlay ou de la voix.
