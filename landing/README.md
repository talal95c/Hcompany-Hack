# Ordinateur CRT → Google

Une seule interaction : petit ordinateur jaune, suivi du pointeur, bouton
« Click » intégré à l’écran incurvé, zoom à travers la vitre, puis navigation
vers Google. Aucune landing, section marketing, commande Tauri ou API.

## Lancer

Node.js 22.12+ et npm :

```sh
cd landing
npm ci
npm run dev
```

`npm run build` produit le site statique dans `dist/`.
`npm run preview` sert ce build. Hébergement à la racine du domaine.

## Vérifier

```sh
npm run typecheck
npm run lint
npm test
npm run build
```

Le lien HTML réel reste disponible sans Canvas, sans JavaScript ou si les
images ne chargent pas. Entrée et Espace activent l’ordinateur. Échap annule
un zoom en cours. Avec réduction des animations, le clic ouvre directement
Google, sans zoom. Pas de stockage de session : l’ordinateur réapparaît à
chaque visite. Ctrl/Cmd-clic conserve le comportement normal d’un lien.

Le changement de destination se fait dans `src/App.tsx` (`DESTINATION`) et
dans le lien sans JavaScript de `index.html`. Le moteur dessine une miniature
statique de Google dans l’écran ; ce n’est ni un iframe ni une page Google
interactive. Le vrai site est ouvert seulement après le zoom.

## Rendu

Le Canvas 2D projette la miniature sur une grille incurvée et superpose la
coque et les reflets. Une seule paire de vues est dessinée à la fois : aucun
mélange de silhouettes qui dédouble les contours. Les vues sont chargées à la
demande, avec un cache limité à huit angles. Tactile et réduction des animations
conservent la vue centrale. Le zoom dure 1 150 ms ; la vitre s’aplatit et la coque
sort du champ avant la navigation.

Les tests couvrent les liens, le clavier, le repli, le cycle de vie, la projection,
le cadrage du zoom et la présence des 114 images. Ils ne remplacent pas une
recette visuelle du navigateur.

## Provenance des visuels

Les 57 vues de coque, les 57 vues de vitre et le poster proviennent de la
référence demandée. Les URL de provenance sont conservées dans
`public/crt/sources.json`. Le moteur de rendu et le composant React sont notre
code ; aucun script tiers du site de référence n’est exécuté ou embarqué.

Ces visuels ne sont pas des créations originales de ce dépôt. Aucune licence
de redistribution n’a été vérifiée : confirmer les droits avant une publication
publique. Aucun autre asset de la précédente landing n’est utilisé.
