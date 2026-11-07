# site

Recréation en React/Vite de la landing [spartanai.framer.website](https://spartanai.framer.website/) (template Framer « Spartan » de Delani), capturée avec REA (`rea analyze-web-bundle`) et un relevé des styles calculés du site d'origine.

```bash
npm install
npm run dev     # http://localhost:5173
npm run build
```

- `src/sections.tsx` : sections de la page (nav, hero, bento, works, capabilities, vision, témoignages, vidéo, process, équipe, pricing, FAQ, insights, footer).
- `src/ui.tsx` : boutons, marquees, révélation au scroll lettre par lettre, compteurs, icônes.
- `public/assets/` : images et vidéo du template original (réduites). Elles appartiennent au template : à remplacer avant toute publication.
