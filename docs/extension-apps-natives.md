# Au-delà de Blender : Excel, Finder, apps métier

Statut : contrats v2 disponibles ; capteurs génériques et routeur à implémenter. [Spécification native](architecture/accessibilite-native.md) · [architecture multi-app](architecture/multi-app.md) · [ADR 0011](decisions/0011-multi-app.md).

## L'idée
Pour Blender, notre add-on lit l'état du logiciel. Pour les autres apps, l'OS expose souvent une description destinée aux lecteurs d'écran : l'arbre d'accessibilité. Notre desktop le lit via un trait Rust et des backends natifs. Un outil comme `agent-desktop` reste une option d'intégration, pas la brique imposée.

## Ce que l'arbre apporte
| Question du prof | Réponse possible |
|---|---|
| Où est le bouton ? | rôle, nom et rectangle, si la cible est unique |
| L'étape est-elle réussie ? | valeur ou état relu avec un check frais |
| « Fais-le » ? | action sémantique avec consentement, puis nouveau check |

L'arbre ne donne pas l'état métier complet de toutes les apps. Un canevas peut être invisible ; la vision Holo reste nécessaire. Une capture fraîche et une assertion visuelle autorisée peuvent servir de check, avec une confiance moindre. Sans check récent, pas de ✓.

## Comment ça s'emboîte
1. La leçon v2 indique déjà l'application, sa version et son capteur ; les cibles restent descriptives.
2. Desktop annonce l'app active ; engine choisit add-on, accessibilité ou vision.
3. Desktop lit seulement le sous-arbre utile ; engine vérifie valeur ou état après l'action.
4. Si la cible est ambiguë ou l'arbre incomplet, engine utilise la vision autorisée ou suspend la validation.

Les valeurs privées ne sont pas journalisées ni envoyées au cloud par défaut. Aucun champ de mot de passe n'est lu ou automatisé ; le secours Holo utilise seulement une capture minimale consentie.

## Ce qui reste à prouver
- Excel, Finder et Photoshop sur Mac : profondeur utile, valeurs, actions et zones absentes.
- Permissions AX dans l'application Tauri signée, refus puis accord ; backends Linux et Windows testés séparément.
- Latence, taux de réussite et fréquence des secours, à mesurer dans `bench/`.
- Tests de reconnexion, refs périmées et arrêt prioritaire avant une démo réelle.

La suite : implémenter le trait, tester les backends et le routeur, puis prouver une leçon par application/version. Le contrat disponible ne signifie pas une fonctionnalité déjà livrée.
