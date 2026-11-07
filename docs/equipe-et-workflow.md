# Équipe et workflow
## Propriété
| Personne | Propriétaire | Interface à coordonner |
|---|---|---|
| A — préparation | prep/, lessons/, engine/checks/, agent/ | bibliothèque checks, carte UI et artefacts avec B |
| B — boucle pédagogique | engine/ hors services Holo/voix, addon/, contrats avec revue A/C | événements et commandes avec A/C |
| C — desktop et services visuels/voix | desktop/, engine/services/holo/ et intégrations Gladia/TTS, bench natif, pitch | IPC natif et réponses service avec B |
Les services restent dans un même processus même quand leur propriétaire diffère. Les clés Codiv et la politique Jev relèvent de B ; A et C relisent leurs frontières.
## Première heure : gel du contrat
1. Lire PRD, ADR et exemples ; choisir version Blender et Mac de démo.
2. Figer champs, enums, erreurs, repères, authentification locale et version v1 des quatre contrats.
3. Confirmer format audio, tailles maximales, ports négociés et variable Codiv. Toute valeur non décidée reste explicitement TBD.
4. Écrire fixtures nominales/vides/invalides et répartir les tâches verticales avec critères de recette.
5. Ne pas bloquer A/C sur l'implémentation de B : faux événements et faux services conformes aux mêmes fixtures.
## Branches et PR
Une branche courte par tâche, PR vers la base convenue par l'équipe, pas de push direct sur branche partagée sans coordination. Décrire contrat touché, tests réellement exécutés, dépendances et limites Mac/Linux. Tout changement incompatible exige revue des trois propriétaires et nouvelle version de contrat. PR petites, pas de refactor incident ; jamais de secret, capture privée ou artefact massif.
Pour cette livraison documentaire, la branche existante de conception est conservée.
## Choisir une tâche comme agent IA
Lire AGENTS puis le document du dossier ; prendre une tâche sans propriétaire actif, annoncer fichiers et contrat d'entrée/sortie ; choisir une tranche testable. D'abord fixture et check, puis code. Ne pas inventer les endpoints fournisseurs non validés. Si la tâche exige une décision produit, une clé absente ou une validation Mac indisponible, remonter le blocage plutôt que prétendre avoir terminé. Reporter résultats exacts et inconnues ; aucune tâche native n'est validée par un simple build Linux.
