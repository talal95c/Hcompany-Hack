# Holo Tutor — landing

Site de présentation français, indépendant de l’application native `h-tutor/`.
Il n’appelle aucune commande Tauri, ne capture pas l’écran et n’utilise aucune clé.

## Démarrage

Node.js 22.12+ et npm :

```sh
cd landing
npm ci
npm run dev
```

Vite écoute sur le port 5173. `npm run build` produit le site statique dans
`dist/` ; `npm run preview` permet de servir ce build. Le site est prévu à la
racine d’un domaine (les chemins des assets commencent par `/`).

## Vérifications

```sh
npm run typecheck
npm run lint
npm test
npm run build
```

La CI lance ces quatre vérifications. Vitest couvre l’entrée, les sorties de
secours, les liens, le menu et la sélection d’aperçu. Ces tests DOM ne prouvent
ni la fluidité du raccord animé ni le fonctionnement natif du tuteur.

L’override npm de `minimatch` est limité au parseur TypeScript ESLint : il évite
la version transitive touchée par GHSA-g3hv-75wg-m249 sans modifier les
dépendances de l’application native.

Recette visuelle : souris et clic sur l’ordinateur, Entrée/Espace, Tab/Échap,
« Passer l’intro », retour/rechargement, « Rejouer l’intro », mobile tactile,
menu, FAQ, préférence de réduction des animations et blocage des images.
Les ancres directes contournent l’introduction ; elle n’apparaît qu’une fois
par session de navigation. Si le stockage est bloqué, toutes les sorties
restent utilisables. Sans JavaScript, un résumé et le lien d’installation
restent disponibles dans `index.html`.

## Ordinateur original

L’entrée affiche 57 vues (19 angles horizontaux × 3 verticaux) d’un ordinateur
créé pour Holo Tutor dans Blender, en WebP transparent. Un canvas interpole
les quatre vues voisines ; aucun runtime 3D n’est téléchargé. Les rendus sont
chargés à quatre requêtes concurrentes sur ordinateur ; un écran tactile ne
charge que la vue centrale. Ils restent décoratifs. Le bouton et le
contenu ne dépendent ni de WebGL, ni d’un chargement complet des images.

Le générateur est `scripts/render_computer.py`. Pour refaire les rendus avec
Blender 4.5, depuis la racine du dépôt :

```sh
blender -b --threads 8 --python landing/scripts/render_computer.py
for image in landing/render-work/frame-*.png; do
  ffmpeg -y -loglevel error -i "$image" -c:v libwebp -quality 84 \
    "landing/public/computer/$(basename "${image%.png}").webp"
done
cp landing/render-work/frames.json landing/public/computer/frames.json
```

`-- --center-only` permet de refaire uniquement la vue centrale. Les PNG de
travail ne sont pas versionnés. Le générateur réutilise la texture d’écran
originale, déjà fournie dans `public/computer/screen.webp`.

## Contenu et assets

- Les boutons d’installation pointent vers les instructions réelles dans
  `h-tutor/README.md`. Pas de formulaire sans backend, ni de téléchargement
  fictif : aucun binaire n’est livré par ce site.
- L’aperçu du guide est **une illustration interactive**, explicitement
  identifiée comme telle, sur une vraie capture Blender issue de
  `tests/services/fixtures/blender_4.5.9_layout_1600x900.png`. Il ne simule pas
  une exécution native, ne valide pas une leçon et ne déclenche aucun agent.
- La [photographie de paysage](https://images.unsplash.com/photo-1470252649378-9c29740c9fa8)
  est utilisée sous la
  [licence Unsplash](https://unsplash.com/license), qui autorise son utilisation
  et sa modification sans attribution obligatoire. La texture du moniteur
  adapte cette photographie avec notre propre titre et notre propre bouton.
- Les polices Manrope et Cormorant Garamond sont auto-hébergées via Fontsource
  (licence SIL OFL, fournie avec leurs paquets). Les icônes sont celles de
  Lucide (licence ISC). Aucun appel de police, tracker ou CDN au runtime.
- Le modèle d’ordinateur, sa géométrie, son éclairage et les illustrations CSS
  sont nos propres assets. Aucun code ni asset de site de référence n’est embarqué.
