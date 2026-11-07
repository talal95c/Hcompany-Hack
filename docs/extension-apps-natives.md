# Au-delà de Blender : Excel, Finder, apps métier (explication)

_7 nov. 2026. Proposition, rien n'est implémenté. Spécification : [accessibilité native](architecture/accessibilite-native.md) ; décision : [ADR 0011](decisions/0011-accessibilite-native.md)._

## L'idée en une phrase
Pour Blender, notre add-on lit l'intérieur du logiciel. Pour les autres apps, on n'a pas besoin d'écrire un add-on par logiciel : l'OS fournit déjà une description de l'interface (l'arbre d'accessibilité, celui qu'utilisent les lecteurs d'écran pour les personnes aveugles). On le lit avec un outil open source, agent-desktop.

## Ce qu'on a aujourd'hui
| Question du prof | Blender | Autre app |
|---|---|---|
| Où est le bouton ? | l'add-on ouvre le bon menu, puis Holo pointe sur la zone capturée ; s'il ne voit pas la cible, il ne devine pas et on propose F3 | Holo sur la fenêtre entière, et seulement sous Linux ; sur Mac et Windows, échec explicite |
| L'étape est-elle réussie ? | check sur l'état réel (bpy) | **rien de fiable** |
| « Fais-le » | Holo clique en pixels, puis check | Holo clique en pixels, sans check |

Le trou, c'est la vérification. Sans check, pas de ✓, donc pas de leçon prouvée.

## Ce que donne l'arbre d'accessibilité
Pour chaque élément visible : son rôle (bouton, champ, cellule…), son nom (« Gras », « Enregistrer »), sa valeur, son état (activé, coché) et son rectangle à l'écran. Exemple réel lu sur une petite fenêtre de test Linux :

```json
{"role":"dialog","name":"ControlApp","children":[
  {"role":"textfield","states":["focused"],"ref_id":"@smrg81dw05npw:e1"},
  {"role":"button","name":"Cancel","ref_id":"@smrg81dw05npw:e2"},
  {"role":"button","name":"OK","ref_id":"@smrg81dw05npw:e3"}]}
```

Ça sert aux trois questions :
- **Où ?** le rectangle exact, sans appel Holo, donc sans latence modèle ni marge d'erreur.
- **Réussi ?** lire la valeur de la cellule ou l'état du bouton : c'est un vrai check, comme bpy pour Blender.
- **Fais-le ?** « appuie sur OK » par sa référence, pas « clique au pixel (812, 430) » : insensible au DPI, au thème et à la taille de fenêtre.

## Pourquoi agent-desktop
| Critère | Ce qu'on a vérifié |
|---|---|
| Trois OS | macOS (AX), Windows (UI Automation), Linux (AT-SPI), une seule CLI |
| Intégration simple | binaire Rust, sortie JSON stable (enveloppe versionnée) ; desktop est déjà en Rust |
| Pas de modèle caché | il observe et agit, nos règles décident ; Holo reste notre modèle |
| Sûr par défaut | actions sémantiques ; souris et clavier physiques seulement avec `--headed` |
| Face Agent | serveur MCP intégré (`agent-desktop mcp`), même logique que notre `agent/` |
| Licence et activité | Apache-2.0, ~18,5 k étoiles, mis à jour le 7 nov. 2026 |

Alternatives écartées : tout en vision (pas de check), écrire nos propres liaisons pour trois OS (trop long), ou laisser engine appeler l'outil (nos règles réservent les accès natifs à desktop).

## Comment ça s'emboîte
Le code a déjà la bonne prise : pour Blender, un « adaptateur » (`AddonTargetAdapter`) ouvre le menu et donne la zone à capturer, et le reste du moteur ne connaît pas Blender. On ajoute un deuxième adaptateur, branché sur l'arbre d'accessibilité.
1. Une leçon pour une app native décrit ses cibles par rôle et nom (« bouton Gras du ruban »), jamais par position : même règle que pour Blender.
2. En direct, desktop lit l'arbre de l'app ; l'adaptateur trouve la cible, ouvre son menu si besoin et donne son rectangle ; l'overlay pointe.
3. L'utilisateur agit ; desktop relit l'arbre ; engine lance le check (« la cellule B2 vaut 42 ») et affiche ✓.
4. Si l'arbre est vide ou ambigu, on retombe sur Holo avec ses garde-fous actuels.

Blender ne change pas : il n'expose pas son interface à l'OS (testé), l'add-on reste la référence.

## Ce qui reste à prouver
- Excel : on s'attend à un arbre riche (Office vise les lecteurs d'écran), **non testé**.
- Photoshop : menus et panneaux probablement visibles, canevas non ; **non testé**.
- Permission Accessibilité macOS pour un sidecar lancé par notre app : à vérifier sur Mac.
- Tests faits : fenêtre GTK lue correctement sous Linux ; Blender invisible pour l'outil.

## Calendrier proposé
| Étape | Contenu | Quand |
|---|---|---|
| 0 | slide « vision » pour le jury, rien dans la démo | hackathon |
| 1 | essai sur Mac : Excel, Finder, Photoshop ; mesures dans `bench/` | après démo |
| 2 | sidecar dans desktop, messages WebSocket `a11y.*`, `A11yTargetAdapter` | si l'étape 1 est concluante |
| 3 | checks `element_*`, leçon multi-app, `list_apps` multi-app | ensuite |
