# engine/learner/

## Responsabilité
Mémoire des compétences.

## Entrées
défis et aides utilisées.

## Sorties
maîtrise, due_at et déblocage.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/engine.md) et [guide des agents](../../AGENTS.md).

## État et validation
`LearnerMemory` conserve les compétences en JSON avec écriture temporaire, fsync et
remplacement atomique. Une mémoire corrompue est sauvegardée avant remise à zéro.
Répétition espacée de type SM-2 : intervalles en jours (est.), à calibrer. Un défi
réussi sans aide débloque la délégation ; pour une compétence non désirée, seule la
confirmation explicite est nécessaire. Les erreurs de stockage restent explicites.
Tests : `pytest -q tests/engine/test_learner.py`.
