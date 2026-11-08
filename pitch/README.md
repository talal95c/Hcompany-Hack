# Rio pitch

Standalone React / TypeScript / Vite deck. 16 main slides + appendix. French script: [SCRIPT.md](SCRIPT.md), also available with **N**.

## Run

```sh
cd pitch
npm install
npm run dev
npm run build
npm run build:single
npx vite preview --port 4174 --host
```

Build generates the QR SVG locally. Assets are self-contained; the Remotion compositions are copied from landing (including TutorialPlayer inside Blender), rendered in grayscale so orange belongs only to the deck's ghost cursor. Slide 11 uses a static, deck-styled console mock for a consistently finished presentation in browser and PDF. No paid template assets.

`npm run build:single` writes `out/rio-pitch.html`: double-click to open offline, with JS, CSS, fonts, QR and imagery inlined. It does not replace the normal `dist/` build. `node scripts/check-single.mjs` verifies local-file rendering with Chrome CDP on port 29229.

Reveal/close use monochrome compressed versions of the two brand hill images (each under 65 KB). The baked wordmark is removed from the reveal image's white sky; the deck uses only the standalone R mark. Motion respects reduced-motion preferences. Print mode freezes players and renders all animated content at its final state.

Navigation: left/right, Space, PageUp/PageDown, Home/End. Click either half of the screen. N toggles notes, F fullscreen. Hashes are one-based: `#5`. Invalid hashes fall back to slide 1. The fixed 1920×1080 stage scales to fit any viewport.

## PDF

With preview running:

```sh
mkdir -p out/shots
google-chrome --headless --no-sandbox --disable-gpu --no-pdf-header-footer --print-to-pdf="$PWD/out/rio-pitch.pdf" --timeout=15000 --virtual-time-budget=8000 'http://localhost:4174/?print'
```

`?print` stacks all 17 pages at 1920×1080, disables enter animations and freezes the compositions on informative frames. Use landscape/no margins if printing manually. The generated PDF and screenshots are ignored by Git.

With Chrome CDP already on port 29229: `node scripts/shots.mjs` captures every slide and tests navigation. The deck has no separate pre-existing test suite.

## Sources and claim boundaries

- Gartner, **2024 Market Guide for Digital Adoption Platforms**, via [WalkMe](https://www.walkme.com/content/2024-gartner-market-guide-for-digital-adoption-platforms/): **$816.4M 2023 market revenue estimate**, rounded to $816M on slide.
- [SAP, 12 September 2024](https://news.sap.com/2024/09/sap-completes-walkme-acquisition/): completed WalkMe acquisition, **about $1.5B equity value**.
- [Grand View Research, corporate e-learning report](https://www.grandviewresearch.com/industry-analysis/corporate-e-learning-market-report), 2025 report, **$104.3B global market in 2024**, rounded to $104B. This is adjacent context, explicitly **not Rio's TAM**. Sources researched 8 November 2026.
- No YouTube usage figure is included: the located Google study was from 2017 and is too old to strengthen this pitch.

Technical wording checked against README, youtube.rs, holo.rs, qa.rs, watch.rs, voice.rs, stt.rs, autopilot.rs, devin.rs and platform/src/ingest.ts. Models are configurable defaults, not immutable deployment guarantees. Web-page text is read first; the web agent is conditional. Devin compiles eligible successful runs, not all runs. Fast mode suppresses narration. Local watch detects changes; Holo verifies screenshots (not offline-only AI). Voice needs setup; Phonon weights have a non-commercial license. Pricing is copied exactly from landing/src/plans.ts.

The checkout integration exists, but production Stripe live mode was **not verified**, so this is not claimed. Enterprise SSO is a roadmap item, not a shipped claim. Economics are an architectural hypothesis, not measured margins: ongoing guidance still costs inference. Competitor positioning says “traditional authored flows”, not that competitors cannot use AI. Compositions are illustrative, not evidence of live task completion. Desktop runs from source; one-click installer planned.
