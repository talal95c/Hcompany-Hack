# Architecture v3 : optimisée, sans rien enlever

_7 nov. 2026. « (est.) » = estimation à mesurer au J1 ; le reste est sourcé (liens en bas)._

## Le principe qui change tout
**Rien de lent ni de fragile sur le chemin critique.** Tout ce qui est prévisible est calculé **pendant la préparation** (tests, explications, audio, cibles). Tous les services IA sont dans le cloud (aucun modèle en local). En direct, le chemin critique ne passe que par l'add-on, notre code et deux appels courts (Gladia, Jev). Holo (API H) pointe **en avance**, pas au moment où l'utilisateur attend.

Toutes les fonctionnalités restent : n'importe quel tuto Blender, la preuve sur ta version, le prof proactif, l'aide qui diminue, les questions à la voix, « fais-le », la délégation, et la face Agent (Skill, MCP).

## 10 optimisations

| # | Avant (v2) | v3 | Gain | Compromis |
|---|---|---|---|---|
| 1 | Holo appelé au moment du besoin, sur une capture plein écran | **Holo4 35B-A3B via l'API H, appelé en avance** (pendant que l'utilisateur fait l'étape N), avec un prompt système stable pour profiter du **cache d'entrée** (0,03 $ au lieu de 0,30 $ par million de tokens) | la latence réseau et modèle est cachée derrière l'action de l'utilisateur | il faut une bonne connexion ; on prévoit un partage 4G en secours |
| 2 | Capture plein écran Retina | **Capture recadrée sur la zone** (l'add-on donne les rectangles des zones Blender) | environ 5 à 10 fois moins de tokens (est.) donc plus rapide et plus précis | aucun |
| 3 | Holo appelé à chaque pointage | **Cache des cibles** indexé par (version Blender, taille de la zone, échelle UI, cible) + **pré-localisation de l'étape N+1** | pointage ≈ 0 ms quand c'est en cache | le cache saute si la zone bouge (l'add-on le détecte) |
| 4 | Le surlignage passe par l'overlay | **Le palier ② est dessiné dans Blender** (`draw_handler_add`, `POST_PIXEL`) + « je t'ouvre le menu » (`wm.call_menu`) | instantané, sans erreur, sans calcul Retina | ne couvre pas les menus déroulants → là, c'est Holo + l'overlay |
| 5 | L'add-on interroge l'historique | **Événements poussés** : `msgbus` + `depsgraph_update_post` + lecture de `operators` toutes les 100 ms | détection d'action ≤ 100 ms | `operators` ne voit que les opérateurs `REGISTER` ; le reste se voit dans l'état de la scène (`depsgraph`) |
| 6 | 1 appel Jev par question | **Connexion persistante** + **questions non sensibles en lot** (bloqué ? quel palier ?) ; l'intention de la phrase reste seule dans son appel | on évite environ 200 ms de poignée de main TCP ; 5 questions vont aussi vite qu'une | l'intention reste isolée parce que plusieurs questions dans un même appel se biaisent (vu sur LawHack) |
| 7 | Gladia attend la fin de la phrase | **Transcriptions partielles** + Jev lancé **dès le partiel** (spéculatif), confirmé sur le final | ~0,3 à 1 s gagnée sur chaque question vocale (est.) | un appel Jev en trop quand le partiel change ; c'est presque gratuit |
| 8 | LLM + TTS en live pour les « pourquoi ? » | **« Pourquoi » pré-écrit et pré-enregistré par étape** à la compilation ; le LLM live, en streaming phrase par phrase, ne sert qu'aux questions hors script | réponse instantanée pour la question la plus fréquente | le hors script reste à 1,5 à 3 s (est.) ; on lit un « bonne question… » en cache pendant ce temps |
| 9 | Préparation : Holo rejoue tout (3 à 5 min, est.) | **Preuve par différence** : chaque étape dont l'opérateur existe est prouvée par exécution `bpy` directe (millisecondes) ; **Holo ne rejoue que le chemin d'interface qui a changé** ; la mémoire ReStep réutilise ce qui est déjà prouvé ; Devin passe en asynchrone | **< 1 min (est.)** pour un tuto connu ; ~2 min pour un nouveau | la preuve `bpy` prouve le résultat, pas le chemin d'interface ; c'est pourquoi Holo garde les étapes modifiées |
| 10 | « Fais-le » = boucle Holo complète | **Holo `agent_loop` avec la leçon comme contexte** (la démo de la thèse du mentor), et **relecture `bpy` en secours** si Holo dépasse le délai | ~22 s / 4 actions dans ReStep, sinon instantané | aucun : la relecture est un secours, pas la démo |

## Ce que ça donne en direct (est., à mesurer)
| Moment | v2 | v3 |
|---|---|---|
| Erreur détectée et dite | < 1 s | **< 0,6 s** (add-on + test local + Jev sur connexion ouverte + audio en cache) |
| Bloqué → zone surlignée | Jev + overlay | **≈ 0,3 s** (dessin dans Blender) |
| Bloqué → pointeur exact | 1 à 3 s | **≈ 0 s (pré-localisé ou en cache) / 1 à 3 s sinon (est.)** |
| « Pourquoi ? » prévu | 1,5 à 3,5 s | **< 1 s** |
| « Pourquoi ? » hors script | 1,5 à 3,5 s | 1,5 à 3 s, masqué par une phrase d'attente |
| Préparation | 3 à 5 min | **< 1 min (connu) / ~2 min (nouveau)** |

## Moins complexe à construire
- **Un seul processus Python asyncio** (on étend ReStep) : bus d'événements, socket vers l'add-on, WebSocket vers l'overlay. Pas de micro-services.
- **Overlay Electron « bête »** : il affiche ce qu'on lui envoie (pointeur, pastille, ✓), sans aucune logique. L'échelle Retina vient du `scaleFactor` d'Electron.
- **Le chemin critique ne dépend que de Gladia et Jev.** Holo travaille en avance ; LLM et TTS ne servent qu'en secours. Tout est dans le cloud.
- **Mode réseau dégradé automatique** : si Jev dépasse 800 ms, une règle prend le relais ; sans Gladia, on tape au clavier ; sans LLM, on joue la réponse en cache.

## Innovations en plus (ça reste innovant, et plus)
1. **Mémoire de compétences à répétition espacée** (comme une appli de flashcards, mais pour des gestes) : chaque compétence a un palier de départ qui baisse à chaque réussite, et elle revient en défi quelques jours plus tard.
2. **Le cache des cibles est partagé** : la première personne qui suit un tuto sur Blender 5.2 rend le pointage instantané pour toutes les suivantes. C'est un effet réseau.
3. **La preuve par différence** est l'argument « on prouve en secondes que ton tuto de 2019 marche en 5.2 », et ça reprend directement la mémoire de ReStep.
4. **Les deux faces lisent la même leçon** : la leçon prouvée qui guide Léa est la Skill qu'exécute l'agent.

## Risques restants (à mesurer au J1)
1. Latence réelle de l'API Holo sur une capture recadrée, depuis le réseau du hackathon. Si le pointage en avance ne suffit pas, le secours est la zone surlignée + le raccourci clavier.
2. Actions du tuto donut visibles dans `operators` ou dans `depsgraph`.
3. Jev sur 20 phrases réelles.
4. Dessin `draw_handler` dans l'en-tête de la vue 3D.

## Sources
- Holo4 Models API, prix et cache : https://hcompany.ai/models-api · localisation : https://hub.hcompany.ai/models-api/element-localization
- Jev, latence et lot de questions mesurés : https://github.com/WallerChen/jev-measured · doc : https://openrouter.ai/docs/guides/community/jev
- Gladia, partiels et endpointing : https://docs.gladia.io/chapters/live-stt/features/partial-transcripts · prix : https://www.gladia.io/pricing
- Blender `operators` (REGISTER uniquement) : https://devtalk.blender.org/t/custom-addon-missing-in-operator-log/19699 · `draw_handler_add` : https://docs.blender.org/api/current/bpy.types.Space.html
