# engine/debug/

## Responsabilité
Observabilité locale.

## Entrées
traces expurgées.

## Sorties
chronologie checks/policy/services.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/engine.md) et [guide des agents](../../AGENTS.md).

## État et validation
`server.DebugServer` sert une page HTML autonome, `/ws` pour la chronologie et
`/metrics` pour p50/p95/max par service et étape de traitement. Anneau, abonnés et
échantillons bornés ; les captures, l'audio, les jetons et textes privés sont expurgés.
Le serveur est lié à ENGINE_HOST et refuse les origines étrangères.
Tests réseau : `pytest -q tests/engine/test_servers.py`.
