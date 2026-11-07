# Captures réelles reproductibles

`python tests/services/fixtures/make_screens.py` génère quatre PNG 1600×900
sur des Xvfb privés : Calc :77, scènes 3D :78 et :79. Jamais de capture de :0.
Options : `--app calc` ou `--app scene`. Les processus sont arrêtés en sortie ;
profils isolés, documents FODS et logs restent dans `.runtime/` (ignoré par git).
Prérequis système : Xvfb, xdotool, ImageMagick, libreoffice-calc, /opt/blender/blender.

- `calc_no_formula.png` : A1=10, A2=20, A3=30 ; A4 sélectionnée et vide.
- `calc_sum_formula.png` : mêmes nombres ; A4 sélectionnée, résultat 60 et
  formule `=SUM(A1:A3)` visible dans la barre de formule.
- `blender_torus.png` / `blender_cube.png` : vraie fenêtre graphique 4.5.9,
  rendu logiciel OpenGL, objet sélectionné nommé Subject dans les deux cas pour
  éviter que son nom fournisse la réponse ; géométrie créée via Python autorisé.

La recette computer-use ouvre une nouvelle feuille identique au négatif sur :80.
Les captures intermédiaires et finale sont dans `../results/computer_use/`.
Les tests live suivent le marqueur `live` et la présence de clés, comme les tests
existants ; aucun flag HCOMPANY_LIVE supplémentaire n'est requis. Les appels Holo
partagent un Pacer à 2,5 s, y compris les anciennes recettes.

## Accessibilité
Installés : at-spi2-core et python3-pyatspi. La capture utilise volontairement le
plugin VCL `gen`. Cette installation LibreOffice ne fournit que
`libvclplug_genlo.so`, pas le plugin gtk3 : aucune découverte des cellules par
pyatspi n'a été validée. Le chemin AT-SPI/GTK3 reste non testé, pas un succès ;
il faudrait installer le plugin GTK3 puis relancer avec un bus D-Bus privé et
`SAL_USE_VCLPLUGIN=gtk3`. La recette ici est strictement visuelle/X11.

Les deux premières fixtures historiques PNG/WAV restent inchangées.
