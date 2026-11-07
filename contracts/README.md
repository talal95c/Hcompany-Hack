# contracts/

## Responsabilité
Formats partagés JSON Schema draft 2020-12, implémentés dans les quatre fichiers `*.schema.json` de ce dossier.

## Entrées
exemples de contrats et décisions M0.

## Sorties
schémas versionnés et fixtures.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../docs/contrats/lecon.md) et [guide des agents](../AGENTS.md).

## État et validation
`lesson.schema.json`, `addon-events.schema.json`, `commands.schema.json` et `desktop-ws.schema.json` décrivent les messages documentés. `examples/<schema>/valid/` contient les fixtures attendues valides et `invalid/` les contre-exemples. Exécuter `pytest -q` depuis la racine après installation Python ; les exemples JSON de la documentation sont aussi testés. La référence relative du WebSocket vers commands doit être résolue avec un registre local, sans téléchargement réseau.

## Limites de cette validation structurelle
Les enveloppes et payloads connus sont fermés ; les objets volontairement non détaillés par le contrat (état d'objet Blender, propriétés opérateur, paramètres de procédure et action native) restent ouverts. Aucun codec audio ni protocole d'action native n'est inventé ici. `object_exists` est le seul check dont les paramètres sont actuellement spécifiés ; chaque nouveau check devra étendre la whitelist et les tests.

La validation du schéma ne constitue ni autorisation d'exécuter, ni preuve : unicité des id d'étape, existence des fichiers de preuve, vrais hashes de sources, compatibilité Blender, ordre des séquences, révision courante et consentement actif doivent être vérifiés au runtime. Le hash illustratif du donut reste accepté structurellement, pas comme preuve publiable. Les futurs handlers pourront ignorer les événements d'une extension mineure inconnue avant validation ; ils ne doivent pas les traiter comme un type connu. Une version majeure incompatible est refusée.
