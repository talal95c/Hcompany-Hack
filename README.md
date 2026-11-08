# Rio

<img src="brand/rio-mark-black.svg" alt="Logo Rio" width="64">

**Colle un tutoriel : Rio te guide pas à pas dans ton propre logiciel, puis peut refaire avec ton accord ce que tu as appris.**

**[Accéder à Rio](https://rio.vignemale.com)** · **[Installer l’application](#installation)** · **[Voir l’architecture](#architecture)**

Le site donne accès à la plateforme d’équipe. L’application de bureau se lance depuis les sources ; un installeur en un clic est prévu.

## Problématique

Apprendre Blender, DaVinci Resolve ou un outil interne, c’est souvent jongler entre un tutoriel et son logiciel :
- faire pause et revenir en arrière pour retrouver la bonne manipulation ;
- chercher un menu qui a changé de place dans sa version ;
- rester bloqué sans savoir pourquoi le résultat diffère ;
- devoir tout réapprendre une semaine plus tard.

Un tutoriel montre une procédure, mais ne voit pas ce qui se passe sur ton écran. Rio accompagne la mise en pratique, directement là où tu travailles.

## Solution

1. **Pars de ton besoin.** Colle un lien YouTube ou une page web, choisis un tutoriel dans la bibliothèque, ou décris ce que tu veux apprendre. Rio prépare des étapes avec un résultat à atteindre.
2. **Apprends dans ton logiciel.** Une barre flottante et un curseur superposé montrent où agir. Rio observe l’écran et suit ta progression, plutôt que de rejouer une vidéo figée.
3. **Pose tes questions.** Tu peux écrire ou parler à Rio pendant la leçon. Il répond, peut montrer l’élément concerné et garde le contexte pour la suite. La voix nécessite une configuration supplémentaire.
4. **Délègue avec ton accord.** Une leçon réussie peut être réutilisée. La petite barre en haut de l’écran propose « Rio le fait pour toi » : l’exécution démarre après ton acceptation, peut être arrêtée et vérifie les résultats à l’écran avant d’annoncer la réussite.
5. **Partage avec ton équipe.** La [plateforme Rio](https://rio.vignemale.com) rassemble tutoriels, base de connaissances, membres et statistiques d’utilisation.

L’application vise macOS. L’autopilote fonctionne aussi sous Linux X11 ; Wayland est explicitement refusé. La précision du pointage et les demandes vagues restent des limites : Rio ne garantit pas la réussite de toute tâche.

## Architecture

```mermaid
flowchart TD
    User[Utilisateur] --> UI[React : barre, curseur, notch]
    UI <--> Desktop[Tauri / Rust : tuteur, capture, voix, autopilote]
    Desktop <--> App[Logiciel de l’utilisateur]
    Desktop <--> Holo[H Company / Holo : vision et raisonnement]
    Desktop <--> Voice[Gladia : transcription / Phonon : voix locale]
    Desktop <--> API[Cloudflare Worker : API Rio]
    Web[Site et console web] <--> API
    API <--> Data[D1 et service de connaissances]
```

Le tuteur organise une leçon en **jalons vérifiables à l’écran**, pas en coordonnées fixes. Holo analyse les captures pour guider l’utilisateur. L’autopilote réutilise ces jalons et contrôle leur résultat sur de nouvelles captures. Certains parcours réussis peuvent aussi être compilés en scripts testés via Devin.

### Organisation du dépôt

| Dossier | Rôle et documentation |
|---|---|
| [`src/`](src/) | Interface React/TypeScript : barre de commande, curseur et notch. |
| [`src-tauri/`](src-tauri/) | Application native Rust/Tauri : tuteur, capture, voix et autopilote. |
| [`landing/`](landing/) | Site public [rio.vignemale.com](https://rio.vignemale.com). [Guide du site](landing/README.md). |
| [`platform/`](platform/) | Worker Cloudflare, API, console et D1. [Installation et API](platform/README.md). |
| [`platform/knowledge/`](platform/knowledge/) | Service de recherche dans la base de connaissances. |
| [`tutorials/`](tutorials/) | Tutoriels d’exemple sous forme de graphes de jalons. |
| [`sim/`](sim/) | Scénarios et applications de test. [Guide du simulateur](sim/README.md). |
| [`tools/`](tools/) | Outils, dont l’explorateur des journaux de session. |
| [`demo/`](demo/) | Préparation des démonstrations et installation de skills d’exemple. |
| [`brand/`](brand/) | Logos et visuels Rio. |
| [`.prime/agent/skills/rio-harness-core/`](.prime/agent/skills/rio-harness-core/) | [Guide technique pour les agents](.prime/agent/skills/rio-harness-core/SKILL.md), invariants et scripts de validation. |

### Services et recherche web

H Company fournit la vision et la planification, Gladia transcrit voix et vidéos YouTube, et Phonon synthétise la voix localement. Cloudflare héberge le site, la console et l’API.

<a id="web-search-h-agents-and-linkup"></a>

- **Pendant une leçon** : base de connaissances de l’équipe, puis Linkup si configuré ; sans résultat, Holo peut répondre à partir de ses connaissances, avec cette origine signalée.
- **Tutoriel créé depuis un objectif** : agent H `h/deep-search-pro`, puis Linkup en secours.
- **Page web collée** : texte de la page ; l’agent H `h/web-surfer-pro` intervient si le contenu est insuffisant.
- **Lien YouTube** : transcription Gladia, puis préparation des étapes par Holo.

### Validation et journaux

Le [simulateur d’apprenant](sim/README.md) exécute le vrai tuteur dans un Chrome sans interface, avec des profils et des erreurs rejouables. Des contrôles de l’état réel de l’application notent le résultat et repèrent les réussites annoncées à tort. Ces évaluations complètent les tests Rust ; elles ne prouvent pas une fiabilité universelle.

Pour explorer les sessions locales :

```bash
python3 tools/session_explorer.py --open
```

Les journaux dans `sessions/` contiennent des captures de l’écran : ils ne doivent pas être publiés sans vérification.

## Installation

### Application de bureau — macOS

Prérequis : [Node.js](https://nodejs.org) **22.12 ou plus récent**, [Rust](https://rustup.rs) et les outils Apple (`xcode-select --install`).

```bash
git clone https://github.com/talal95c/Hcompany-Hack.git
cd Hcompany-Hack
cp .env.example .env
```

Renseigne `HAI_API_KEY` dans `.env` avec une [clé H Company](https://platform.hcompany.ai/settings/api-keys), puis lance Rio :

```bash
npm install
npm run tauri dev
```

Dans **Réglages Système → Confidentialité et sécurité**, autorise le terminal pour l’enregistrement de l’écran, l’accessibilité et la surveillance de l’entrée. Ajoute l’autorisation microphone pour la voix, puis redémarre Rio.

Ouvre la barre avec **⌥ ⇧ Espace** ou l’icône de la barre des menus. Décris ton objectif ou colle un lien de tutoriel, puis suis le curseur.

Options dans [`.env.example`](.env.example) :
- `GLADIA_API_KEY` active la transcription vocale ;
- `HF_TOKEN` donne accès à [Phonon 40m](https://huggingface.co/gradium/phonon-40m-multilingual), après acceptation des conditions ; sans accès, Rio utilise le modèle public 31m. Les poids Phonon sont sous licence non commerciale CC BY-NC 4.0 ;
- `RIO_API_URL=https://rio.vignemale.com` et `RIO_API_TOKEN` relient l’application à l’équipe ; le jeton se crée dans **Settings** sur la console ;
- `LINKUP_API_KEY` ajoute la recherche web de secours.

### Développement web

Pour travailler uniquement sur le site :

```bash
cd landing
npm install
npm run dev
```

Pour la console, l’API et les migrations locales, suivre le [guide de la plateforme](platform/README.md#run-it-locally). Les clés restent dans les fichiers locaux ignorés par Git ou dans les secrets Cloudflare.

### Vérifications

Depuis la racine, `npm run build` vérifie TypeScript et construit l’interface. Les tests natifs se lancent avec `cd src-tauri && cargo test`. Les tests web et de simulation sont détaillés dans les guides de la [plateforme](platform/README.md) et du [simulateur](sim/README.md).
