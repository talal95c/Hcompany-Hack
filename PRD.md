# PRD — le prof qui te regarde faire (Blender, macOS)

_Version 1 · 7 nov. 2026 · Statut : à valider par l'équipe_

## 1. Problème
Apprendre un logiciel complexe comme Blender, c'est aujourd'hui un tuto YouTube d'un côté et le logiciel de l'autre :
- pause et retour en arrière en permanence ;
- le tuto est sur une autre version ;
- personne ne vérifie ce que tu fais ;
- une semaine plus tard, tu ne sais plus le refaire.

Les assistants qui voient l'écran donnent la réponse, mais ne rendent pas autonome et ne prouvent pas que le tuto marche sur ta version.

## 2. Proposition
> Colle n'importe quel tuto Blender. On le transforme en prof qui te regarde faire, dans **ta** version, et qui s'efface quand tu sais. Une fois que tu sais faire, la même leçon permet à Holo de le faire pour toi.

Deux faces d'une même leçon prouvée :
- **Apprendre** (un humain) : guidage, vérification, aide qui diminue.
- **Exécuter** (un agent) : la leçon sert de contexte à Holo, et elle est exportée en H Skill et via MCP pour les équipes et les entreprises.

## 3. Utilisateurs
| Persona | Besoin | Ce qu'on lui donne |
|---|---|---|
| **Léa, débutante Blender** | suivre un tuto sans se perdre et retenir | leçon guidée, prof proactif, défi final |
| **Créateur pressé** | ne pas apprendre ce qui l'ennuie | « fais-le », débloqué une fois la compétence acquise |
| **Équipe en entreprise** | former les nouveaux arrivants et automatiser les procédures internes | bibliothèque de procédures prouvées, servies aux humains et aux agents (en slide pendant la démo) |

## 4. Objectifs et non-objectifs
**Objectifs du hackathon**
- Démo en direct sur Mac : le donut Blender, étapes 1 à N, sans fausse démo.
- On montre l'aide qui diminue : la dernière étape est faite sans aide.
- « Fais-le » : Holo agit sur le vrai écran avec la leçon comme contexte.
- Un tuto inconnu court (3 étapes) préparé devant le jury.

**Non-objectifs (pour l'instant)**
- Photoshop et Excel en direct (slide ou vidéo de 15 s).
- Le packaging Windows (le code reste compatible).
- Les comptes, le paiement et le cloud multi-utilisateurs.

## 5. Stack imposée
| Besoin | Service |
|---|---|
| Vision, pointage, computer use, LLM (compilation, « pourquoi ») | **Holo4 · H Company** (Models API, offre Pro) |
| Skills, agents | **H Agents API** |
| Décisions rapides | **Jev · TypeSafe** (clé Codiv) |
| Transcription (tuto + voix en direct) | **Gladia** |
| Recherche web | **Linkup** |
| Réparation et tests manquants | **Devin** |
| Synthèse vocale | ⚠️ **à décider** : Gladia ne fait que de la transcription, pas de synthèse vocale |

Tous les services IA sont dans le cloud. Seul notre code tourne sur le Mac.

## 6. Fonctionnalités
| ID | Fonctionnalité | Priorité | Critère d'acceptation |
|---|---|---|---|
| F1 | **Leçon guidée** : étapes, consigne, test par étape, ✓ | P0 | les étapes du donut s'enchaînent, chaque ✓ correspond à un test réel sur la scène |
| F2 | **Add-on « Œil »** : flux d'événements et état de la scène | P0 | une action dans Blender apparaît sur la page de debug en ≤ 100 ms |
| F3 | **Prof proactif** : erreur, blocage, réussite, avec des seuils pour ne pas agacer | P0 | cube au lieu de tore → correction en < 1 s ; 20 s sans progrès → palier suivant ; pas plus d'une intervention toutes les 30 s |
| F4 | **Paliers d'aide** ① voix → ② zone surlignée dans Blender → ③ pointeur Holo → ④ démo | P0 | chaque palier se déclenche dans l'ordre et l'aide utilisée baisse sur la leçon |
| F5 | **Pointage Holo** : capture recadrée, cible de l'étape suivante calculée en avance, cache | P0 | le pointeur tombe sur le bon élément sur Retina ; ≈ 0 s quand la cible est en cache |
| F6 | **Voix en entrée** : Gladia en direct + intention par Jev (question, « fais-le », frustration, « chut ») | P0 | 20 phrases réelles classées correctement à ≥ 90 % |
| F7 | **Voix en sortie** : phrases pré-générées + réponses aux « pourquoi » | P0 | consignes et « pourquoi » prévus joués instantanément |
| F8 | **« Fais-le »** : Holo pilote la souris et le clavier sur le Mac, avec la leçon comme contexte | P0 | l'étape est faite et le test passe ; relecture `bpy` en secours |
| F9 | **Préparation** : tuto → étapes → tests → preuve par différence → leçon prouvée | P0 | donut préparé à l'avance ; un tuto de 3 étapes préparé en direct en < 2 min |
| F10 | **Face Agent** : export en H Skill + serveur MCP | P1 | un agent MCP trouve et exécute la leçon |
| F11 | **Mémoire de compétences** (répétition espacée) + défi final sans aide | P1 | le palier de départ baisse après une réussite |
| F12 | « Pourquoi » hors script (Holo en LLM, streaming) | P1 | réponse en ≤ 3 s, avec une phrase d'attente |
| F13 | Recherche Linkup quand une étape a changé et que la preuve échoue | P1 | une étape cassée est réparée à partir de la doc |
| F14 | Devin : écrit le test manquant ou répare la procédure (PR) | P2 | une PR est ouverte |

## 7. Exigences non fonctionnelles
- **Latence (estimations à mesurer)** : erreur signalée < 0,6 s ; zone surlignée ≈ 0,3 s ; « pourquoi » prévu < 1 s.
- **Coût** : < 0,30 € par leçon de 20 min (estimation, tarifs publics).
- **Quotas** : Codiv à 60 req/min, donc on déclenche sur événement et on n'interroge pas en boucle.
- **macOS (Apple Silicon)** : Blender 5.x ; permissions Enregistrement de l'écran et Accessibilité vérifiées au premier lancement ; échelle Retina gérée.
- **Windows** : pas de code propre à macOS en dehors de `engine/platform/` et `overlay/`.
- **Confidentialité** : on envoie seulement des captures recadrées, rien n'est stocké côté serveur, et l'overlay est exclu des captures.
- **Mode dégradé** : Jev > 800 ms → une règle ; sans Gladia → clavier ; sans réseau → partage 4G et vidéo de secours.

## 8. Inventaire : ce qu'on a, ce qu'on modifie, ce qu'on crée
Notre code interne existant (moteur de preuve en sandbox, overlay, vérificateurs) est porté dans ce dépôt, renommé et adapté à la nouvelle structure.

| Composant | Dossier | Déjà disponible | À modifier | À créer |
|---|---|---|---|---|
| Overlay | `overlay/` | Electron transparent, laisse passer les clics, exclu des captures, raccourci pour parler, marqueur en coordonnées normalisées | packaging macOS, permissions micro et écran, ✓ et pastille | protocole WebSocket avec l'engine |
| Add-on | `addon/` | serveur dans Blender (timers, socket) qui expose l'état de la scène (objets, modificateurs, matériaux, mode, rendu) | passer de « question → réponse » à un **flux poussé** | `operators`, `msgbus`, `depsgraph`, rectangles des zones, `draw_handler`, `wm.call_menu`, relecture `bpy` |
| Tests | `engine/checks/` | 10 tests « état → (ok, détail) » | paramétrables par leçon (noms, valeurs) | ~5 tests pour le donut (tore, subdivision, lissage, matériau, glaçage…) |
| Pointage | `engine/services/holo/` | localisation d'un élément sur une capture (thinking off, temperature 0) | capture recadrée, coordonnées Retina | travail en avance, cache |
| Computer use | `engine/services/holo/` | boucle « capture → Holo → une action » | **moteur souris et clavier pour macOS** (aujourd'hui uniquement X11) | mode « fais-le » sur le vrai écran |
| Carte des menus | `prep/ui_map/` | arbre des menus par version (2.79b, 5.2.3) avec l'opérateur derrière chaque entrée, libellés | ajouter la version du Mac de démo | description de cible, nom de menu pour `wm.call_menu`, différence entre versions |
| Transcription | `prep/ingest/` | vidéo → Gladia (horodatage au mot, vocabulaire) → étapes | brancher sur le compilateur | — |
| Compilation | `prep/compile/` | modèle de procédure (objectif, chemin ancien et nouveau, alternatives) | — | Holo en LLM : étapes → choix de test, « pourquoi », erreurs connues |
| Preuve | `prep/prover/` | planificateur (exécuter, rejouer, explorer, observer, consolider), surprise visuelle, sandbox Blender sous Linux | — | **preuve par différence** (`bpy` direct si inchangé) |
| Recherche doc | `prep/docs_search/` | Linkup → étapes | — | — |
| Réparation | `prep/repair/` | Devin : test manquant, page de doc (PR) | — | — |
| Face Agent | `agent/` | procédures prouvées servies par MCP, export en H Skill | format leçon → Skill | — |
| Mesures | `bench/` | 12 sondes de localisation avec la vérité terrain | — | variante recadrée, `operators` du donut, Jev sur 20 phrases |
| **Orchestrateur** | `engine/` | — | — | **tout** : bus, machine à états, politique d'aide, mémoire de compétences, Jev, Gladia en direct, cache, mode dégradé, page de debug |
| Contrats | `contracts/` | — | — | leçon, événements, ordres (JSON Schema) |

## 9. Jalons testables (en vrai, sur le Mac)
| Jalon | Ce que tu testes |
|---|---|
| M0 | `contracts/` figés ; `bench/` : Holo (latence et précision) et `operators` sur le donut |
| M1 | add-on installé → tu fais une action → tu la vois sur la page de debug avec sa latence |
| M2 | donut, étapes 1 à 3 : ✓, erreur signalée, zone surlignée |
| M3 | voix : Gladia + intention par Jev ; voix du prof |
| M4 | pointeur Holo sur le bon bouton, cible en avance et cache |
| M5 | « fais-le » : Holo agit sur ton Mac |
| M6 | préparation d'un tuto de 3 étapes en direct ; export en Skill et MCP |

## 10. Risques
| Risque | Parade |
|---|---|
| Holo trop lent sur le réseau du hackathon | travail en avance + cache ; zone surlignée + raccourci clavier |
| Actions invisibles dans `operators` | lecture de l'état de la scène (`depsgraph`) |
| « Fais-le » sur Mac (permissions Accessibilité, Retina) | testé dès M0 ; relecture `bpy` en secours |
| Commentaires du prof trop fréquents | seuils, pause de 30 s, « chut » |

## 11. Questions ouvertes
1. Synthèse vocale : quel service ? (Gladia n'en fait pas.)
2. Version exacte de Blender et modèle du Mac de démo.
3. Nom du produit.
