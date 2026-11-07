# ADR 0005 — Préparer ce qui est prévisible

Statut : accepté pour la conception ; implémentation et tests à venir.

## Contexte
La lenteur cloud ne doit pas interrompre l'apprentissage.

## Décision
Code pour le certain, Jev pour l'ambigu, Holo pour voir/agir ; N+1 pré-localisé ; cache version×taille région×échelle UI×cible ; pourquoi/audio compilés ; Jev persistant et spéculatif ; preuve par diff.

## Alternatives
Holo à chaque événement ; tout rejouer visuellement.

## Conséquences
Invalidation stricte des caches, contrôle des partiels et des quotas.

Référence : [architecture](../architecture/vue-ensemble.md).
