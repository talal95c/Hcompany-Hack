# prep/compile/

## Responsabilité
Compilation Holo LLM.

## Entrées
texte, carte et bibliothèque checks.

## Sorties
étapes typées, pourquoi, erreurs et audio si TTS.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/preparation.md) et [guide des agents](../../AGENTS.md).

## État et validation
`HoloCompiler.compile(transcript, ui_map, lesson_id=..., blender_version=...)` appelle
Holo4 via AsyncOpenAI (HAI_API_KEY), température 0, JSON object et réflexion désactivée.
Modèle par défaut holo4-27b ; modèle et alternative configurables sur HTTP 404/429.
Leçon validée par
JSON Schema avant preuve, avec un nouvel essai si JSON invalide ; tokens et latences
mesurés. `reselect(step, docs)` fournit le callback de sélection autorisée.

Les procédures/checks inconnus ne sont pas corrigés : originaux conservés dans
compile_report.json/rejections, étape marquée handoff. Pour rester conforme au schéma,
un check inconnu est représenté par object_exists avec type/primitive unresolved,
jamais exécuté : le prover écrit une réparation avec l'original. Tests unitaires et
live couvrent compilation, rejets, JSON invalide et timeout.
