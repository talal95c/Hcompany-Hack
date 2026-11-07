# prep/docs_search/

## Responsabilité
Recherche éditeur Linkup.

## Entrées
étape cassée et version.

## Sorties
sources et candidat à retester.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/preparation.md) et [guide des agents](../../AGENTS.md).

## État et validation
`docs_search` appelle Linkup via httpx, filtre docs.blender.org avec includeDomains, délai explicite de 15 s et latence mesurée en logs. Tests timeout et clé absente ; test live opt-in avec LINKUP_API_KEY. Aucun candidat n’est accepté sans nouveau check.

Une version explicite (`blender_version`) ou présente dans la requête du prover
(`Blender 4.5.9 …`) limite la recherche et les résultats aux chemins du manuel/API
de cette série (`4.5`). Les liens `latest`, `current` et des autres versions sont
écartés, sans réécriture d'URL. Aucun résultat compatible signifie une liste vide.
