# Face Agent : même preuve, deux usages
## Artefacts
Une révision H Skill par version de Blender et révision de leçon. Contenu : objectif, préconditions, étapes, checks, cibles descriptives, limites de preuve, contexte d'exécution et empreinte. Identifiant distant et API de publication à valider avec les crédits H ; ne pas supposer une API Skills identique à Models API.
Le MCP dans agent/ expose seulement les révisions proven. Il ne recalcule pas une preuve et ne masque jamais un échec.
| Outil | Entrée | Sortie / garde-fou |
|---|---|---|
| find | query, blender_version, skill_id optionnel | liste compatible, statut et résumé, aucun secret |
| get | lesson_id, revision, blender_version | leçon immuable + preuves ; erreur si non prouvée |
| run | lesson_id, revision, session_id, consent_token | run_id et progression ; bureau verrouillé, consentement requis |
| report_broken | revision, step_id, description, evidence_ref | ticket_id ; met en quarantaine après triage, pas de réparation automatique publiée |
## Exécution
run utilise engine et la même politique de sécurité que « fais-le ». La Skill apporte du contexte à Holo, pas des coordonnées absolues. Fin = checks réussis ; une déclaration visuelle du modèle n'est pas un succès suffisant. Concurrence : un run propriétaire du bureau ; les autres reçoivent busy.
## Entreprise
Même procédure pour onboarding humain et automatisation agent ; traçabilité par version et PR de réparation, validation avant promotion. À prévoir hors hackathon : authentification, rôles, isolation des organisations, conservation des preuves, consentement captures et révocation. Aucun argument commercial ne doit promettre ces fonctions avant implémentation. La rétention cloud dépend des contrats fournisseurs : pas de promesse « rien stocké » sans vérification.
