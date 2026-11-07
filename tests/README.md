# tests/

## Responsabilité
Validation automatique et fixtures.

## Entrées
contrats, faux services et scènes de test.

## Sorties
rapports nominal/vide/erreur et non-régression.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../docs/tests-et-jalons.md) et [guide des agents](../AGENTS.md).

## État et validation
`test_contracts.py` vérifie les quatre schémas draft 2020-12, chaque fixture valide/invalide, la couverture des types, les exemples JSON des documents de contrat et l'import des packages Python. Exécuter `ruff check .` puis `pytest -q` à la racine. Aucun service cloud ni Blender n'est requis pour ces tests. Les tests du moteur et des backends natifs restent à écrire.
