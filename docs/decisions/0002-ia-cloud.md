# ADR 0002 — IA exclusivement cloud

Statut : accepté pour la conception ; implémentation et tests à venir.

## Contexte
La machine utilisateur ne doit pas héberger de modèles.

## Décision
Holo pour localisation, computer use et LLM ; Jev via Codiv pour ambiguïté ; Gladia STT ; Linkup recherche ; Devin réparation async ; TTS ouvert.

## Alternatives
Modèles locaux ; multiplier les LLM de compilation.

## Conséquences
Réseau nécessaire ; clés hors clients fins, mode texte et checks locaux en secours.

Référence : [architecture](../architecture/vue-ensemble.md).
