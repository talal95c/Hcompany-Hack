# Zones d'ombre et registre des risques
Les propriétaires A/B/C sont définis dans [équipe](equipe-et-workflow.md). Rien ci-dessous n'est déjà validé par ce dépôt.
| Inconnue / risque | Comment résoudre, preuve attendue | Propriétaire | Jalon |
|---|---|---|---|
| Latence Holo sur crop Retina depuis la salle | bench captures réelles, p50/p95, précision et tokens ; pré-localisation puis zone si trop lent | C | M1 puis M6 |
| Modèle Holo exact et crédits Pro | requête localisation + compilation réelles, relever identifiant et quota sans clé | C | M1 |
| Couverture operators donut | chaque action réelle, comparer REGISTER et snapshot/depsgraph, lister angles morts | B | M1 |
| Check primitive torus robuste | provenance et géométrie sur plusieurs paramètres, cube et renommage comme négatifs | A | M2 |
| Jev sur 20 phrases réelles | jeu annoté dont chut, fais-le, pourquoi, ambigu ; matrice confusion, pas seulement moyenne | B | M1 |
| Nom de variable Codiv et quota partagé | confirmer SDK/API et secret canonique, vérifier 60 req/min avec spéculation bornée | B | M0/M1 |
| Exclusion ScreenCaptureKit depuis Tauri | capture test macOS 15+ sans nos deux fenêtres malgré présence écran | C | M1 |
| Pill click-through au survol | prouver suivi curseur natif + activation avant entrée WebView ; absence d'interception Blender hors pill | C | M1 |
| enigo et Accessibilité | refus puis accord, input de test Blender et stop ; touches relâchées après crash | C | M1 |
| Micro WKWebView ou natif | tester demande permission, audio et PTT hors focus ; choisir backend | C | M1 |
| draw_handler HEADER/UI | tracer dans régions réelles de la version cible, suppression handles et changement d'espace | B | M2 |
| Fournisseur TTS | comparer français, streaming, latence, prix, droits et cache ; décision ADR avant promesse voix | C | M1 |
| Modèle Mac démo et version Blender | relever matériel, OS, version exacte, langue UI, échelle, moniteurs ; geler fixture | C | M0 |
| Gladia FR/EN code switching | phrases françaises avec termes Blender anglais, partiels et finaux comparés | C | M3 |
| Sandbox identique utilisateur | installer version exacte, refuser export incompatible, recette différences Mac/Linux | A | M2 |
| Cartes menus complètes et contextuelles | exporter carte de version cible, tester menus dynamiques et contextes | A | M2 |
| Preuve bpy vs chemin UI | afficher ui_path_verified et retester chemins modifiés, ne pas surpromettre | A | M2 |
| API Skills et MCP H | valider authentification, publication, révision, consentement run ; pas d'API supposée | A | M5 |
| Tarifs Linkup, Devin, TTS et Jev | relever offres effectives avant chiffrage global ; factures/tokens sans secrets | A/C | M1 |
| Rétention cloud et données utilisateur | lire politiques et options des fournisseurs, consentement et purge | B | M6 |
| Undo démo sûr | vérifier checkpoint et concurrence ; sinon vidéo uniquement | B | M4 |
| Windows capture et DPI | tests natifs Graphics Capture, exclusions et moniteurs ; hors packaging démo | C | après M6 |
| Nom du produit | choisir nom public, vérifier disponibilité ; Hcompany-Hack reste nom de travail | A/B/C | M0 |
| Répétition espacée | calibrer intervalles sur usages, mesurer réussite sans aide ; pas d'algorithme déclaré optimal | B | M5 |
| Distribution macOSPrivateApi | vérifier signature/notarisation et canal de distribution accepté | C | M6 |
| Budget préparation | mesurer upload, compilation, preuves, cache ; durée vidéo variable | A | M2/M6 |
## Règle d'escalade
Points multi-app à lever avec C après M6 : couverture de l'arbre Excel / Finder / Photoshop sur Mac (valeurs, actions, canevas absents), permissions AX de l'application Tauri signée (refus puis accord), et permissions d'un backend optionnel en sidecar si retenu. Mesures dans bench ; voir [accessibilité native](architecture/accessibilite-native.md) et [ADR 0011](decisions/0011-multi-app.md).

Une inconnue bloquant une garantie laisse la fonctionnalité pending ou dégradée, pas « terminée ». Résolution : ajouter résultat reproductible dans bench, mettre à jour ADR et critère de recette, puis clore le risque.
