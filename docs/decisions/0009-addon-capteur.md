# ADR 0009 — Blender observé par add-on

Statut : accepté pour la conception ; implémentation et tests à venir.

## Contexte
Pas d'arbre d'accessibilité Blender adapté au besoin.

## Décision
bpy comme capteur, msgbus/depsgraph et REGISTER operators ; checks sur état.

## Alternatives
OCR comme source de vérité ; supposer tous les opérateurs observables.

## Conséquences
Tests de couverture sur actions réelles ; unknown si information absente.

Référence : [architecture](../architecture/vue-ensemble.md).
