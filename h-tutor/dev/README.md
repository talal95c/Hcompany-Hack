# Galerie de matériaux (développement uniquement)

`npm run dev -- --host 0.0.0.0`, puis ouvrir `/gallery.html`.
L'entrée Vite de production reste limitée à `index.html` et `overlay.html` :
la galerie, les arrière-plans et les mocks ne sont pas importés par l'application.

La galerie monte **le vrai composant App**, avec les mocks IPC/événements Tauri
officiels. Les états sont atteints par les formulaires et boutons existants,
sans modifier le moteur ni injecter de paramètres dans App.
Les commandes réseau sont simulées : aucune capture, microphone ou API cloud.

- `state` : `home-empty`, `home-typed`, `listening`, `importing`, `planning`,
  `thinking`, `running`, `explain`, `qa`, `done`, `error`, `palette`, `palette-empty`.
- `bg` : `pioneer` (ciel mauve), `terracotta`, `grey`, `busy` (tableur clair fictif).
- `material` : `native` pour la teinte translucide, `css` pour le repli sombre.

Exemple : `/gallery.html?state=palette&bg=terracotta`.
Sur le tableur, sélectionner `material=css` pour évaluer le repli Linux.
Le navigateur floute son arrière-plan CSS ; il ne prouve pas la vibrance native.
Les effets natifs `hudWindow` (macOS) et `acrylic` (Windows) sont déclarés dans
`src-tauri/tauri.conf.json`, selon le schéma Tauri 2 / tauri-utils 2.10.2.
La palette et la barre forment une seule surface, sans espace transparent.

Après `npm run build`, `node dev/check-design.mjs` vérifie mécaniquement les
couleurs, les rayons, les emoji, les gradients et l'exclusion de la galerie.
Les dégradés de paysages de la galerie et celui du curseur conservé sont des
exceptions voulues, pas des accents de l'interface.

Limites : les paysages sont des études CSS, pas des reproductions photographiques.
La vibrance macOS, l'acrylique Windows, la lisibilité sur un bureau natif et la
performance sur appareil de référence demandent une recette sur ces plateformes.
