# Additionner et présenter des montants

Leçon originale française, contrat v2, révision 1, pour **LibreOffice Calc 7.3.7**
(paquet testé : 7.3.7.2). Le capteur demandé est `auto` : lectures AT-SPI pour
les valeurs et le gras, assertion Holo sur capture fraîche pour la monnaie.
Le générateur écrit un brouillon ; seul un parcours complet réussi le promeut
en `proven`. Les droits de la source originale sont décrits dans [SOURCE](SOURCE.md).

**État actuel : prouvée.** Les cinq étapes et toutes leurs erreurs connues ont
été rejouées dans l'application réelle. Le manifeste complet empreinte chaque
preuve, chaque capture originale et chaque image agrandie réellement envoyée.
La disponibilité cloud reste intermittente : les tentatives bornées sont mesurées,
et une réponse absente ou insuffisamment confiante reste `unknown`.

## Parcours

1. `saisir_entete` : A1 contient Montant.
2. `saisir_valeurs` : A2=12, A3=30, A4=8.
3. `formule_somme` : A5 contient `=SOMME(A2:A4)` et affiche 50. La fonction
   s'appelle SUM dans les interfaces anglaises. Les essais négatifs omettent
   `=` ou arrêtent la plage à A3 (42).
4. `entete_gras` : sélectionner A1 puis Ctrl+G ; le bouton Gras est coché.
   L'essai négatif applique le gras à A2 puis revient à A1 pour contrôler
   l'absence de gras sur l'en-tête.
5. `format_monetaire` : sélectionner A2:A5 puis Monnaie ; les quatre cellules
   affichent respectivement 12,00 €, 30,00 €, 8,00 € et 50,00 €.
   L'essai négatif ne formate que A5.

## Cibles réellement observées

Les rôles techniques AT-SPI restent en anglais, les noms produit sont français.
La racine est `frame:Sans nom 1 - LibreOffice Calc`, puis `panel:`, `panel:`,
`root pane:Sans nom 1 - LibreOffice Calc`, `panel:`.

- Grille : `scroll pane:`,
  `document spreadsheet:Sans nom 1 - Classeurs LibreOffice`,
  `table:Feuille Feuille1`, puis `table cell:A1` à `table cell:A5`.
- Mise en forme : `tool bar:Formatage`, puis `toggle button:Gras` ou
  `push button:Monnaie`. Le nom accessible est **Monnaie**, pas « Format monétaire ».
- Les menus observés incluent Format → Texte → Gras et Format → Format numérique
  → Monnaie. Le parcours rejoué utilise le clavier et la barre d'outils.

Chaque résolution repart de ces chemins descriptifs, sans coordonnées stockées.
Un clic xdotool utilise le rectangle lu au moment du geste. Les très grandes
tables sont interrogées par coordonnées de cellule via l'interface AT-SPI Table,
avec vérification du nom retourné ; jamais par énumération du milliard de cellules.

## Limites et preuve

`Table.isSelected` et l'état `selected` des cellules sont restés faux après un
clic réel, y compris après invalidation des caches et traitement des événements.
Le lecteur traite donc cet état comme indisponible pour les cellules : `unknown`,
pas une preuve de non-sélection. Le gras utilise l'état `checked` du bouton Gras
après un clic explicite sur A1. Les attributs de texte n'exposaient pas le gras.

Après application du format monétaire, AT-SPI Text continuait à retourner `50`
alors que la capture affichait `50,00 €`. La dernière étape utilise donc un
`visual_assert` explicite par cellule, pas une conversion fabriquée de la valeur numérique.
Holo voit uniquement le recadrage du haut gauche de cette fenêtre synthétique,
où les en-têtes et A1:A5 sont visibles. Les captures utilisées, réponses,
confiances, identifiants de requête et latences sont conservés dans les preuves
et empreintés par le manifeste. Une confiance insuffisante vaut `unknown`.
La rétention du fournisseur cloud reste à vérifier avant des données utilisateur.
Une question groupant les quatre cellules a initialement donné un faux positif
sur le chemin où seule A5 était formatée. Les assertions finales séparent chaque
cellule et les essais négatifs contrôlent précisément l'absence de format en A2.
Les petites captures sont agrandies proportionnellement pour que leur côté le
plus court mesure au moins 600 pixels avant l'envoi à Holo. L'original et l'image
envoyée sont conservés et empreintés, avec leurs dimensions dans chaque résultat.
Un timeout vaut `unknown` et ne peut pas valider une étape.

Chaque erreur est rejouée sur un document neuf, en reconstruisant le même état
par les gestes précédents. Les résumés avant erreur et avant chemin correct
doivent être identiques. Tous les checks doivent passer après le bon geste,
mais pas avant ni sur le chemin erroné ; les checks d'erreur ne passent pas sur
le chemin correct. Aucun geste ne passe par une API de document ou un script métier.

Les preuves concernent la session X11 française isolée, pas une recette macOS,
ni une traduction des raccourcis pour toutes les versions d'Excel. Le routage
générique du moteur pédagogique n'est pas implémenté ici. Les paliers d'aide
sont du contenu, pas une implémentation de voix ou de surlignage en production.

## Reproduction

Depuis la racine, avec l'environnement du projet activé :

```sh
python lessons/build_generic.py
python tests/lessons/prove_generic.py lessons/tableur-somme lessons/tableur-somme/proof-run.json
ruff check lessons tests/lessons
pytest -q tests/lessons
pytest -q -m 'a11y and not live' tests/lessons -v
pytest -m live tests/lessons -v
pytest -q
```

Le parcours complet et le test `live` exigent `HAI_API_KEY` dans l'environnement,
jamais dans un fichier. Le test `a11y and not live` rejoue les quatre étapes
natives et toutes leurs erreurs dans une copie ; il ne prétend pas prouver
l'affichage monétaire. Les tests réels ignorent proprement les dépendances
natives absentes. Les tests hors ligne ne nécessitent ni application ni cloud.

Le lanceur crée un bus privé, un profil jetable et un runtime privé de mode 700,
avec Xvfb sur `:89` (modifiable par `GENERIC_DISPLAY`, jamais `:0` ni `:77`).
Il exige `/usr/bin/python3` avec pyatspi, `soffice`, `xdotool`, Xvfb,
`at-spi-bus-launcher`, `dbus-run-session` et ImageMagick `import`/`convert`.
Le Python du projet prend en charge JSON Schema et le client Holo existant ;
le pilote natif reste compatible Python 3.10. Le transport Holo existant est
réutilisé avec `holo4-27b` et `enable_thinking=false` ; il n'exposait pas encore
d'API publique d'assertion visuelle, d'où l'adaptateur de test dédié.

Les appels Holo sont espacés d'au moins 2,5 s après chaque réponse, y compris
entre deux assertions distinctes. Le budget du processus est 420 s,
celui d'une tentative cloud 12 s. Au maximum cinq tentatives
sur timeout ou quota/429 respectent Retry-After (secondes ou date HTTP) ; si ce
délai dépasse le budget global de 120 s, aucune tentative anticipée n'est faite.
Chaque tentative et la durée totale sont enregistrées. Après épuisement : `unknown`.
Le sous-processus cloud est borné à 125 s. Les pauses entre gestes sont
des budgets de stabilisation, pas des mesures de performance.
Les durées mesurées figurent dans les JSON : démarrage jusqu'à la fenêtre prête,
lecture de chaque check, appel Holo et murale par étape (erreurs et reconstruction
incluses). Le total inclut les démarrages de chaque checkpoint.

Le portail GTK peut signaler l'absence de RealtimeKit et de configuration
PipeWire dans cette session minimale. Ces services audio ne sont pas utilisés
par les lectures AT-SPI ni par la capture X11 ; ce n'est pas une validation audio.
