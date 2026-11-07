# prep/prover/

## Responsabilité
Preuve par différence.

## Entrées
étapes et checkpoints.

## Sorties
preuves bpy/UI et statut par étape.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/preparation.md) et [guide des agents](../../AGENTS.md).

## État et validation
`prove_lesson` enchaîne checkpoints, checks topologiques, traces du planificateur et preuves JSON/manifest. Cartes inconnues ou modifiées : job Holo pending ; check absent : réparation locale. Échec : Linkup puis callback async `reselect(step, docs)` et un seul nouvel essai. Tests stubs et leçon réelle à trois primitives dans tests/prep.

Après réussite d'un candidat, la leçon conserve la procédure réellement prouvée,
ses préconditions, la cible UI et les signatures/empreintes correspondantes.
Le cache n'accepte pas une preuve dont la procédure sélectionnée diffère de celle
de l'étape ; les anciennes preuves incohérentes doivent être recalculées.
