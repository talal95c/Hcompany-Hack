# Benchmark holo

Mesuré le 2026-11-07T13:49:08.268194+00:00

| Mesure | Valeur |
|---|---|
| api_calls | 193 |
| prompt_tokens | 717040 |
| output_tokens | 2622 |
| cached_tokens | 76832 |
| cache_observed | true |
| cost_usd_computed | 0.19961135999999993 |
| http_errors | 0 |
| http_429 | 0 |
| rate_limit_429_count | 1 |
| pacing_wait_ms | 348310.4495899983 |
| cooldown_wait_ms | 15075.12348499995 |
| hit_rate_http_200 | 0.7083333333333334 |

Mesures réelles ; coût calculé depuis les tokens aux tarifs imposés $0.30/M entrée, $0.03/M cache, $2/M sortie, pas une facture. Le catalogue annonce un tarif plus élevé pour 27B.
Passage uncached : nonce unique au tout début du système ; passage cached : corps identique répété immédiatement, seul le pacing partagé peut attendre. Les cached_tokens vérifient le cache effectivement servi.
Latence = tentative réussie seule. Token bucket partagé capacité 1, intervalle initial 2 s, concurrence 1 ; Retry-After et resets respectés. Les 429 augmentent l'intervalle et déclenchent un backoff 15/30/60 s (jusqu'à 20 tentatives). Les en-têtes rate-limit reçus sont conservés par tentative ; aucun plafond fournisseur n'est inventé si ces en-têtes sont absents.
12 régions distinctes × 2 échelles × full/crop × 2 passages par modèle. Hit : point à l'intérieur du rectangle RNA (bord droit/bas exclus). Les régions superposées du viewport se chevauchent selon Blender.
Sources : https://hub.hcompany.ai/models-api/element-localization et https://hub.hcompany.ai/models-api/chat-completions. temperature=0, thinking off, structured_outputs JSON normalisé [0,1000].
## Résultats Holo

| Modèle / échelle / image | Hits | HTTP erreurs | p50 ms | p95 ms | Moy. entrée / sortie | Coût USD |
|---|---:|---:|---:|---:|---:|---:|
| holo4-27b / 1x / crop | 83.3% | 0 | 263.0 | 431.4 | 987 / 14 | 0.00712 |
| holo4-27b / 1x / full | 83.3% | 0 | 392.0 | 665.4 | 2262 / 14 | 0.01586 |
| holo4-27b / 2x / crop | 83.3% | 0 | 272.5 | 1287.9 | 3308 / 14 | 0.02145 |
| holo4-27b / 2x / full | 83.3% | 0 | 1206.4 | 1685.1 | 8382 / 14 | 0.05129 |
| holo4-35b-a3b / 1x / crop | 58.3% | 0 | 254.1 | 399.2 | 986 / 14 | 0.00747 |
| holo4-35b-a3b / 1x / full | 58.3% | 0 | 338.4 | 430.6 | 2263 / 14 | 0.01695 |
| holo4-35b-a3b / 2x / crop | 50.0% | 0 | 330.9 | 713.7 | 3306 / 14 | 0.02246 |
| holo4-35b-a3b / 2x / full | 66.7% | 0 | 591.7 | 1097.3 | 8382 / 14 | 0.05702 |

## Cache contrôlé : nonce unique puis répétition identique

| Modèle / échelle / image | Passage | p50 ms | p95 ms | Tokens entrée | Tokens cachés |
|---|---|---:|---:|---:|---:|
| holo4-27b / 1x / crop | uncached | 217.5 | 437.7 | 11847 | 0 |
| holo4-27b / 1x / crop | cached | 287.8 | 431.4 | 11847 | 2400 |
| holo4-27b / 1x / full | uncached | 392.3 | 477.6 | 27149 | 0 |
| holo4-27b / 1x / full | cached | 390.1 | 1668.5 | 27149 | 4000 |
| holo4-27b / 2x / crop | uncached | 261.5 | 1309.9 | 39690 | 0 |
| holo4-27b / 2x / crop | cached | 272.5 | 1216.2 | 39690 | 11200 |
| holo4-27b / 2x / full | uncached | 1215.5 | 1898.1 | 100584 | 0 |
| holo4-27b / 2x / full | cached | 1192.6 | 1685.1 | 100584 | 36000 |
| holo4-35b-a3b / 1x / crop | uncached | 254.1 | 385.1 | 11836 | 0 |
| holo4-35b-a3b / 1x / crop | cached | 249.6 | 448.8 | 11836 | 1056 |
| holo4-35b-a3b / 1x / full | uncached | 342.2 | 1603.4 | 27152 | 0 |
| holo4-35b-a3b / 1x / full | cached | 335.8 | 427.8 | 27152 | 0 |
| holo4-35b-a3b / 2x / crop | uncached | 316.1 | 1025.7 | 39676 | 0 |
| holo4-35b-a3b / 2x / crop | cached | 330.9 | 713.7 | 39676 | 7392 |
| holo4-35b-a3b / 2x / full | uncached | 872.5 | 1198.0 | 100586 | 0 |
| holo4-35b-a3b / 2x / full | cached | 583.5 | 1074.9 | 100586 | 14784 |

**Attention : 0 requêtes en erreur HTTP sont comptées comme misses. Latence = tentative HTTP 200 seule, sans attente ni tentatives échouées. Attentes de pacing/cooldown et nombre de 429 sont comptés séparément.**

## Échecs (point pixels, boîte pixels)

| Modèle / échelle / image / cible / passage | Point prédit | Boîte attendue |
|---|---|---|
| holo4-35b-a3b / 1 / full / VIEW_3D/HEADER / 1 | (825.6, 10.8) | [0, 27, 1585, 54] |
| holo4-35b-a3b / 1 / full / VIEW_3D/HEADER / 2 | (825.6, 10.8) | [0, 27, 1585, 54] |
| holo4-35b-a3b / 1 / full / VIEW_3D/TOOL_HEADER / 1 | (1599.36, 41.04) | [0, 54, 1585, 81] |
| holo4-35b-a3b / 1 / full / VIEW_3D/TOOL_HEADER / 2 | (1599.36, 41.04) | [0, 54, 1585, 81] |
| holo4-35b-a3b / 1 / crop / VIEW_3D/TOOL_HEADER / 1 | (1596.128, 38.891999999999996) | [0, 54, 1585, 81] |
| holo4-35b-a3b / 1 / crop / VIEW_3D/TOOL_HEADER / 2 | (1596.128, 38.891999999999996) | [0, 54, 1585, 81] |
| holo4-35b-a3b / 1 / full / VIEW_3D/UI / 1 | (1599.36, 632.88) | [1294, 81, 1585, 976] |
| holo4-35b-a3b / 1 / full / VIEW_3D/UI / 2 | (1599.36, 632.88) | [1294, 81, 1585, 976] |
| holo4-35b-a3b / 1 / crop / VIEW_3D/UI / 1 | (1594.519, 374.881) | [1294, 81, 1585, 976] |
| holo4-35b-a3b / 1 / crop / VIEW_3D/UI / 2 | (1594.519, 374.881) | [1294, 81, 1585, 976] |
| holo4-35b-a3b / 1 / full / OUTLINER/HEADER / 1 | (1728.0, 62.64) | [1588, 27, 1920, 54] |
| holo4-35b-a3b / 1 / full / OUTLINER/HEADER / 2 | (1728.0, 62.64) | [1588, 27, 1920, 54] |
| holo4-35b-a3b / 1 / crop / PROPERTIES/NAVIGATION_BAR / 1 | (1604.584, 370.224) | [1588, 387, 1618, 1056] |
| holo4-35b-a3b / 1 / crop / PROPERTIES/NAVIGATION_BAR / 2 | (1604.584, 370.224) | [1588, 387, 1618, 1056] |
| holo4-35b-a3b / 1 / full / PROPERTIES/HEADER / 1 | (1599.36, 408.24) | [1588, 360, 1920, 387] |
| holo4-35b-a3b / 1 / full / PROPERTIES/HEADER / 2 | (1599.36, 408.24) | [1588, 360, 1920, 387] |
| holo4-35b-a3b / 1 / crop / PROPERTIES/HEADER / 1 | (1649.44, 410.4) | [1588, 360, 1920, 387] |
| holo4-35b-a3b / 1 / crop / PROPERTIES/HEADER / 2 | (1649.44, 410.4) | [1588, 360, 1920, 387] |
| holo4-35b-a3b / 1 / crop / DOPESHEET_EDITOR/HEADER / 1 | (793.237, 975.375) | [0, 979, 1585, 1006] |
| holo4-35b-a3b / 1 / crop / DOPESHEET_EDITOR/HEADER / 2 | (793.237, 975.375) | [0, 979, 1585, 1006] |
| holo4-35b-a3b / 2 / full / VIEW_3D/TOOL_HEADER / 1 | (3210.24, 812.16) | [0, 109, 3170, 163] |
| holo4-35b-a3b / 2 / full / VIEW_3D/TOOL_HEADER / 2 | (3210.24, 812.16) | [0, 109, 3170, 163] |
| holo4-35b-a3b / 2 / crop / VIEW_3D/TOOL_HEADER / 1 | (3201.91, 78.74799999999999) | [0, 109, 3170, 163] |
| holo4-35b-a3b / 2 / crop / VIEW_3D/TOOL_HEADER / 2 | (3201.91, 78.74799999999999) | [0, 109, 3170, 163] |
| holo4-35b-a3b / 2 / crop / VIEW_3D/UI / 1 | (3205.128, 80.741) | [2586, 163, 3170, 1952] |
| holo4-35b-a3b / 2 / crop / VIEW_3D/UI / 2 | (3205.128, 80.741) | [2586, 163, 3170, 1952] |
| holo4-35b-a3b / 2 / crop / OUTLINER/WINDOW / 1 | (3227.118, 82.4) | [3177, 109, 3840, 713] |
| holo4-35b-a3b / 2 / crop / OUTLINER/WINDOW / 2 | (3227.118, 82.4) | [3177, 109, 3840, 713] |
| holo4-35b-a3b / 2 / full / OUTLINER/HEADER / 1 | (3432.96, 127.44) | [3177, 55, 3840, 109] |
| holo4-35b-a3b / 2 / full / OUTLINER/HEADER / 2 | (3432.96, 127.44) | [3177, 55, 3840, 109] |
| holo4-35b-a3b / 2 / crop / PROPERTIES/NAVIGATION_BAR / 1 | (3218.586, 740.402) | [3177, 774, 3238, 2111] |
| holo4-35b-a3b / 2 / crop / PROPERTIES/NAVIGATION_BAR / 2 | (3218.586, 740.402) | [3177, 774, 3238, 2111] |
| holo4-35b-a3b / 2 / full / PROPERTIES/WINDOW / 1 | (3198.72, 812.16) | [3238, 774, 3840, 2111] |
| holo4-35b-a3b / 2 / full / PROPERTIES/WINDOW / 2 | (3198.72, 812.16) | [3238, 774, 3840, 2111] |
| holo4-35b-a3b / 2 / full / PROPERTIES/HEADER / 1 | (3494.4, 805.68) | [3177, 720, 3840, 774] |
| holo4-35b-a3b / 2 / full / PROPERTIES/HEADER / 2 | (3494.4, 805.68) | [3177, 720, 3840, 774] |
| holo4-35b-a3b / 2 / crop / PROPERTIES/HEADER / 1 | (3328.08, 950.069) | [3177, 720, 3840, 774] |
| holo4-35b-a3b / 2 / crop / PROPERTIES/HEADER / 2 | (3328.08, 950.069) | [3177, 720, 3840, 774] |
| holo4-35b-a3b / 2 / crop / DOPESHEET_EDITOR/HEADER / 1 | (157.68200000000002, 2035.0) | [0, 1959, 3170, 2013] |
| holo4-35b-a3b / 2 / crop / DOPESHEET_EDITOR/HEADER / 2 | (157.68200000000002, 2035.0) | [0, 1959, 3170, 2013] |
| holo4-27b / 1 / crop / OUTLINER/WINDOW / 1 | (1610.28, 40.800000000000004) | [1588, 54, 1920, 357] |
| holo4-27b / 1 / crop / OUTLINER/WINDOW / 2 | (1610.28, 40.800000000000004) | [1588, 54, 1920, 357] |
| holo4-27b / 1 / full / OUTLINER/HEADER / 1 | (1685.76, 65.88) | [1588, 27, 1920, 54] |
| holo4-27b / 1 / full / OUTLINER/HEADER / 2 | (1685.76, 65.88) | [1588, 27, 1920, 54] |
| holo4-27b / 1 / full / PROPERTIES/WINDOW / 1 | (1601.28, 407.16) | [1618, 387, 1920, 1056] |
| holo4-27b / 1 / full / PROPERTIES/WINDOW / 2 | (1601.28, 407.16) | [1618, 387, 1920, 1056] |
| holo4-27b / 1 / crop / DOPESHEET_EDITOR/WINDOW / 1 | (802.891, 1001.375) | [0, 1006, 1585, 1056] |
| holo4-27b / 1 / crop / DOPESHEET_EDITOR/WINDOW / 2 | (802.891, 1001.375) | [0, 1006, 1585, 1056] |
| holo4-27b / 2 / full / VIEW_3D/TOOL_HEADER / 1 | (3148.7999999999997, 295.92) | [0, 109, 3170, 163] |
| holo4-27b / 2 / full / VIEW_3D/TOOL_HEADER / 2 | (3148.7999999999997, 295.92) | [0, 109, 3170, 163] |
| holo4-27b / 2 / crop / VIEW_3D/TOOL_HEADER / 1 | (3150.422, 299.971) | [0, 109, 3170, 163] |
| holo4-27b / 2 / crop / VIEW_3D/TOOL_HEADER / 2 | (3150.422, 297.978) | [0, 109, 3170, 163] |
| holo4-27b / 2 / crop / OUTLINER/WINDOW / 1 | (3221.43, 82.4) | [3177, 109, 3840, 713] |
| holo4-27b / 2 / crop / OUTLINER/WINDOW / 2 | (3221.43, 82.4) | [3177, 109, 3840, 713] |
| holo4-27b / 2 / full / PROPERTIES/WINDOW / 1 | (3210.24, 889.92) | [3238, 774, 3840, 2111] |
| holo4-27b / 2 / full / PROPERTIES/WINDOW / 2 | (3210.24, 887.76) | [3238, 774, 3840, 2111] |

## Métadonnées

```json
{
  "timestamp_utc": "2026-11-07T13:49:08.268194+00:00",
  "git_commit": "caa96ec83ab08659a24ff0bfb794e0ff9dac51fb",
  "hostname": "devin-box",
  "cpu": "Intel(R) Xeon(R) Processor",
  "python": "3.11.17",
  "blender_version": "Blender 4.5.9 LTS"
}
```
