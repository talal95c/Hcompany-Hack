# Tests et jalons M0–M6
Ce dépôt contient uniquement du design, pas de code ni résultats de benchmark. Les commandes d'implémentation et manifests seront ajoutés par les propriétaires ; ne pas confondre plan de tests et résultats.
| Jalon | Test manuel réel effectué par l'utilisateur | Tests automatisés attendus | Sortie exigée |
|---|---|---|---|
| M0 — contrats et machine cible | choisir Mac, Blender exact, nom de travail ; lire un exemple d'étape avec l'équipe | validation fixtures leçon/événements/ordres/WS, rejet major incompatible | gel v1 et affectation A/B/C |
| M1 — faisabilité native et cloud | voir pointeur, cliquer Blender au travers, survol pill ; refuser puis accorder permissions ; PTT et stop | transformations DPI, cache invalidé, Holo mock timeout, quota Jev et partiels périmés | capture excluant nos fenêtres, mesures Holo/Jev, TTS décidé ou texte assumé |
| M2 — preuve et capteur | faire ajouter tore puis cube, déplacer régions, ouvrir menu, observer debug | checks nominal/vide/erreur, scène inconnue, menus diff identiques/changés, export refusé si pending | donut prouvé version exacte, couverture operators documentée |
| M3 — direct et voix | réussir étape puis demander pourquoi, parler FR avec termes anglais, dire chut | machine états, déduplication, cancel spéculation, silence, Gladia offline | ✓ réel, question cache, aucune action sur partiel |
| M4 — aide et délégation | attendre 20 s, faire 3 undos, parcourir paliers puis fais-le et stop | horloge virtuelle cooldown 30 s, undo sûr, consentement absent, focus perdu, crash pendant touche | aide ordonnée, injection contrôlée, secours bpy annoncé |
| M5 — mémoire et Agent | défi sans aide puis déléguer, chercher/get/run une leçon par MCP | progression compétence, calendrier injectable, refus non-proven/version incompatible/busy | Skill versionnée et même check en mode agent |
| M6 — répétition générale | tuto inconnu court, réseau salle puis coupure, relance app et reprise | reconnect snapshot, pas de replay mutation, absence secrets logs, liens docs | rapport mesures vs cibles, limites affichées, vidéo secours étiquetée |
## Linux VM vs Mac
Linux : checks purs, contrats, policy à horloge simulée, engine avec faux clients, sandbox Blender Xvfb et préparation. Les tests d'intégration ne doivent appeler le cloud qu'avec activation explicite, budget borné et fixtures non sensibles. Cas nominal, état vide, malformé, timeout et déconnexion par composant.
Mac utilisateur : Tauri transparent, ScreenCaptureKit, permissions, enigo, Retina et multimoniteur, micro/hotkey hors focus. Tester chaque refus avant accord, redémarrage et révocation. Linux ne valide aucune de ces garanties natives. Windows nécessite ensuite sa propre recette.
## Page debug locale
Afficher session et step, génération, dernière révision scène/UI, événement entrant, check pass/fail/unknown, raison de policy, palier et cooldown, dernier progrès, services in-flight, cache hit/miss, quota restant estimé, latences et permission status. Boutons pause/reprise, snapshot et stop ; pas de bouton exécutant du Python libre. Traces exportables opt-in expurgées, sans clés, captures ou voix par défaut.
## Mesures reproductibles
Chaque résultat inclut date, matériel, OS/Blender, langue, échelle, réseau, taille capture, version modèle, nombre d'essais et échecs, p50/p95. Les cibles < 0,6 s correction, < 1 s pourquoi cache et ~2 min préparation sont (est.) et devront être confrontées aux résultats. Ne jamais effacer les échecs pour embellir la médiane.
