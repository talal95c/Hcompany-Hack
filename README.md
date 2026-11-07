# Hcompany-Hack — le prof qui te regarde faire

> Colle n'importe quel tuto Blender. On le transforme en prof qui te regarde faire, **dans ta version du logiciel**, et qui s'efface quand tu sais.
> Puis la même leçon prouvée devient le **contexte** qui permet à un agent (Holo) de le faire à ta place, en 4 actions au lieu de 20.

## Le problème
Apprendre Blender, c'est un tuto YouTube d'un côté, le logiciel de l'autre :
- tu fais sans arrêt pause et retour en arrière ;
- le tuto est sur une autre version que la tienne ;
- personne ne te dit si tu as bien fait ;
- une semaine plus tard, tu ne sais plus le refaire.

Les assistants « je vois ton écran, je te montre le bouton » (Clicky, HeyBraza, Nudge…) répondent à la question, mais tu n'apprends pas, et ils ne vérifient pas que le tuto marche sur ta version.

## Ce qu'on fait
1. **Préparer** : le tuto (vidéo ou doc) devient des étapes, chacune avec un test sur l'état réel de Blender. Holo **prouve** la leçon sur ta version avant de te l'enseigner.
2. **Apprendre** : tu fais, l'add-on Blender voit ce que tu fais, et le prof réagit tout seul (erreur, blocage, réussite). L'aide monte par paliers quand tu bloques et diminue au fil des réussites : voix → zone surlignée → pointeur → démo.
3. **Déléguer** : une fois que tu sais le faire, « fais-le » est débloqué. Holo exécute avec la leçon comme contexte.
4. **Face Agent / entreprise** : chaque leçon prouvée est exportée en H Skill et via MCP. C'est du contexte réutilisable par n'importe quel agent sur les logiciels de l'entreprise.

## Partenaires
| Brique | Rôle |
|---|---|
| **H Company · Holo4** (Models API, Agents API, Skills, MCP) | voir et pointer sur ton écran, prouver la leçon en sandbox, « fais-le » |
| **TypeSafe · Jev** | décisions rapides et ambiguës : intention d'une phrase, bloqué ou pas, quel palier d'aide |
| **Gladia** | transcription du tuto et de la voix de l'utilisateur en direct |
| **Linkup** | doc de l'éditeur quand une étape a changé de version |
| **Devin** | écrit les tests manquants et répare les procédures (PR) |

Tous les services IA sont dans le cloud ; rien ne tourne en local à part notre code.

## Plateformes
Démo sur **macOS**. Tout est prévu pour tourner aussi sous **Windows** : Python, add-on Blender, Tauri v2. Les spécificités de chaque OS (permissions, mise à l'échelle de l'écran, capture) sont isolées dans `desktop/` et `engine/platform/`.

## Le dépôt
```
contracts/  formats partagés (leçon, événements, ordres) — figés en premier
engine/     orchestrateur Python (la boucle en direct)
addon/      add-on Blender « Œil » (capteur + surlignage)
desktop/    overlay Tauri v2 (pointeur, pastille, ✓)
prep/       préparation : tuto → leçon prouvée
agent/      face Agent : H Skills + serveur MCP
lessons/    leçons prouvées (donut…)
bench/      mesures du J1 (Holo, operators, Jev, overlay)
tests/      tests automatiques
docs/       vision, optimisations, schémas
```
Le détail est dans [ARCHITECTURE.md](ARCHITECTURE.md).

## État
Socle étape 0 disponible sur `dev` : contrats JSON Schema draft 2020-12 et fixtures, packages Python importables, tests de contrats et scaffold desktop Tauri v2. Aucun moteur pédagogique, capture, injection ou client IA opérationnel à ce stade. Installation et commandes exactes : [environnement de développement](docs/environnement-dev.md).


## Conception détaillée et statut
La référence d'implémentation est l'[index du design](docs/README.md). Desktop est une app Tauri v2 : Rust possède deux fenêtres, capture avec exclusion explicite, injection enigo, permissions et sidecar Python ; web reste sans politique pédagogique. Tous les services IA sont cloud, Holo sert aussi de LLM. TTS reste ouvert : Gladia ne synthétise pas la voix. Les inventaires décrivent notre code existant porté à adapter, pas du code déjà livré ici. Les durées sont des objectifs (est.) sauf les mesures publiques explicitement identifiées. Les schémas SVG historiques sont conservés sans régénération ; les documents détaillés et ADR font foi en cas d'écart.
