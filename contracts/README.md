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
Les enveloppes et payloads connus sont fermés ; les objets volontairement non détaillés par le contrat (état d'objet Blender, propriétés opérateur, paramètres de procédure et action native) restent ouverts. Aucun codec audio n'est inventé ici. La leçon v2 exige `app` et accepte les cibles génériques ; les huit checks Blender (également nommés `blender.*`) et les checks `element_exists`, `element_value`, `element_state`, `window_title`, `visual_assert` ont des paramètres fermés. La v1 Blender reste acceptée. Les ajouts WebSocket d'accessibilité et `highlight.rect` sont additifs en version 1.0 ; ils ne prouvent pas que les backends natifs sont implémentés.

La validation du schéma ne constitue ni autorisation d'exécuter, ni preuve : unicité des id d'étape, existence des fichiers de preuve, vrais hashes de sources, compatibilité Blender, ordre des séquences, révision courante et consentement actif doivent être vérifiés au runtime. Le hash illustratif du donut reste accepté structurellement, pas comme preuve publiable. Les futurs handlers pourront ignorer les événements d'une extension mineure inconnue avant validation ; ils ne doivent pas les traiter comme un type connu. Une version majeure incompatible est refusée.

L'extension additive de surveillance ajoute `watch`/`unwatch` à `a11y.request`,
`events_supported` optionnel à `a11y.result`, les notifications `a11y.event`
corrélées par `watch_id` et séquence, et `a11y.cancel`. Les requêtes peuvent porter
`generation`, `focus_epoch` et `deadline_ms`. Une notification invalide les valeurs
précédentes et demande une lecture fraîche ; elle ne contient aucun texte de l'app.
Un backend sans événements conserve le polling et les checks de fraîcheur.
Le champ optionnel `a11y.event.scoped` indique qu'une ré-résolution ciblée peut
être tentée malgré `reconcile=true`. Il n'autorise jamais à réutiliser une ref
périmée : un `get` réussi retourne une nouvelle ref après validation du
descripteur. En cas d'échec, le moteur conserve la réconciliation complète.
