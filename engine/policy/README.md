# engine/policy/

## Responsabilité
Politique d'aide.

## Entrées
erreurs, progrès, horloge et chut.

## Sorties
palier ou abstention.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/engine.md) et [guide des agents](../../AGENTS.md).

## État et validation
`HelpPolicy` publie décisions et commandes validées sur le bus. Horloge injectée,
erreurs connues dédupliquées, absence de progrès pertinent, undos, cooldown différé,
silence et aide explicite sont couverts. Jev ne tranche que l'ambigu ; timeout,
réponse invalide ou panne donnent une règle locale et un signal dégradé unique.

Paliers successifs : texte/audio en cache, région/menu réellement identifiés,
pointeur issu du cache valide ou d'une capture fournie, puis procédure sûre.
Sans cible Holo, rester au palier ② avec indication F3. Le replay ne déclenche
pas immédiatement undo : l'orchestrateur doit attendre son acquittement et appeler
`finish_demo()` avec checkpoint sûr. Ce module ne décide jamais de la sécurité
d'un checkpoint. L'orchestrateur doit relayer les diagnostics `Topic.DEBUG`
au desktop et appeler `process()` sur événements et timer pour les reports différés.
Tests : `pytest -q tests/engine/test_policy.py`.
