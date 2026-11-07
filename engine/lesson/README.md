# engine/lesson/

## Responsabilité
Machine de progression.

## Entrées
leçon et checks.

## Sorties
étape/génération courante.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/engine.md) et [guide des agents](../../AGENTS.md).

## État et validation
Chargement strict des leçons prouvées, table des transitions, garde de précondition de mode,
génération et avancement dédupliqué disponibles. `runtime.EngineRuntime` relie
transports, checks, politique, mémoire, caches et debug, avec timer de progression.

`python -m engine` démarre les trois serveurs et émet uniquement la ligne de
disponibilité sur stdout. SIGINT, SIGTERM ou `shutdown` sur stdin ferment la session.
Les services sont injectables ; une fabrique optionnelle `engine.services.build_clients`
peut fournir les clients. Aucun service cloud n'est requis pour les checks locaux.

Consentement : un bouton transmet l'intention JSON `fais-le` et un UUID. Validité
60 s selon l'horloge ; les jetons déjà vus ne peuvent pas renouveler leur durée.
Pour une compétence non désirée, l'intention inclut `delegation_confirmed: true`
et `wants_to_learn: false`. Sinon la compétence doit être débloquée. L'API
`input_action()` exige permissions, consentement et capture unique non consommée.
Elle attend l'acquittement puis demande un snapshot ; elle ne génère pas d'action
arbitraire. Un pilote de services peut appeler cette API pour chaque action.
Les identifiants de captures et consentements ne sont jamais réutilisés ; après
4096 identifiants par catégorie, une nouvelle session est nécessaire (borne mémoire).

Les captures sont des PNG inline bornés, crop en pixels physiques avec échelle et
moniteur. Le contrat ne comporte ni commande de demande de capture ni carte de menus :
le desktop fournit les captures ; le contexte de menu/checkpoint sûr doit être injecté
par le pilote via `help_context`. Un replay sûr attend son acquittement avant undo.
Tests : `pytest -q tests/engine/test_foundation.py`.
