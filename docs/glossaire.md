# Glossaire
| Terme | Définition |
|---|---|
| Leçon | suite d'étapes versionnées avec objectifs, checks, cibles et preuves |
| Étape | unité atomique de progression validée sur état réel |
| Check | fonction déterministe typée produisant pass/fail/unknown |
| Proven | toutes les étapes validées, preuves liées à la version exacte |
| Preuve de résultat | check réussi après exécution ; ne certifie pas nécessairement le chemin UI |
| Preuve UI | chemin réellement joué dans l'interface et documenté |
| Diff | comparaison versionnée des opérateurs, paramètres, préconditions et chemins |
| UI map | carte menus/libellés/opérateurs d'une version Blender |
| Target | description sémantique à localiser ; pas des pixels persistants |
| Arbre d'accessibilité | description privée de l'interface fournie par l'OS (AX, UI Automation, AT-SPI) : rôle, nom, valeur, états et rectangle |
| Ref | identifiant d'élément valable pour un seul snapshot d'accessibilité ; jamais stocké dans une leçon |
| Grounding | localisation d'une cible sur une capture fraîche |
| Région | sous-surface Blender WINDOW, HEADER, UI, etc. |
| PTT | push-to-talk, raccourci global de prise de parole |
| Pill | petite fenêtre d'état et commandes du desktop |
| Click-through | fenêtre qui laisse passer les clics vers l'application dessous |
| Sidecar | processus Python lancé et arrêté par Tauri |
| bpy | API Python de Blender, utilisée uniquement dans Blender |
| REGISTER | option d'opérateur requise pour sa présence dans window_manager.operators |
| Holo | modèle cloud H pour voir, localiser, agir et compiler |
| Jev | décision ambiguë rapide via Codiv |
| Gladia | transcription live/fichier, pas synthèse vocale |
| TTS | synthèse vocale, fournisseur encore ouvert |
| Skill | procédure prouvée exportée comme contexte agent |
| MCP | protocole d'outils find/get/run/report_broken côté agent |
| Snapshot | état complet cohérent utilisé après connexion ou perte d'événements |
| Génération | numéro invalidant les calculs async d'une ancienne étape |
| Révision scène/UI | version locale de l'état observé ou du layout |
| est. | estimation de conception, non mesure de notre système |
