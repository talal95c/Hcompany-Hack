# prep/repair/

## Responsabilité
Réparation asynchrone Devin.

## Entrées
check manquant ou procédure cassée.

## Sorties
PR à relire et retester, jamais publication directe.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/preparation.md) et [guide des agents](../../AGENTS.md).

## État et validation
`write_repair_request` écrit sous out/repair les demandes JSON (contrat, fixture, attendu, version), sans réseau. Tests de contenu et confinement du nom de fichier dans tests/prep. Revue et réparation restent humaines/asynchrones.
