# Benchmark holo

Mesuré le 2026-11-07T13:36:46.173957+00:00

| Mesure | Valeur |
|---|---|
| api_calls | 354 |
| prompt_tokens | 449672 |
| output_tokens | 1591 |
| cached_tokens | 252576 |
| cache_observed | true |
| cost_usd_computed | 0.06988808000000003 |
| http_errors | 75 |
| http_429 | 75 |
| hit_rate_http_200 | 0.7435897435897436 |

Mesures réelles ; coût calculé depuis les tokens aux tarifs imposés $0.30/M entrée, $0.03/M cache, $2/M sortie, pas une facture. Le catalogue annonce un tarif plus élevé pour 27B.
Passages 1 et 2 : requêtes identiques consécutives par paire. Aucune garantie que le premier soit sans cache ; seuls les cached_tokens retournés prouvent un cache. Latence inclut retries et backoff éventuels.
12 régions distinctes × 2 échelles × full/crop × 2 passages par modèle. Hit : point à l'intérieur du rectangle RNA (bord droit/bas exclus). Les régions superposées du viewport se chevauchent selon Blender.
Sources : https://hub.hcompany.ai/models-api/element-localization et https://hub.hcompany.ai/models-api/chat-completions. temperature=0, thinking off, structured_outputs JSON normalisé [0,1000].
## Résultats Holo

| Modèle / échelle / image | Hits | HTTP erreurs | p50 ms | p95 ms | Moy. entrée / sortie | Coût USD |
|---|---:|---:|---:|---:|---:|---:|
| holo4-27b / 1x / crop | 54.2% | 9 | 519.3 | 3058.3 | 800 / 8 | 0.00444 |
| holo4-27b / 1x / full | 54.2% | 9 | 500.0 | 3623.3 | 1397 / 8 | 0.00787 |
| holo4-27b / 2x / crop | 54.2% | 9 | 1235.3 | 4440.1 | 1985 / 9 | 0.00866 |
| holo4-27b / 2x / full | 54.2% | 9 | 1828.3 | 4343.5 | 5221 / 9 | 0.01467 |
| holo4-35b-a3b / 1x / crop | 37.5% | 10 | 682.9 | 3273.1 | 784 / 8 | 0.00432 |
| holo4-35b-a3b / 1x / full | 33.3% | 11 | 735.5 | 3563.8 | 1211 / 7 | 0.00337 |
| holo4-35b-a3b / 2x / crop | 33.3% | 8 | 1851.1 | 4326.4 | 2465 / 9 | 0.01105 |
| holo4-35b-a3b / 2x / full | 41.7% | 10 | 2281.0 | 4423.2 | 4873 / 8 | 0.01551 |

## Première requête vs répétition identique

| Passage | Appels | p50 ms | p95 ms | Tokens entrée | Tokens cachés |
|---|---:|---:|---:|---:|---:|
| 1 | 96 | 1235.3 | 4275.6 | 232130 | 131104 |
| 2 | 96 | 1711.7 | 4343.5 | 217542 | 121472 |

## Cache effectivement observé (tous modèles et conditions)

| Cache retourné | Appels | p50 ms | p95 ms | Tokens entrée | Tokens cachés |
|---|---:|---:|---:|---:|---:|
| False | 50 | 539.4506510000383 | 4515.656479999961 | 139432 | 0 |
| True | 67 | 485.0005620000388 | 1851.05611299997 | 310240 | 252576 |

**Attention : 75 requêtes en erreur HTTP sont comptées comme misses. Les latences incluent ces erreurs et retries ; les moyennes tokens incluent les zéros sans usage. Ce taux brut n'isole donc pas la qualité du modèle.**

## Échecs (point pixels, boîte pixels)

| Modèle / échelle / image / cible / passage | Point prédit | Boîte attendue |
|---|---|---|
| holo4-35b-a3b / 1 / crop / VIEW_3D/HEADER / 1 | [699.915, 12.97] | [0, 27, 1585, 54] |
| holo4-35b-a3b / 1 / crop / VIEW_3D/HEADER / 2 | [699.915, 12.97] | [0, 27, 1585, 54] |
| holo4-35b-a3b / 1 / full / VIEW_3D/TOOL_HEADER / 1 | [1601.28, 41.04] | [0, 54, 1585, 81] |
| holo4-35b-a3b / 1 / full / VIEW_3D/TOOL_HEADER / 2 | [1601.28, 41.04] | [0, 54, 1585, 81] |
| holo4-35b-a3b / 1 / crop / VIEW_3D/TOOL_HEADER / 1 | [1596.128, 39.888999999999996] | [0, 54, 1585, 81] |
| holo4-35b-a3b / 1 / crop / VIEW_3D/TOOL_HEADER / 2 | [1596.128, 39.888999999999996] | [0, 54, 1585, 81] |
| holo4-35b-a3b / 1 / full / VIEW_3D/UI / 1 | [1601.28, 635.04] | [1294, 81, 1585, 976] |
| holo4-35b-a3b / 1 / full / VIEW_3D/UI / 2 | [1601.28, 635.04] | [1294, 81, 1585, 976] |
| holo4-35b-a3b / 1 / full / OUTLINER/HEADER / 1 | [1728.0, 61.56] | [1588, 27, 1920, 54] |
| holo4-35b-a3b / 1 / crop / OUTLINER/HEADER / 1 | [1610.28, 6.78] | [1588, 27, 1920, 54] |
| holo4-35b-a3b / 1 / full / OUTLINER/HEADER / 2 | None | [1588, 27, 1920, 54] |
| holo4-35b-a3b / 1 / crop / OUTLINER/HEADER / 2 | None | [1588, 27, 1920, 54] |
| holo4-35b-a3b / 1 / crop / PROPERTIES/NAVIGATION_BAR / 1 | None | [1588, 387, 1618, 1056] |
| holo4-35b-a3b / 1 / full / PROPERTIES/NAVIGATION_BAR / 1 | None | [1588, 387, 1618, 1056] |
| holo4-35b-a3b / 1 / crop / PROPERTIES/NAVIGATION_BAR / 2 | None | [1588, 387, 1618, 1056] |
| holo4-35b-a3b / 1 / full / PROPERTIES/NAVIGATION_BAR / 2 | None | [1588, 387, 1618, 1056] |
| holo4-35b-a3b / 1 / crop / PROPERTIES/WINDOW / 1 | None | [1618, 387, 1920, 1056] |
| holo4-35b-a3b / 1 / full / PROPERTIES/WINDOW / 1 | None | [1618, 387, 1920, 1056] |
| holo4-35b-a3b / 1 / crop / PROPERTIES/WINDOW / 2 | None | [1618, 387, 1920, 1056] |
| holo4-35b-a3b / 1 / full / PROPERTIES/WINDOW / 2 | None | [1618, 387, 1920, 1056] |
| holo4-35b-a3b / 1 / crop / PROPERTIES/HEADER / 1 | None | [1588, 360, 1920, 387] |
| holo4-35b-a3b / 1 / full / PROPERTIES/HEADER / 1 | None | [1588, 360, 1920, 387] |
| holo4-35b-a3b / 1 / crop / PROPERTIES/HEADER / 2 | None | [1588, 360, 1920, 387] |
| holo4-35b-a3b / 1 / full / PROPERTIES/HEADER / 2 | None | [1588, 360, 1920, 387] |
| holo4-35b-a3b / 1 / crop / DOPESHEET_EDITOR/WINDOW / 1 | None | [0, 1006, 1585, 1056] |
| holo4-35b-a3b / 1 / full / DOPESHEET_EDITOR/WINDOW / 1 | None | [0, 1006, 1585, 1056] |
| holo4-35b-a3b / 1 / full / DOPESHEET_EDITOR/WINDOW / 2 | None | [0, 1006, 1585, 1056] |
| holo4-35b-a3b / 1 / crop / DOPESHEET_EDITOR/HEADER / 1 | None | [0, 979, 1585, 1006] |
| holo4-35b-a3b / 1 / full / DOPESHEET_EDITOR/HEADER / 1 | None | [0, 979, 1585, 1006] |
| holo4-35b-a3b / 1 / crop / DOPESHEET_EDITOR/HEADER / 2 | None | [0, 979, 1585, 1006] |
| holo4-35b-a3b / 1 / full / DOPESHEET_EDITOR/HEADER / 2 | None | [0, 979, 1585, 1006] |
| holo4-35b-a3b / 2 / crop / VIEW_3D/HEADER / 1 | None | [0, 55, 3170, 109] |
| holo4-35b-a3b / 2 / full / VIEW_3D/HEADER / 1 | None | [0, 55, 3170, 109] |
| holo4-35b-a3b / 2 / crop / VIEW_3D/HEADER / 2 | None | [0, 55, 3170, 109] |
| holo4-35b-a3b / 2 / full / VIEW_3D/HEADER / 2 | None | [0, 55, 3170, 109] |
| holo4-35b-a3b / 2 / full / VIEW_3D/TOOL_HEADER / 1 | None | [0, 109, 3170, 163] |
| holo4-35b-a3b / 2 / crop / VIEW_3D/TOOL_HEADER / 1 | [3195.474, 78.74799999999999] | [0, 109, 3170, 163] |
| holo4-35b-a3b / 2 / full / VIEW_3D/TOOL_HEADER / 2 | [3137.2799999999997, 302.40000000000003] | [0, 109, 3170, 163] |
| holo4-35b-a3b / 2 / crop / VIEW_3D/TOOL_HEADER / 2 | [3195.474, 78.74799999999999] | [0, 109, 3170, 163] |
| holo4-35b-a3b / 2 / crop / VIEW_3D/UI / 1 | [3201.91, 740.424] | [2586, 163, 3170, 1952] |
| holo4-35b-a3b / 2 / crop / VIEW_3D/UI / 2 | [3201.91, 740.424] | [2586, 163, 3170, 1952] |
| holo4-35b-a3b / 2 / crop / OUTLINER/WINDOW / 1 | [3221.43, 82.4] | [3177, 109, 3840, 713] |
| holo4-35b-a3b / 2 / crop / OUTLINER/WINDOW / 2 | [3221.43, 82.4] | [3177, 109, 3840, 713] |
| holo4-35b-a3b / 2 / full / OUTLINER/HEADER / 1 | [3459.84, 123.12] | [3177, 55, 3840, 109] |
| holo4-35b-a3b / 2 / full / OUTLINER/HEADER / 2 | [3459.84, 123.12] | [3177, 55, 3840, 109] |
| holo4-35b-a3b / 2 / crop / PROPERTIES/NAVIGATION_BAR / 1 | [3214.32, 740.402] | [3177, 774, 3238, 2111] |
| holo4-35b-a3b / 2 / crop / PROPERTIES/NAVIGATION_BAR / 2 | [3214.32, 740.402] | [3177, 774, 3238, 2111] |
| holo4-35b-a3b / 2 / full / PROPERTIES/WINDOW / 1 | [3198.72, 816.48] | [3238, 774, 3840, 2111] |
| holo4-35b-a3b / 2 / crop / PROPERTIES/WINDOW / 2 | None | [3238, 774, 3840, 2111] |
| holo4-35b-a3b / 2 / full / PROPERTIES/WINDOW / 2 | None | [3238, 774, 3840, 2111] |
| holo4-35b-a3b / 2 / crop / PROPERTIES/HEADER / 1 | None | [3177, 720, 3840, 774] |
| holo4-35b-a3b / 2 / full / PROPERTIES/HEADER / 1 | None | [3177, 720, 3840, 774] |
| holo4-35b-a3b / 2 / crop / PROPERTIES/HEADER / 2 | None | [3177, 720, 3840, 774] |
| holo4-35b-a3b / 2 / full / PROPERTIES/HEADER / 2 | None | [3177, 720, 3840, 774] |
| holo4-35b-a3b / 2 / crop / DOPESHEET_EDITOR/WINDOW / 1 | None | [0, 2013, 3170, 2111] |
| holo4-35b-a3b / 2 / full / DOPESHEET_EDITOR/WINDOW / 1 | None | [0, 2013, 3170, 2111] |
| holo4-35b-a3b / 2 / full / DOPESHEET_EDITOR/WINDOW / 2 | None | [0, 2013, 3170, 2111] |
| holo4-35b-a3b / 2 / crop / DOPESHEET_EDITOR/HEADER / 1 | None | [0, 1959, 3170, 2013] |
| holo4-35b-a3b / 2 / full / DOPESHEET_EDITOR/HEADER / 1 | None | [0, 1959, 3170, 2013] |
| holo4-35b-a3b / 2 / crop / DOPESHEET_EDITOR/HEADER / 2 | None | [0, 1959, 3170, 2013] |
| holo4-35b-a3b / 2 / full / DOPESHEET_EDITOR/HEADER / 2 | None | [0, 1959, 3170, 2013] |
| holo4-27b / 1 / crop / OUTLINER/WINDOW / 1 | [1608.5, 39.288000000000004] | [1588, 54, 1920, 357] |
| holo4-27b / 1 / crop / OUTLINER/WINDOW / 2 | [1608.5, 39.288000000000004] | [1588, 54, 1920, 357] |
| holo4-27b / 1 / full / OUTLINER/HEADER / 1 | [1672.32, 65.88] | [1588, 27, 1920, 54] |
| holo4-27b / 1 / full / OUTLINER/HEADER / 2 | [1672.32, 65.88] | [1588, 27, 1920, 54] |
| holo4-27b / 1 / crop / PROPERTIES/NAVIGATION_BAR / 2 | None | [1588, 387, 1618, 1056] |
| holo4-27b / 1 / full / PROPERTIES/NAVIGATION_BAR / 2 | None | [1588, 387, 1618, 1056] |
| holo4-27b / 1 / full / PROPERTIES/WINDOW / 1 | None | [1618, 387, 1920, 1056] |
| holo4-27b / 1 / crop / PROPERTIES/WINDOW / 1 | None | [1618, 387, 1920, 1056] |
| holo4-27b / 1 / crop / PROPERTIES/WINDOW / 2 | None | [1618, 387, 1920, 1056] |
| holo4-27b / 1 / full / PROPERTIES/WINDOW / 2 | None | [1618, 387, 1920, 1056] |
| holo4-27b / 1 / crop / PROPERTIES/HEADER / 1 | None | [1588, 360, 1920, 387] |
| holo4-27b / 1 / full / PROPERTIES/HEADER / 1 | None | [1588, 360, 1920, 387] |
| holo4-27b / 1 / crop / PROPERTIES/HEADER / 2 | None | [1588, 360, 1920, 387] |
| holo4-27b / 1 / full / PROPERTIES/HEADER / 2 | None | [1588, 360, 1920, 387] |
| holo4-27b / 1 / crop / DOPESHEET_EDITOR/WINDOW / 1 | None | [0, 1006, 1585, 1056] |
| holo4-27b / 1 / full / DOPESHEET_EDITOR/WINDOW / 1 | None | [0, 1006, 1585, 1056] |
| holo4-27b / 1 / crop / DOPESHEET_EDITOR/WINDOW / 2 | None | [0, 1006, 1585, 1056] |
| holo4-27b / 1 / full / DOPESHEET_EDITOR/WINDOW / 2 | None | [0, 1006, 1585, 1056] |
| holo4-27b / 1 / crop / DOPESHEET_EDITOR/HEADER / 1 | None | [0, 979, 1585, 1006] |
| holo4-27b / 1 / full / DOPESHEET_EDITOR/HEADER / 1 | None | [0, 979, 1585, 1006] |
| holo4-27b / 1 / crop / DOPESHEET_EDITOR/HEADER / 2 | None | [0, 979, 1585, 1006] |
| holo4-27b / 1 / full / DOPESHEET_EDITOR/HEADER / 2 | None | [0, 979, 1585, 1006] |
| holo4-27b / 2 / full / VIEW_3D/HEADER / 1 | None | [0, 55, 3170, 109] |
| holo4-27b / 2 / crop / VIEW_3D/HEADER / 1 | None | [0, 55, 3170, 109] |
| holo4-27b / 2 / full / VIEW_3D/HEADER / 2 | None | [0, 55, 3170, 109] |
| holo4-27b / 2 / crop / VIEW_3D/HEADER / 2 | None | [0, 55, 3170, 109] |
| holo4-27b / 2 / full / VIEW_3D/TOOL_HEADER / 1 | None | [0, 109, 3170, 163] |
| holo4-27b / 2 / crop / VIEW_3D/TOOL_HEADER / 1 | None | [0, 109, 3170, 163] |
| holo4-27b / 2 / full / VIEW_3D/TOOL_HEADER / 2 | None | [0, 109, 3170, 163] |
| holo4-27b / 2 / crop / VIEW_3D/TOOL_HEADER / 2 | None | [0, 109, 3170, 163] |
| holo4-27b / 2 / crop / OUTLINER/WINDOW / 1 | [3221.43, 82.4] | [3177, 109, 3840, 713] |
| holo4-27b / 2 / crop / OUTLINER/WINDOW / 2 | [3221.43, 82.4] | [3177, 109, 3840, 713] |
| holo4-27b / 2 / full / PROPERTIES/WINDOW / 1 | [3210.24, 814.32] | [3238, 774, 3840, 2111] |
| holo4-27b / 2 / full / PROPERTIES/WINDOW / 2 | [3210.24, 814.32] | [3238, 774, 3840, 2111] |
| holo4-27b / 2 / full / PROPERTIES/HEADER / 2 | None | [3177, 720, 3840, 774] |
| holo4-27b / 2 / crop / PROPERTIES/HEADER / 2 | None | [3177, 720, 3840, 774] |
| holo4-27b / 2 / crop / DOPESHEET_EDITOR/WINDOW / 1 | None | [0, 2013, 3170, 2111] |
| holo4-27b / 2 / full / DOPESHEET_EDITOR/WINDOW / 1 | None | [0, 2013, 3170, 2111] |
| holo4-27b / 2 / crop / DOPESHEET_EDITOR/WINDOW / 2 | None | [0, 2013, 3170, 2111] |
| holo4-27b / 2 / full / DOPESHEET_EDITOR/WINDOW / 2 | None | [0, 2013, 3170, 2111] |
| holo4-27b / 2 / crop / DOPESHEET_EDITOR/HEADER / 1 | None | [0, 1959, 3170, 2013] |
| holo4-27b / 2 / full / DOPESHEET_EDITOR/HEADER / 1 | None | [0, 1959, 3170, 2013] |
| holo4-27b / 2 / crop / DOPESHEET_EDITOR/HEADER / 2 | None | [0, 1959, 3170, 2013] |
| holo4-27b / 2 / full / DOPESHEET_EDITOR/HEADER / 2 | None | [0, 1959, 3170, 2013] |

## Métadonnées

```json
{
  "timestamp_utc": "2026-11-07T13:36:46.173957+00:00",
  "git_commit": "21e2a46bbb8f59b1cb3f5dd800e9927412af1893",
  "hostname": "devin-box",
  "cpu": "Intel(R) Xeon(R) Processor",
  "python": "3.11.17",
  "blender_version": "Blender 4.5.9 LTS"
}
```
