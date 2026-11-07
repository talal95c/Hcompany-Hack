# ADR 0010 — Décrire les cibles, pas stocker les pixels

Statut : accepté pour la conception ; implémentation et tests à venir.

## Contexte
Les coordonnées changent selon version, menus et DPI.

## Décision
Leçon contient description et région ; Holo calcule les coordonnées sur capture fraîche, cache invalidable.

## Alternatives
Coordonnées fixes dans lesson.json.

## Conséquences
Portabilité et audit ; calcul Retina obligatoire dans desktop.

Référence : [architecture](../architecture/vue-ensemble.md).
