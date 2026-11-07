# Guide des agents de développement
## Lire avant de coder
Ce projet neuf transforme un tutoriel Blender en leçon prouvée, enseigne sur le poste de l'utilisateur et exporte la même procédure aux agents. Projet neuf, ne référence pas de code externe. Décrire les briques adaptées comme « notre code existant porté » sans attribution à un autre projet.
Ordre de lecture : [PRD](PRD.md), [architecture](docs/architecture/vue-ensemble.md), [index](docs/README.md), [contrat leçon](docs/contrats/lecon.md), puis document du composant et ADR concernés.
## Règles d'or
- Le code valide le certain, Jev tranche l'ambigu, Holo voit et agit. Tous les modèles sont cloud.
- Un seul engine Python asyncio ; add-on et desktop sont des clients fins. Ne pas déplacer les décisions dans le front.
- Pas de ✓ sans check récent ; unknown n'est pas pass. Seulement les révisions prouvées sont exportées.
- Aucune clé dans git, logs, prompts ou WebView. Captures minimales et consenties ; rétention cloud à vérifier.
- Les actions sur le bureau exigent consentement, verrou, arrêt prioritaire et test après action.
- Toute durée non mesurée porte « (est.) ». Une cible de recette n'est pas une mesure.
## Carte
contracts/ : futurs JSON Schema, autorité des formats ; engine/ : bus, lesson, checks, policy, learner, cache, services, fallback, platform, debug ; addon/ : bpy ; desktop/src-tauri/ : Rust natif ; desktop/web/ : interface ; prep/ : ingest, compile, ui_map, prover, sandbox, docs_search, repair ; agent/ : Skill/MCP ; lessons/ : artefacts ; bench/ : mesures ; tests/ : tests. [Responsabilités](docs/equipe-et-workflow.md).
## Conventions
Python 3.11, asyncio, annotations de types aux frontières, ruff ; exceptions explicites et annulation propagée. Rust dans desktop/src-tauri/, aucune logique native dans le web. JSON Schema dans contracts/ après gel M0 : versionner les changements incompatibles, fixtures normales/vides/erreur. Textes produit en français, identifiants techniques stables en anglais. Ne pas écrire du Python arbitraire depuis un modèle : sélectionner une procédure/check autorisé.
## Tests et définition de fini
Le socle étape 0 fournit pyproject.toml, les schémas et fixtures, des packages Python importables et un scaffold Tauri. Installer le projet dans un venv Python 3.11, puis lancer `ruff check .` et `pytest -q` à la racine ; `cargo check --locked` dans desktop/src-tauri. Voir les [commandes d'installation](docs/environnement-dev.md). Le moteur pédagogique et les backends natifs restent à implémenter ; les tests actuels valident les contrats et imports, pas une leçon en direct.
À chaque évolution : vérifier liens Markdown, cohérence des contrats et marquage des estimations ; couvrir nominal/vide/erreur, timeouts, reconnexion et recette Mac [M0–M6](docs/tests-et-jalons.md) selon le périmètre. Fini = contrat respecté, checks exécutés et résultats rapportés, limites explicites, documentation actualisée, PR relue ; build Linux ne valide pas capture/injection macOS. Gradium TTS est prévu localement côté Rust selon la nouvelle décision étape 0 (note dans desktop/README.md), sans implémentation ni modification des autres services cloud à ce stade.
