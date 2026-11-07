# Préparation et preuve par différence
## Pipeline
1. ingest : fichier vidéo, URL autorisée ou documentation → texte horodaté, langue, source et empreinte. Gladia fichier pour la vidéo, pas de modèle local.
2. compile : Holo LLM transforme le texte en étapes atomiques, choisit un check existant paramétré, préconditions, cible descriptive, pourquoi, erreurs connues. Validation du contrat avant exécution. Préparer audio lorsque le TTS sera choisi.
3. ui_map : charger cartes source et cible exactes ; menu → libellé, opérateur, paramètres, identifiant wm.call_menu. Usages : description Holo, ouverture de menu, comparaison des versions.
4. diff : comparer signature opérateur, paramètres, préconditions, chemin UI et check. L'existence d'un opérateur seule ne suffit pas à déclarer l'étape inchangée.
5. prove : exécuter en sandbox isolée, vérifier l'état puis conserver preuves et limites.
6. export : publier uniquement une révision intégralement prouvée, avec empreintes et version exacte.
## Algorithme de preuve
```
pour chaque étape dans l'ordre :
  si check absent : HANDOFF vers Devin, statut pending, ne pas publier
  si contexte, carte ou signature inconnus : traiter comme changé
  si signature et chemin inchangés :
    charger checkpoint ; exécuter procédure bpy autorisée ; évaluer check
  sinon :
    Holo voit et agit dans le Blender sandbox ; évaluer check séparément
  si échec : Linkup cherche documentation éditeur, compiler candidat et retester
  si succès : enregistrer état avant/après, chemin, check, version et preuve
  sinon : failed/pending ; interdire export
```
Le diff évite le computer use inutile, pas la validation. Une preuve bpy atteste le résultat et marque ui_path_verified=false ; ne jamais la présenter comme une preuve visuelle du chemin. Réutilisation de preuve seulement si empreintes version, check, paramètres et fixture coïncident.
## Sandbox
Linux cloud avec Blender graphique sous Xvfb, répertoire de travail isolé, versions installées explicitement, pas de secrets dans les fichiers .blend. Limiter réseau et commandes, checkpoint par étape, timeout et nettoyage des processus. La version doit correspondre à celle de l'utilisateur ; un résultat Linux ne prouve pas à lui seul raccourcis et menus macOS. Recette Mac finale requise. La preuve visuelle et la vérification bpy sont séparées pour éviter qu'un agent ne falsifie son propre succès.
## Planificateur
| Mode | Entrée / condition | Action | Transition |
|---|---|---|---|
| EXECUTE | étape nouvelle | tenter chemin prévu | succès → CONSOLIDATE ; divergence → EXPLORE |
| REPLAY | preuve compatible | rejouer chemin mémorisé | succès → CONSOLIDATE ; échec → EXPLORE |
| EXPLORE | interface différente | Holo explore borné | succès → CONSOLIDATE ; bloqué → OBSERVE |
| OBSERVE | information manquante | Linkup lit doc éditeur | candidat → EXECUTE ; pas de check → HANDOFF |
| CONSOLIDATE | check réussi | enregistrer preuves et mémoire | étape suivante → REPLAY ou EXECUTE |
| HANDOFF | check absent ou réparation non sûre | Devin prépare PR asynchrone | revue et tests → EXECUTE ; sinon pending |
## Budget
Tuto déjà connu < 1 min (est.), nouveau court ~2 min (est.). Décomposition cible : ingest 10–30 s (est.), compile 5–20 s (est.), diff < 1 s (est.), preuves 10–60 s (est.), export 1–5 s (est.). Ces postes ne garantissent pas le total ; durée vidéo, upload et nombre d'étapes dominent. Devin et revue exclus du budget et du direct.
