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

Les boutons « Get started » de Pro et Team ouvrent une session **Stripe Checkout** en mode abonnement (mensuel ou annuel selon le toggle, nombre de sièges ajustable pour Team). La clé secrète reste côté serveur.

```bash
STRIPE_SECRET_KEY=sk_test_... npm run dev   # ou dans site/.env.local (ignoré par git), voir .env.example
```

- `src/plans.ts` : catalogue unique (prix affichés = prix facturés). Learner 0 $, Pro 15 $/mois ou 12 $/mois facturé 144 $/an, Team 36 $/mois ou 29 $/mois facturé 348 $/an, par siège.
- `server/stripe.ts` : `POST /api/checkout` crée la session, `GET /api/checkout-session?id=cs_…` confirme le retour. Les produits `rio_pro`/`rio_team` et leurs prix (lookup keys `rio_<plan>_<month|year>`) sont créés automatiquement au premier achat, puis recréés si un montant change dans `src/plans.ts`.
- Servi par Vite en dev et en `npm run preview` (plugin `stripe-api` dans `vite.config.ts`), et par les fonctions `api/` (signature Web `Request → Response`) pour un déploiement serverless avec `site/` comme racine.
- Retour : `/?checkout=success&session_id=…` affiche une confirmation (plan et e-mail lus côté serveur), `/?checkout=cancel#pricing` indique qu'aucun paiement n'a été fait. `SITE_URL` fixe l'origine des URL de retour en production.
- Carte de test : `4242 4242 4242 4242`, date future, CVC quelconque.
