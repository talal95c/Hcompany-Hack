# ADR 0003 — Un cerveau, clients fins

Statut : accepté pour la conception ; implémentation et tests à venir.

## Contexte
Une logique répartie créerait des états contradictoires.

## Décision
Un Python asyncio engine ; add-on socket et desktop WebSocket ; préparation Linux Xvfb, direct sur Mac.

## Alternatives
Microservices ; logique pédagogique dans le front ou Blender.

## Conséquences
Contrats et annulation centralisés ; ne pas bloquer la boucle.

Référence : [architecture](../architecture/vue-ensemble.md).
