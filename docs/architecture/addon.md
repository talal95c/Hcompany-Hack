# Add-on Blender — capteur et actionneur borné
## Accès aux données
Blender ne fournit pas d'arbre d'accessibilité exploitable pour notre besoin. Le capteur utilise bpy : objets, maillages, matériaux, modificateurs, mode, sélection et géométrie des régions. Une identité d'objet stable dans la session évite les faux positifs dus aux renommages.
- bpy.msgbus : notifications des propriétés souscrites ; réabonnement après chargement.
- bpy.app.handlers.depsgraph_update_post : changements de scène, à agréger.
- bpy.context.window_manager.operators : observation des seuls opérateurs REGISTER. Ne pas assimiler cette liste à un historique complet ; vérifier l'état pour les autres actions.
- bpy.app.timers : vidange de la file réseau sur le thread principal. Aucun appel bpy depuis le thread socket.
## Transport et événements
Socket local bidirectionnel JSON délimité par retour ligne. Port négocié au lancement, pas de dépendance à un port public fixe. Handshake version, jeton de session, puis snapshot complet. Les événements sont décrits dans [le contrat](../contrats/evenements-addon.md).
Types poussés : hello, operator.executed, scene.changed, mode.changed, selection.changed, regions.changed, undo, snapshot, command.result, heartbeat. Agréger les changements fréquents ; ne jamais perdre un résultat de commande. Poll des opérateurs à 100 ms (est., cadence cible à mesurer), pas de cloud dans les callbacks.
## Commandes
highlight, open_menu, replay, undo_demo, request_snapshot, clear_highlight. Voir [ordres](../contrats/ordres.md). replay référence une procédure autorisée, jamais une chaîne Python arbitraire. Préconditions : objet actif, mode, éditeur, absence d'opérateur modal incompatible. Les effets sont confirmés par un nouvel état.
## Dessin et menus
Space.draw_handler_add avec région WINDOW / HEADER / UI / TOOLS selon besoin, mode POST_PIXEL ; enregistrer les handles par zone et les supprimer au teardown. Tous les types ne sont pas nécessairement supportés par chaque Space : tester HEADER sur la version de démo. tag_redraw pour rafraîchir ; pas de boucle graphique bloquante. wm.call_menu reçoit un identifiant validé de la carte versionnée et un temp_override window/area/region approprié.
## Limites et garde-fous
Une primitive « tore » ne se déduit pas du seul type MESH ni du nom Torus. Enregistrer la provenance de création quand disponible et vérifier la géométrie attendue ; sinon check unknown. Chargement de fichier : réinitialiser abonnements, régions et identités. Une démonstration annulée n'est sûre que depuis un checkpoint et sans intervention concurrente ; si la pile undo est ambiguë, utiliser la vidéo de preuve.
