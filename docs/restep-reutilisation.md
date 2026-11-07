# Ce qu'on réutilise de ReStep (branche `refonte-abm`)

_Lu le 7 nov. 2026 : 4 000 lignes de Python, 1 add-on Electron, 10 capacités Blender._

## Verdict
**Environ la moitié de notre architecture existe déjà dans ReStep.** La préparation et la face Agent sont quasiment complètes. Côté direct, on trouve des briques solides (overlay, guidage Holo sur le vrai écran, vérificateurs), mais **la boucle d'apprentissage elle-même n'existe pas** : pas d'écoute en continu, pas de politique d'aide, pas de Jev, pas de modèle de l'apprenant. C'est elle, notre « engine ».

## Réutilisé tel quel ou presque
| ReStep | Ce que c'est | Chez nous |
|---|---|---|
| `assistant/main.js` + `ui/assistant/guide.js` | Electron : fenêtre transparente toujours au premier plan, **laisse passer les clics**, exclue des captures (`setContentProtection`), Ctrl+Space pour parler, capture d'écran avec `scaleFactor`, marqueur placé en coordonnées normalisées | **`overlay/`** : c'est déjà notre overlay. Il est packagé pour Windows aujourd'hui ; il faut l'adapter à macOS (packager, permissions) |
| `restep_api.guide()` + `guide_steps()` | Holo localise l'élément suivant **sur le vrai écran de l'utilisateur** à partir d'une capture (redimensionnée en 1280, thinking off, `temperature 0`) | **`engine/services/holo`** : on y ajoute la capture recadrée, le travail en avance et le cache |
| `probe_localization.py` | 12 sondes Blender avec la vérité terrain, qui mesurent la précision et la latence de Holo | **`bench/`** : c'est déjà la mesure J1 n°1 ; on ajoute la variante recadrée |
| `verify.py` (`CHECKS`) | 10 tests « état → (ok, détail) » : biseau, subdivision, fusion de sommets, résolution, matériau, calque, lissage, sphère UV, export… | **`engine/checks/`** : le début de notre bibliothèque de tests (objectif ~15) |
| `verifier_server.py` | serveur dans Blender (`bpy.app.timers`, 127.0.0.1:8765) qui expose l'état complet de la scène | **`addon/`** : la base de l'add-on « Œil ». On passe d'un mode « question → réponse » à un **flux poussé** (opérateurs, `msgbus`, `depsgraph`, zones), plus surlignage et ouverture de menu |
| `apps/blender/menus/menus_<v>.json` + `oplabels_<v>.json` | **arbre complet des menus de chaque version** (lu dans `bl_ui`), avec l'opérateur derrière chaque entrée (1 368 libellés en 5.2.3) | trois usages chez nous : **(1)** description de cible pour Holo (« Ajouter › Maillage › Tore ») ; **(2)** nom de menu pour `wm.call_menu` (palier ②) ; **(3)** **preuve par différence** : on compare les chemins entre deux versions **sans lancer Holo** |
| `apps/blender/capabilities.json` | par procédure : objectif, chemin ancien et nouveau, alternatives, preuves dans les sources | modèle direct pour **`contracts/lesson`** |
| `transcribe.py`, `teach.py`, `check_gladia.py` | vidéo → Gladia (horodatage au mot, vocabulaire de l'interface) → étapes ; Whisper en secours | **`prep/`** (compilation du tuto) |
| `meta.py` (System M) + `surprise.py` | table de transitions EXECUTE / REPLAY / EXPLORE / OBSERVE ; surprise = écart avec la mémoire, sur une grille 32×20 en ~1 ms | **`prep/`** pour la preuve ; option en direct : « l'écran ne ressemble à rien de connu » (une fenêtre inattendue s'est ouverte) sans appeler de modèle |
| `restep_core`, `restep_mcp.py`, `h_skills.py`, `h_agent.py` | procédures prouvées servies par MCP, export en H Skill, verrou sur le bureau | **face Agent**, sans modification |
| `devin.py`, `devin_handoff.py`, `observe_docs.py` | Devin écrit le test manquant ; Linkup lit la doc | **`prep/`**, sans modification |

## Ce qui manque (notre travail)
1. **La boucle en direct** (`engine/`) : bus d'événements, machine à états de la leçon, politique d'aide, Jev, Gladia live côté apprenant, mémoire de compétences, cache.
2. **L'add-on en mode écoute** : flux poussé, opérateurs, zones, `draw_handler`, `wm.call_menu`.
3. **macOS** : ReStep fait tourner ses sandboxes sous **Linux (Xvfb + Xlib, `fcntl`, `launch_blender.sh`)** et son assistant est packagé **pour Windows**. Notre répartition : **préparation et preuve sur une machine Linux dans le cloud** (comme ReStep), **le direct sur le Mac ou le PC de l'utilisateur**.
4. **« Fais-le » sur le vrai écran** : `agent_loop` agit avec `screen.py`, uniquement sous X11. Sur Mac ou Windows, il faut un autre moteur de souris et de clavier, ou bien l'add-on rejoue l'action en `bpy`. → question ouverte.

## Points d'attention vus dans `PREP_REPORT.md`
- **H, palier gratuit = uniquement `holo3-1-35b-a3b` à 10 req/min ; `holo4-*` renvoie 402 « add credits »** → il faut acheter des crédits avant le hackathon (c'est aussi ce qui rend « travailler en avance » possible).
- Gladia : la clé manquait de leur côté (Whisper local a servi de secours).
- Les versions préparées sont Blender **2.79b** et **5.2.3 LTS** (1280×800).
