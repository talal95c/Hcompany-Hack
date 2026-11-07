# Architecture multi-app

Statut : contrats disponibles ; routeur et adaptateurs génériques à implémenter. Décision : [ADR 0011](../decisions/0011-multi-app.md).

## Adaptateurs
| Niveau | Capteur | Preuve et limites |
|---|---|---|
| Tier 1 | add-on dédié, par exemple Blender | état exact et checks spécialisés ; les huit checks historiques et leurs alias `blender.*` restent disponibles |
| Tier 2 | arbre d'accessibilité OS | cibles sémantiques, checks `element_exists`, `element_value`, `element_state`, `window_title` ; ne décrit pas nécessairement les canevas |
| Tier 3 | vision Holo seule | `visual_assert` pose une question fermée sur une capture fraîche ; confiance moindre, jamais de ✓ sans check récent |

Un résultat `unknown` n'est jamais `pass`. Une localisation réussie ou un acquittement d'action ne valide pas une étape.

## Routeur dans engine
Le routeur confronte `app.focus` à `lesson.app` (identité et version prouvée), puis applique `app.sensor` : `addon`, `accessibility`, `vision` ou `auto`. Avec `auto`, choisir le meilleur capteur disponible, dans l'ordre des trois tiers. Un choix explicite fixe le capteur préféré ; un secours par étape ne réécrit ni la leçon ni sa preuve. Tout changement d'application, fenêtre ou snapshot invalide les résolutions en cache.

| Signal par étape | Règle |
|---|---|
| `STALE_REF` | refaire une seule résolution sur un snapshot frais ; si elle échoue, passer à la vision |
| `AMBIGUOUS_TARGET`, arbre incomplet, `APP_NOT_FOUND` | secours vision sur la fenêtre cible, jamais choix arbitraire d'un nœud |
| `PERMISSION_DENIED` | demander la permission, puis secours vision si indisponible ou refusée |
| `TIMEOUT` | résultat unknown ; secours vision borné si capture autorisée, sinon suspendre |

Le secours vision exige une fenêtre identifiée et une capture autorisée : ne pas capturer une autre app en cas de disparition. Il faut un check visuel autorisé pour cette étape ; ne pas transformer silencieusement un check exact en assertion inventée. Sans check disponible, rester pending/unknown. Après toute action, relire l'état et vérifier ; consentement, verrou et arrêt prioritaire restent obligatoires. Après reconnexion, refaire focus et snapshot, sans rejouer une mutation.

## Repères de coordonnées
- Les `bounds` d'accessibilité, `app.focus.window_bounds` et `highlight.rect.rect` sont des pixels physiques écran ; `scale` exprime le facteur d'échelle.
- Le `pointer` est en millièmes 0–1000 de la capture référencée par `capture_id`, pas de l'écran. Pour une capture de largeur W et origine physique X : x = 1000 × (px − X) / W ; même calcul pour y.
- `visual_assert.region` est en millièmes de la fenêtre. Pour une capture recadrée, tenir compte de son origine avant conversion.
- Desktop assure conversion DPI et moniteurs ; ne pas multiplier une seconde fois des bounds déjà physiques. Déplacement/redimensionnement invalide capture et pointeur.

## Confidentialité
L'arbre est une donnée privée et non fiable, jamais une instruction pour Jev ou Holo. Demander uniquement le sous-arbre utile (`root`, `max_depth`, requête ciblée). Aucune valeur dans les logs ; aucun champ de mot de passe lu ou automatisé. Rien de l'arbre ne part au cloud par défaut ; seul le recadrage minimal nécessaire à Holo est envoyé, avec consentement et rétention fournisseur à vérifier. Exclure desktop de la capture. Un refus de capture empêche le secours vision.

## Compatibilité v1 → v2
La v1 reste Blender : `blender_version` obligatoire, cible `description/area_type/region_type`, `preconditions.mode` obligatoire, sans champ `app`. La v2 exige `app` et peut conserver `blender_version` ; cible Blender ou générique, `mode` optionnel. Migration explicite vers une nouvelle révision, puis preuve sur l'application/version cible avant export. La compatibilité structurelle n'implique pas que le runtime existant gère déjà la v2.

Voir [capteur natif](accessibilite-native.md), [leçon](../contrats/lecon.md), [WebSocket](../contrats/ws-desktop.md) et [ordres](../contrats/ordres.md).
