# addon/

## Responsabilité
Capteur bpy et commandes bornées.

## Entrées
socket engine et état Blender.

## Sorties
événements poussés, surlignage et replay.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../docs/architecture/addon.md) et [guide des agents](../AGENTS.md).

## État et validation
Implémentation disponible : client socket asyncio dans un thread sans bpy, files bornées,
réabonnement msgbus au chargement, handlers depsgraph/undo persistants, observation des opérateurs
REGISTER, snapshots, sélection/mode, régions et heartbeat. Le timer principal vide les commandes
et observe à une cadence cible de 100 ms (est.). Les deltas sont agrégés ; les résultats de
commandes sont conservés pour déduplication pendant la session. Une reconnexion recommence par
hello et snapshot, sans rejouer les commandes en attente de l'ancienne connexion.

Les enveloppes entrantes et sortantes sont validées avec les JSON Schema du dépôt. Une enveloppe
invalide ou une autre session est ignorée sans mutation. Un résultat incertain après coupure
exige réconciliation par snapshot côté engine. Les résultats connus restent consultables par
command_id, y compris après reconnexion.

### Installation et lancement
Garder le checkout complet (les schémas restent dans `contracts/`, voisin de `addon/`). Installer
`jsonschema>=4.22,<5` dans le Python de Blender, puis rendre le checkout importable dans Blender
ou lier son dossier `addon/` au dossier scripts/addons de Blender. Appeler `addon.register()` ;
`addon.unregister()` retire timers, abonnements, handlers et dessins, puis ferme le transport.

Le lanceur fournit `ADDON_ENGINE_PORT` (port TCP négocié, écoute engine sur 127.0.0.1 uniquement)
et `ADDON_SESSION_TOKEN` (jeton éphémère partagé). Dans le contrat v1, ce jeton est le `session_id`
de chaque enveloppe, y compris hello ; ne jamais journaliser les enveloppes brutes. Aucun champ
d'authentification supplémentaire n'est ajouté au schéma gelé. L'engine doit contrôler ce jeton
avant d'accepter le flux ; ne pas employer un identifiant de session public comme jeton.

Procédures autorisées : `add_torus` (rayons et segments), `add_cube` (size),
`add_subdivision_modifier` (SUBSURF sur objet actif). Aucun Python fourni par le réseau n'est
évalué. Les commandes respectent deadline relatif, révision de scène et déduplication. Pour
`undo_demo`, le checkpoint est le command_id du dernier replay isolé ; une modification de scène,
un chargement ou une reconnexion invalide sa réutilisation. En background, undo_demo est refusé.
Menus autorisés : `VIEW3D_MT_mesh_add`, `VIEW3D_MT_add`. Les couleurs de highlight sont
`#RRGGBB` ou `#RRGGBBAA` ; les handles POST_PIXEL expirent et sont retirés au teardown.

### Vérification reproductible
Depuis le venv Python 3.11 du projet :

```sh
ruff check .
pytest -q
pytest -q tests/addon -m live -s
```

La suite live lance réellement `blender -b --factory-startup --python ...` et un serveur TCP
asyncio local. Elle crée un tore, un cube et un modificateur subdivision par bpy, puis répète
ces actions via commandes réseau. Elle vérifie schémas, scène vide, sélection/mode, déduplication,
révision périmée, expiration, paramètres invalides, contexte headless, reconnexion et teardown.
Elle imprime les latences mesurées action → delta et commande → résultat, sans jeton.
Mesure Linux / Blender 4.5.9 LTS de cette validation : 44 événements validés, 16 commandes ;
action → scene.changed : 16,60 / 29,18 / 37,75 / 54,41 / 63,54 ms (tore, cube, subdivision,
mode édition, mode objet). Commande → résultat : min 4,12 ms, moyenne 7,59 ms, max 16,82 ms.
Résultats : `ruff check .` propre, `pytest -q` : 118 passés ;
`pytest -q tests/addon -m blender -s` : 1 passé, 2 désélectionnés.
Le mode background n'entretient pas la boucle UI : le harness pompe explicitement le même callback
que le timer enregistré. Ce test ne mesure donc pas la cadence réelle de la boucle UI Blender.

### Limites explicites
Le headless ne fournit pas l'historique REGISTER des actions scriptées : le delta de scène fait
foi ; la provenance est inconnue si aucun opérateur n'a été observé. Les créations replay ont
une provenance enregistrée. Une provenance seule ne prouve pas la géométrie attendue.
Les régions sont vides en background ; menus et dessins sont refusés avec bad_context.
Le dessin, les menus, l'annulation interactive et la cadence des timers UI restent à valider
visuellement sur le Mac de démonstration. Aucun service cloud n'est appelé par ce client fin.
`monitor_id` identifie la fenêtre Blender, pas un écran physique : le desktop doit effectuer
la correspondance fenêtre/moniteur et la transformation DPI avant tout pointage multi-écran.
