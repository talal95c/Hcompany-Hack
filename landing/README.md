# site

Landing de **Rio** (textes produit en anglais), construite en React/Vite sur la mise en page de la landing [spartanai.framer.website](https://spartanai.framer.website/) (template Framer « Spartan » de Delani), capturée avec REA (`rea analyze-web-bundle`) et un relevé des styles calculés du site d'origine.

```bash
npm install
npm run dev     # http://localhost:5173
npm run build
```

`npm run render:usecases` exports the three vector Remotion demos to `out/*.mp4`; their live players pause offscreen and show a still verified step with reduced motion (Remotion licensing applies).

- `src/sections.tsx` : sections de la page (nav, hero, bento, works, capabilities, vision, témoignages, vidéo, process, équipe, pricing, FAQ, insights, footer).
- `src/ui.tsx` : boutons, marquees, révélation au scroll lettre par lettre, compteurs, icônes.
- `public/assets/` : images et vidéo du template original (réduites). Elles appartiennent au template : à remplacer avant toute publication.

## Paiement (Stripe Checkout)

Les boutons « Get started » de Pro et Team ouvrent une session Stripe Checkout en abonnement (mensuel ou annuel selon le toggle, sièges ajustables pour Team). En production, la route est servie par le Worker de `../platform` (secret `STRIPE_SECRET_KEY`) ; en local, par le plugin `stripe-api` de `vite.config.ts` :

```bash
STRIPE_SECRET_KEY=sk_test_... npm run dev   # ou dans .env.local (ignoré par git)
```

- `src/plans.ts` : catalogue unique, les prix affichés sont les prix facturés.
- `server/stripe.ts` : `POST /api/checkout` et `GET /api/checkout-session?id=cs_…`. Les produits et prix Stripe sont créés au premier achat.
- Carte de test : `4242 4242 4242 4242`.
