# data/ — sources pour le graphe relationnel

État : **inventaire et organisation**. Aucun graphe n'est encore construit et aucune donnée lourde
n'est versionnée. Ce dossier dit *quelles* données nourriront le graphe, *pourquoi*, et *comment*
les récupérer de façon reproductible.

## Pourquoi un graphe

Aujourd'hui, la connaissance est dispersée :
- `prep/ui_map` : menus et opérateurs par version de Blender ;
- `lessons/*/proof` : étapes, opérateurs et checks prouvés ;
- `engine/cache` : cibles localisées par Holo, mais en mémoire seulement (LRU, perdu à la fermeture) ;
- `engine/learner` : maîtrise des compétences, par utilisateur ;
- `agent/triage` et `report_broken` : leçons cassées.

Un graphe relie tout ça : **app → version → zone → élément → action → état vérifiable → étape →
compétence**. Deux bénéfices attendus (hypothèses, à mesurer dans `bench/`) :
1. **Plus précis tout de suite.** Si le graphe connaît le `menu_id` d'un élément, on l'ouvre avec
   `wm.call_menu` sans Holo. S'il connaît la zone, on recadre la capture sur cette zone.
2. **Plus précis avec le temps.** Chaque étape réussie et vérifiée ajoute ou renforce un lien.

Modèle proposé : [graphe/modele.md](graphe/modele.md).

## Organisation

```
data/
├── README.md            ce fichier
├── sources.json         manifeste : URL, révision figée, licence, volumes, rôle dans le graphe
├── graphe/modele.md     nœuds, liens, et quelle source remplit quoi
├── mesures/             résultats déjà mesurés qui orientent le graphe
└── raw/                 téléchargements locaux (ignoré par git)
```

Règle : seuls les manifestes, les modèles et les petits résultats sont versionnés. Les images et
jsonl externes vont dans `data/raw/<id>/` à la révision indiquée dans `sources.json`.

## Les sources, par priorité

### 1. Internes : la vérité terrain (priorité haute)
| Source | Où | Ce qu'elle donne au graphe | Fiabilité |
|---|---|---|---|
| Carte UI | `prep/ui_map`, cache `~/.cache/hcompany-prep/ui_maps/<version>.json` | menus → entrées → opérateurs, libellés, diff entre versions | exacte (extraite de Blender) |
| Preuves de leçons | `lessons/*/proof/*.json` | étape → opérateur et propriétés → checks, état avant/après | exacte, rejouée |
| Leçons | `lessons/*/lesson.json` | étape → compétence, consigne, préconditions | relue |
| Événements add-on | flux `addon` (opérateurs, mode, sélection, rectangles des zones) | enrichissement en continu : quelle cible et quelle action ont marché | exacte, si le check passe |
| Cibles Holo | `engine/cache` (`TargetCache`) | description → position observée, avec le contexte | observation, à confirmer par un check |

C'est la seule source qui sait *ce qui marche chez nous*. Les données publiques servent à pré-remplir
et à mesurer.

### 2. Publiques : pré-remplir les éléments d'interface (priorité moyenne)
| Source | Volume utile (compté le 2026-11-07) | Apport |
|---|---|---|
| **GroundCUA** | Blender 399 captures annotées (181 éléments sur la capture examinée, avec nom et type : Button, Menu…) ; LibreOffice Calc 757 ; Gnumeric 691 ; OnlyOffice Spreadsheet 689 ; Metabase 352 ; GnuCash 659 ; Frappe Books 1000 | nœuds « élément » avec nom, type et voisins spatiaux ; le meilleur pour pré-remplir |
| **ScreenSpot-Pro** | Blender 71 (Windows) ; Excel 64 (macOS Retina) ; Word 84 (macOS) ; PowerPoint 82 et Photoshop 51 (Windows) | liens « intention en phrase → élément » ; sert surtout de jeu de test |

### 3. Publiques : procédures vérifiées hors Blender (priorité moyenne, pour Excel et les données)
| Source | Volume | Apport |
|---|---|---|
| **Spider2-V** | 495 tâches : tableur 62, BigQuery 40, dbt 40, Snowflake 44, Metabase 48, Superset 33, Airbyte 48, Airflow 38, Dagster 40, Jupyter 44, ServiceNow 58 | tâche → tutoriel pas à pas (`verbose_instruction.txt`) → fichier attendu → script de vérification ; même structure que nos leçons |
| **OSWorld** | LibreOffice Calc 47, Writer 23, multi-apps 102 | tâche → vérification automatique |
| **Windows Agent Arena** | LibreOffice Calc 24 (sous Windows) | idem, sous Windows |

Attention : les tâches « excel » de Spider2-V tournent sur **LibreOffice Calc** avec des `.xlsx`,
pas sur Microsoft Excel. Le seul vrai Excel sur Mac recensé ici, ce sont les 64 cibles de ScreenSpot-Pro.

### 4. Plus tard (priorité basse)
| Source | Pourquoi plus tard |
|---|---|
| AgentNet / OpenCUA | 23K trajectoires (≈ 1,7 Go de jsonl) : enchaînements d'actions réels, mais conçus pour l'entraînement |
| RealCUA | arbres d'accessibilité et événements réels sur macOS, idéal pour un graphe, mais accès sur demande (https://info.fig.inc/data) |
| VideoGUI, BlenderGym | idées de méthode ; pas de licence déclarée sur GitHub, donc on ne réutilise pas leurs données |

## Règles d'enrichissement

1. Un lien n'est ajouté que si le check de l'étape **passe**. `unknown` n'est pas `pass`.
2. Un échec baisse la confiance d'un lien, il n'en crée pas.
3. Une position à l'écran est une **observation** (version, résolution, disposition, date), jamais
   une vérité ; on stocke la description de la cible ([ADR 0010](../docs/decisions/0010-cibles-descriptives.md)).
4. Chaque nœud et chaque lien gardent leur **provenance** (`source`, `revision`) ; on ne mélange
   pas une annotation publique et une preuve interne.
5. Local par défaut : rien de l'utilisateur (scène, valeurs, captures) ne quitte la machine sans
   consentement. Le partage entre utilisateurs est une décision à prendre plus tard.

## Récupérer une source

Les révisions figées sont dans `sources.json`. Exemples :

```bash
# Hugging Face (annotations seulement ; ajouter les images si besoin)
huggingface-cli download likaixin/ScreenSpot-Pro --repo-type dataset \
  --revision 210e78d3844251110bff86c95835ebd37a6930fa \
  --include "annotations/*" --local-dir data/raw/screenspot-pro
huggingface-cli download ServiceNow/GroundCUA --repo-type dataset \
  --revision 5d6845b0116029d46ec762e734701c5b8ce207c3 \
  --include "data/Blender/*" --local-dir data/raw/groundcua

# GitHub (dossier de tâches uniquement)
git clone --filter=blob:none --sparse https://github.com/xlang-ai/Spider2-V data/raw/spider2-v
git -C data/raw/spider2-v checkout c2a3a6c2f5d7604464f162c6550b60db3eee04e8
git -C data/raw/spider2-v sparse-checkout set evaluation_examples/examples/excel
```

## Mesures déjà faites

[mesures/holo-grounding-blender.md](mesures/holo-grounding-blender.md) : Holo sur 131 cibles Blender
publiques. C'est ce qui justifie le graphe : environ 1 petite cible sur 4 est ratée en vision seule.

## Ce qui reste ouvert
- Choisir le stockage du graphe (JSON versionné, SQLite, ou base de graphe) : pas décidé.
- Mesurer le gain réel (graphe + recadrage sur zone contre Holo seul) dans `bench/`.
- Le contrat de leçon est propre à Blender (`blender_version`) ; un graphe multi-app demandera
  `app` et `app_version` (voir la PR accessibilité native).
