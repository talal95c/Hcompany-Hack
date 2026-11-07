# engine/fallback/

## Responsabilité
Secours déterministes.

## Entrées
timeouts et état des services.

## Sorties
règles, clavier, texte ou pause.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/engine.md) et [guide des agents](../../AGENTS.md).

## État et validation
`with_fallback()` borne un appel et propage l'annulation. `Fallback.call()` ajoute
santé par service, backoff exponentiel borné et latence mesurée dans un callback
de debug, sans enregistrer arguments, exceptions fournisseur ou secrets.
L'appelant fournit une fabrique : aucun appel réseau n'est créé pendant le backoff.
Jev utilise une règle locale ; Holo reste au palier ②. `transcribe()` signale le
clavier si le final est vide, absent ou tardif ; `synthesize()` retourne `None`
pour garder le texte en absence d'audio. Le callback relaie erreurs et latences.
Tests : `pytest -q tests/engine/test_fallback.py`.
