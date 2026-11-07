# Vision produit + architecture — agent d'apprentissage computer-use (hackathon)

_Version 1 — 7 nov. 2026. Sources vérifiées le jour même, liens en bas._

## 0. Ce qu'on a appris en regardant le marché (le constat qui change tout)

« Une IA qui voit ton écran, te parle et pointe où cliquer pour apprendre Blender/Photoshop/Excel » **existe déjà, au moins 8 fois** :

| Produit | Ce qu'il fait | Ce qu'il ne fait pas |
|---|---|---|
| HeyClicky (Farza) | hotkey + voix, pointe à l'écran, mode « agent » qui fait la tâche | pas de parcours, pas de vérification de ce que TU fais |
| HeyBraza | « you make the clicks, so the skill is yours », Blender/Photoshop/Premiere, 10 $/mois, « step-by-step courses » | réactif (tu demandes → il pointe), pas de preuve d'acquisition |
| Nudge | tuteur dans le logiciel, 80 cours, « each step checked as you go » | cours écrits à la main, catalogue fermé |
| TryUncle, Pointy, Alfred, Ourguide, User Manual | variantes « pointe le bouton » | idem |
| Adobe AI Assistant (Photoshop web) | « do it for me, or show me how » natif | Photoshop seulement |

**Conclusion de la discussion interne : « il pointe et c'est toi qui cliques » n'est plus un différenciateur.** Si on pitch ça, le jury pense « HeyBraza ». Il faut un angle que ces produits ne peuvent pas copier en une semaine.

## 1. Discussion interne — 3 visions confrontées

**A. « Tuteur proactif »** — il intervient sans qu'on le lui demande dès que tu te trompes.
- Pour : Jev le rend possible (décision en 70–500 ms annoncés, 0,042 $/M tokens), personne ne le fait.
- Contre : seul, c'est une feature, pas un produit ; risque d'être intrusif.

**B. « N'importe quel tuto → cours vivant dans TA version »** — tu colles un lien YouTube (ou une page de doc), l'agent le transforme en leçon interactive, **rejouée et prouvée par Holo sur ta version du logiciel** avant de te l'enseigner.
- Pour : attaque LE problème n°1 des tutos (« le tuto est en Blender 2.8, j'ai la 5.2, le menu n'est plus là ») ; catalogue infini sans écrire de cours (contrairement à Nudge) ; c'est exactement ce que ReStep sait faire (tutos Blender 2.79 rejoués en 5.2 : 18/19 PASS avec preuve).
- Contre : la compilation prend du temps (pas instantané) → à faire en préparation, pas en live.

**C. « Preuve de compétence »** — modèle de l'apprenant, aide qui diminue, défi final sans aide, révision espacée, « passeport » des compétences.
- Pour : c'est ce qui fait la différence entre apprendre et être assisté ; mesurable en démo.
- Contre : invisible en 3 min de démo si on ne le met pas en scène.

**Verdict : B est le cœur (le « pourquoi nous »), A est le moteur (le « wow » live), C est la preuve (le « ça marche »).** Les trois tiennent ensemble car ils partagent le même objet : une **leçon = suite d'étapes avec un test vérifiable sur l'état de l'appli**.

## 2. Vision produit finale

### One-liner
**« Colle n'importe quel tuto. On le transforme en prof qui te regarde faire, dans ta version du logiciel, et qui s'efface quand tu sais. »**

### Le problème (pour le pitch, en bénéfices)
1. Les tutos sont sur une autre version, une autre langue, un autre écran que le tien.
2. Personne ne vérifie que tu as bien fait : tu découvres l'erreur 10 étapes plus tard.
3. Tu reproduis, tu ne retiens pas : une semaine après, tu ne sais plus le refaire.
4. Les assistants IA actuels attendent qu'on leur pose la question — et souvent font à ta place.

### Les 3 promesses
1. **Ton tuto, ta version** — n'importe quelle vidéo/doc devient une leçon ; si un bouton a bougé depuis le tuto, on l'a déjà retrouvé (et prouvé) pour toi.
2. **Il te voit faire** — chaque étape est validée sur l'état réel de l'appli (pas « à l'œil ») ; il réagit dès que tu dévies, pas seulement quand tu demandes.
3. **Il s'efface** — l'aide baisse à chaque étape réussie ; tu finis par un défi sans aide ; il te le refait faire plus tard.

### Parcours utilisateur (ce que voit l'utilisateur)
1. **Choisir** : coller un lien YouTube / une doc, ou dire « je veux faire un donut dans Blender ».
2. **Préparation (≈~3–5 min (estimé), barre de progression honnête)** : « 14 étapes trouvées · 3 ont changé depuis la vidéo (menu déplacé) · toutes vérifiées sur Blender 5.2 ».
3. **Leçon** : une pastille/notch discrète + voix. Pour chaque étape :
   - il dit l'objectif (« ajoute un tore ») et **le pourquoi** (1 phrase de concept) ;
   - **tu fais** ; validation instantanée ✓ quand l'état de l'appli correspond ;
   - si tu bloques ou dévies → **échelle d'aide** : ① indice verbal → ② zone surlignée → ③ pointeur exact + raccourci → ④ « regarde » : il le fait dans une copie/sandbox (ou fait puis annule), puis **tu refais**.
4. **Défi final** : refaire une variante sans aide (« maintenant fais un cube biseauté »).
5. **Fiche de fin** : compétences acquises, raccourcis appris, niveau d'aide utilisé par étape (courbe qui descend), rappel programmé.

### Modes
- **Guidé** (défaut) · **Défi** (aide seulement si demandée) · **Pourquoi ?** (question libre à la voix : « à quoi sert ce bouton ? ») · **Fais-le** (délégation explicite, ce n'est pas le mode par défaut).

### Différenciation (tableau pitch)
| | Clicky / HeyBraza / Pointy | Nudge | Adobe Assistant | **Nous** |
|---|---|---|---|---|
| Voit l'écran, pointe | ✓ | ✓ | Photoshop seul | ✓ |
| Leçon à partir de N'IMPORTE quel tuto | — | — (cours maison) | — | **✓** |
| Tuto ancien adapté + prouvé sur ta version | — | — | — | **✓ (Holo, sandbox)** |
| Vérifie sur l'état réel de l'appli | — | ✓ (annoncé) | n/a | **✓ (API de l'appli)** |
| Réagit sans qu'on demande | — | ? | — | **✓ (Jev)** |
| Aide dégressive + défi final + révision | — | partiel | — | **✓** |
_(colonnes concurrents : d'après leurs sites au 07/11/2026 ; à re-vérifier avant le pitch)_

### Ce qu'on ne fait PAS (scope hackathon)
- Pas de catalogue de 100 logiciels : **Blender en démo phare, Excel en 2ᵉ démo courte** (preuve que l'archi est générique). Photoshop = slide « next ».
- Pas de modèle entraîné : on n'entraîne aucun poids ; l'« apprentissage » du système = mémoire des chemins prouvés (comme ReStep) + modèle de l'apprenant.
- L'agent n'agit **jamais** sur le fichier de l'utilisateur sans son accord (mode ④ = sandbox ou fait-puis-annule).


## 2bis. Retour mentor (07/11) → le produit a deux faces, un seul actif

**Ce qu'a dit le mentor :**
1. Les agents computer-use sont corrects en général, mais sur un logiciel où ils n'ont pas de données, il suffit de leur donner le contexte (« clique là, puis là, fais ça ») : ça coûte moins cher, ça va plus vite et c'est plus fiable. Tout est une histoire de contexte.
2. Ce qu'on peut vendre aux entreprises, c'est du **contexte personnalisé** sur leurs propres applis et web apps internes, jusqu'à automatiser ce qui ne l'est pas aujourd'hui.
3. Son vécu : ChatGPT avec une capture d'écran, « va dans Paramètres, clique sur ce bouton »… et lui qui répond « tu peux pas le faire directement ? ».

**Notre lecture : une procédure prouvée, deux usages.**

| | Face 1 · Apprendre (humain) | Face 2 · Exécuter (agent) |
|---|---|---|
| Qui l'utilise | l'apprenant, un nouvel employé | Holo, ou n'importe quel agent via H Skill / MCP |
| Ce qu'on livre | leçon guidée, aide qui diminue | Skill avec les étapes, les cibles et un test par étape |
| Pourquoi c'est mieux | dans ta version, vérifiée | moins cher, plus rapide, plus fiable |
| Preuve (chiffres ReStep, `runs/`) | Blender 2.79 → 5.2 : 18/19 réussies avec preuve | Holo seul : échec après 20 actions / 188 s · Holo + ReStep : réussite en 4 actions / 22 s · 24/24 contre 17/21 |

Les chiffres de ReStep démontrent mot pour mot la thèse du mentor : avec le contexte, l'agent fait 5× moins d'actions, est 8× plus rapide et réussit 24 tâches sur 24.

**La boucle qui relie les deux faces :**
- Un humain montre ou explique une procédure (Gladia) → elle devient une leçon **et** une Skill.
- Une mise à jour du logiciel casse la procédure → ReStep la répare, et la leçon comme la Skill se mettent à jour d'elles-mêmes.
- **« Apprends-le une fois, délègue-le ensuite »** : quand une compétence est acquise (défi réussi sans aide), le bouton « fais-le pour moi » se débloque. C'est la réponse à la frustration n°3 : on ne refuse jamais de faire, on fait d'abord comprendre. Et « fais-le » reste accessible à tout moment pour ce que tu ne veux pas apprendre.

**Business :**
- B2C / étudiants : apprendre Blender, Photoshop, Excel (acquisition, démo du hackathon).
- B2B : onboarding sur les outils internes, procédures toujours à jour après chaque mise à jour du logiciel, et les mêmes procédures exécutées par des agents. C'est l'origine de ReStep (back-office, ERP). Ce qui se vend : le **contexte de l'entreprise** (sa bibliothèque de procédures prouvées), pas le modèle.

**Recommandations pour ne pas se diluer :**
- La démo live montre **une seule face : Apprendre** (Blender). La face Agent tient en 15 s : « la leçon que tu viens de suivre, Holo l'exécute maintenant en 4 actions », en direct, avec la Skill exportée. Ensuite une slide B2B.
- Pas de « on automatise tout ce qui n'est pas automatisable » sans preuve : on s'en tient aux chiffres mesurés ci-dessus.
- La cible B2B dans le pitch : onboarding et procédures internes (le problème déjà démontré par ReStep), pas « tous les logiciels ».

## 3. Architecture

```
┌──────────────────────── PRÉPARATION (hors ligne, ~3–5 min (estimé)) ─────────────────────────┐
│ Source : YouTube (sous-titres/Gladia) │ doc web (Linkup) │ démo enregistrée          │
│        ↓                                                                            │
│ Compilateur de leçon (LLM)  → étapes {objectif, concept, raccourci, test d'état}    │
│        ↓                                                                            │
│ Preuve (ReStep, système B) : Holo4 rejoue chaque étape dans une SANDBOX de la       │
│ version de l'utilisateur ; le vérificateur (bpy / Excel) confirme ; si cassé →      │
│ réparation (exploration Holo / doc Linkup) → chemin prouvé + coords + capture      │
│        ↓                                                                            │
│ Leçon prouvée (JSON) + cache des cibles UI par version                              │
└─────────────────────────────────────────────────────────────────────────────────────┘
┌──────────────────────────── LIVE (sur le PC de l'utilisateur) ─────────────────────┐
│ Capteurs  : arbre d'accessibilité (agent-desktop, refs + diff) · état de l'appli    │
│             (add-on Blender bpy en socket local · Excel via AppleScript/JXA) · voix (PTT)  │
│             · capture écran seulement sur besoin                                    │
│        ↓ événements (changement d'état, inactivité, parole)                         │
│ Cerveau rapide = Jev (System One)  — décisions typées + probabilités :              │
│   step_done? (Noul, + test d'état déterministe) · deviation? (Choice: ok/erreur     │
│   connue/hors sujet) · stuck? · hint_level (Choice 0–4) · intent de la phrase       │
│   (question / « fais-le » / frustration / « suivant »)                              │
│        ↓                                                                            │
│ Orchestrateur de leçon (code, machine à états) + modèle de l'apprenant              │
│        ↓                                    ↘ question ouverte « pourquoi ? »        │
│ Sorties : overlay (halo, pointeur, flèche) ·      LLM (réponse courte, contexte      │
│ voix TTS (phrases pré-écrites de la leçon)        = étape + écran)                  │
│ Ciblage : ref accessibilité → sinon cache prouvé → sinon Holo4 localisation live    │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Rôle de chaque partenaire (et pourquoi lui)
| Brique | Rôle | Pourquoi |
|---|---|---|
| **Jev (TypeSafe)** | toutes les décisions live fermées : étape faite ? erreur ? bloqué ? quel niveau d'aide ? intention de la phrase | annoncé 70–500 ms, sortie typée + probabilité calibrée → on agit au-dessus d'un seuil, on escalade en dessous ; pas de texte = pas d'hallucination dans la boucle |
| **Holo4 (H Company)** | (1) préparation : rejouer/prouver le tuto dans une sandbox ; (2) live : localiser un élément quand l'accessibilité ne suffit pas (Blender dessine son UI lui-même) ; (3) mode « regarde » | VLM computer-use, 80,8 % OSWorld (35B-A3B), 0,30 $/M in, API compatible OpenAI, localisation d'éléments dédiée (exemple doc = capture Blender) |
| **agent-desktop (Vercel)** | lire l'arbre d'accessibilité en JSON avec refs, diff entre deux snapshots | rapide, sans pixels, Mac/Windows/Linux |
| **ReStep** | moteur de préparation : rejouer, vérifier, réparer quand la version a changé, mémoire des chemins prouvés | déjà démontré sur Blender 2.79 → 5.2 avec vérificateur bpy |
| **Vérificateurs d'appli** | vérité terrain pour valider une étape | Blender : bpy (objets, modificateurs, mode) ; Excel (Mac) : AppleScript/JXA ou relecture du .xlsx |
| **LLM (Mistral/OpenAI)** | compiler la leçon, répondre aux « pourquoi ? » | seul endroit où on génère du texte libre, hors chemin critique |

### Règles de conception (et pourquoi)
1. **Le déterministe d'abord** : une étape est validée par un test d'état (bpy/Excel) ; Jev n'arbitre que l'ambigu (« il a fait un tore mais à la mauvaise taille, c'est grave ? »). → fiable en démo.
2. **Événementiel, pas de polling** : on n'appelle Jev que sur changement d'état / 8 s d'inactivité / parole. → tient dans le quota Codiv (60 req/min mesuré sur LawHack) et coûte ~0.
3. **Une question Jev par appel quand elle est sensible** (mesuré sur LawHack : 2 questions dans un appel faussent la 2ᵉ). → précision.
4. **Holo hors du chemin critique live** : les cibles sont pré-calculées pendant la préparation ; Holo live seulement en repli. → latence.
5. **Jamais d'action sur le fichier de l'utilisateur** sans « fais-le » explicite ; démonstrations en sandbox. → confiance, et cohérent avec « apprendre ».

### Format d'une étape (contrat entre préparation et live)
```json
{
  "id": "add_torus",
  "goal": "Ajoute un tore",
  "concept": "Les maillages de base sont dans Ajouter > Maillage",
  "shortcut": "Maj+A",
  "check": {"type": "bpy", "expr": "any(o.type=='MESH' and 'Torus' in o.name for o in bpy.data.objects)"},
  "known_errors": [{"id": "added_cube", "hint": "C'est un cube, on veut un tore"}],
  "proven_path": [{"target": "menu Ajouter", "ref_or_coords": "...", "screenshot": "..."}],
  "hints": ["Le menu pour ajouter un objet...", "highlight:menu Ajouter", "point:Maillage > Tore", "demo"],
  "changed_since_source": true
}
```

## 4. Scénario de démo (3 min)
1. **(20 s) Le problème** : une vraie vidéo « donut Blender » de 2019 à côté de Blender 5.2 : le menu de la vidéo n'existe plus.
2. **(30 s) Colle le lien** : préparation accélérée → « 14 étapes · 3 changées depuis la vidéo · toutes prouvées sur ta version ». On montre Holo qui rejoue dans la sandbox (vidéo x8).
3. **(80 s) Leçon live** : Talal fait ; ✓ instantanés ; il ajoute volontairement un cube au lieu d'un tore → l'agent réagit **sans qu'on lui demande** (Jev) ; il bloque sur le modificateur → indice ① puis pointeur ③.
4. **(30 s) Défi sans aide** + fiche : courbe du niveau d'aide qui descend à 0.
5. **(20 s) Excel** : même moteur, TCD en 4 étapes → « marche sur n'importe quel logiciel ».

## 5. Faisabilité (honnête)
| Morceau | Risque | Pourquoi / repli |
|---|---|---|
| Vérificateur Blender bpy | faible | déjà fait dans ReStep |
| Holo rejoue un tuto Blender | moyen | ReStep 18/19 avec preuve ; repli : leçon pré-préparée pour la démo |
| Compiler un tuto YouTube en étapes + tests | moyen | sous-titres + LLM ; les tests d'état générés sont la partie fragile → bibliothèque de tests Blender réutilisables |
| Jev « étape faite / erreur / bloqué » | faible-moyen | questions simples sur état structuré ; à mesurer sur 20 cas avant la démo |
| Overlay + voix | faible | déjà fait dans Gerald (si réutilisable) |
| Excel (Mac) | moyen | pas de COM sur Mac → AppleScript/JXA (`tell application "Microsoft Excel"`) ou relecture du .xlsx sauvegardé (openpyxl) ; repli Excel web |
| Latence perçue | moyen | test d'état local (<100 ms) + Jev (70–500 ms annoncés) ; Holo hors chemin critique |

## 6. Questions encore ouvertes
Tranché le 07/11 : ReStep = notre équipe, on réutilise son moteur · démo sur **Mac** (accessibilité macOS via agent-desktop, overlay natif) · équipe de 3 + IA.

Reste ouvert : nom du produit.

## Sources (consultées le 07/11/2026)
- HeyClicky https://www.heyclicky.com/ · clicky open source https://github.com/farzaa/clicky
- HeyBraza https://heybraza.com/ · Nudge https://nudgelearn.com/ · TryUncle https://tryuncle.com/ · Pointy https://www.pointy.help/ · Alfred https://learnwithalfred.ai/
- Adobe Research, AI Assistant Photoshop https://research.adobe.com/news/do-it-for-me-or-show-me-how-the-research-behind-photoshops-ai-assistant/
- Holo4 / Models API https://hcompany.ai/models-api · localisation https://hub.hcompany.ai/models-api/element-localization · https://huggingface.co/Hcompany/Holo4-35B-A3B
- Jev https://typesafe.ai/blog/introducing-system-one-models-and-jev · InfoQ https://www.infoq.com/news/2026/10/typesafe-ai-jev-released/
- computah https://github.com/musubipapi/computah · agent-desktop https://github.com/vercel-labs/agent-desktop · ReStep (README fourni)
