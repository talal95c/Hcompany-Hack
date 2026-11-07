# Un titre structuré dans Writer

Leçon originale en français, contrat v2, révision 1, LibreOffice Writer 7.3.7
(paquet 7.3.7.2). Trois étapes : saisir « Rapport mensuel », appliquer **Titre 1**
avec Ctrl+1, puis enregistrer **rapport-mensuel.odt**. Aucun appel Holo nécessaire.
Le générateur produit un brouillon ; seule une preuve complète promeut la révision.

## Cibles AT-SPI réellement observées

Racine : `frame:Sans nom 1 - LibreOffice Writer`, `panel:`, `panel:`,
`root pane:Sans nom 1 - LibreOffice Writer`, `panel:`.

- `scroll pane:` → `document text:Sans nom 1 - Document LibreOffice` →
  `paragraph:` (texte du titre avant mise en forme), puis `heading:` après Ctrl+1.
- `tool bar:Formatage` → `panel:Style de paragraphe` → `panel:` → `filler:` →
  `panel:` → `panel:` → `filler:` → `filler:` → `text:` lit **Titre 1**.
  Le combo voisin n'expose pas cette valeur ; son enfant Text est vide.
- `tool bar:Standard` → `push button:Enregistrer sous...`.

Les nœuds Text et Paragraph sont anonymes : leur cible omet `name` plutôt que
d'inventer un nom ou d'écrire une chaîne vide interdite par le contrat. Leur
chemin et leur rôle les identifient uniquement ; toute ambiguïté vaut `unknown`.
Les coordonnées des gestes ne sont jamais stockées. Le titre de fenêtre est
relu depuis l'application après l'enregistrement, qui renomme les accessibles.

## Preuve

Chaque erreur part d'un document neuf reconstruit par les gestes précédents :
mauvais texte, gras sans style, style sur un second paragraphe, mauvais nom de
fichier. Le contrôle du style revient au premier paragraphe pour ne pas confondre
un titre ailleurs avec le bon titre. Le document normal ne contient qu'une ligne.

Enregistrer sous utilise Ctrl+Maj+S, Ctrl+L, le chemin complet dans le dossier
privé de l'essai, deux validations Entrée, puis Ctrl+S pour enregistrer l'état final.
Le format natif ODT ne déclenche pas de confirmation de conversion sur la version
testée. Les variantes d'interface et de format ne sont pas validées ici.

Le titre de fenêtre doit contenir le nom demandé. En complément, le pilote
vérifie le fichier sur disque, son type MIME ODF et `content.xml` : un `text:h`
de niveau 1, style `Heading_20_1`, contient exactement « Rapport mensuel ».
L'ODT réellement enregistré est copié dans `proof/`, avec son SHA256 et celui de
`content.xml`. Cette lecture ZIP/XML est une preuve, jamais un geste d'édition.
Le manifeste empreinte source, leçon, compagnon, preuves et document enregistré.
Les durées incluent reconstruction et essais négatifs. Pas de recette macOS ni
de validation visuelle humaine ; preuve native X11 française uniquement.

## Reproduction depuis la racine

```sh
python lessons/build_generic.py
python tests/lessons/prove_generic.py lessons/texte-titre lessons/texte-titre/proof-run.json
ruff check lessons tests/lessons
pytest -q tests/lessons
pytest -q -m 'a11y and not live' tests/lessons -v
pytest -q
```

Le générateur régénère aussi le brouillon Calc. La session et les prérequis
natifs sont décrits dans [la leçon de tableur](../tableur-somme/README.md).
Les tests natifs couvrent les deux applications ; les contrôles de preuves
complètes ne s'appliquent pas au brouillon Calc en attente du fournisseur cloud.
