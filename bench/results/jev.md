# Benchmark jev

Mesuré le 2026-11-07T13:53:30.232920+00:00

| Mesure | Valeur |
|---|---|
| logical_calls | 69 |
| http_attempts | 69 |
| http_errors | 0 |
| http_429 | 0 |
| input_tokens | 45886 |
| output_tokens | 0 |
| cold_first_call_ms | 329.6347599998626 |
| extra_result_ids | 0 |

Latences réelles : seule tentative HTTP 200, hors pacing et retries. Amorti = durée batch / nombre de phrases, pas une latence individuelle.
Cold = première requête HTTP de ce client (connexion/TLS inclus), pas un modèle GPU froid garanti. Warm = même httpx.AsyncClient conservé sur toute la matrice.
Golds écrits manuellement avant les appels ; petit jeu synthétique, sans audio ni contexte d'étape, pas une validation sur des apprenants réels.
API typée choice : ni system message chat ni température ; définitions et instructions stables. Aucun modèle chat utilisé. Quota documentaire 1200 req/min non mesuré ; pacing local 1.05 s entre départs.
## Résultats

| Mode | Appels | Phrases | Exactitude | Parse fails | p50 ms | p95 ms | Amorti p50 ms/phrase |
|---|---:|---:|---:|---:|---:|---:|---:|
| single | 64 | 64 | 96.9% | 0 | 203.97454799990555 | 237.50392900001316 | 203.97454799990555 |
| batch8 | 4 | 32 | 100.0% | 0 | 266.50250200009395 | 1704.4437489998927 | 33.312812750011744 |
| all | 1 | 32 | 96.9% | 0 | 692.6333679998606 | 692.6333679998606 | 21.644792749995645 |

## Par étiquette (correct / total)

| Label | single | batch8 | all |
|---|---:|---:|---:|
| why | 8/8 | 4/4 | 3/4 |
| help | 6/8 | 4/4 | 4/4 |
| delegate | 8/8 | 4/4 | 4/4 |
| stop | 8/8 | 4/4 | 4/4 |
| repeat | 8/8 | 4/4 | 4/4 |
| next | 8/8 | 4/4 | 4/4 |
| question | 8/8 | 4/4 | 4/4 |
| other | 8/8 | 4/4 | 4/4 |

## Confusions

```json
{
  "single": [
    {
      "id": "help4",
      "text": "Tu peux juste me montrer où est le modifier bevel ?",
      "gold": "help",
      "predicted": "delegate"
    },
    {
      "id": "help4",
      "text": "Tu peux juste me montrer où est le modifier bevel ?",
      "gold": "help",
      "predicted": "delegate"
    }
  ],
  "batch8": [],
  "all": [
    {
      "id": "why1",
      "text": "Euh pourquoi on applique la scale avant le bevel ?",
      "gold": "why",
      "predicted": "stop"
    }
  ]
}
```

## Latence de chaque batch

- batch8 : 353.7012560000221 ms ; amorti 44.212657000002764 ms/phrase.
- batch8 : 1704.4437489998927 ms ; amorti 213.0554686249866 ms/phrase.
- batch8 : 266.50250200009395 ms ; amorti 33.312812750011744 ms/phrase.
- batch8 : 217.9691339999863 ms ; amorti 27.246141749998287 ms/phrase.
- all : 692.6333679998606 ms ; amorti 21.644792749995645 ms/phrase.

## Stabilité et connexion persistante

| Condition | Appels | p50 ms | p95 ms |
|---|---:|---:|---:|
| warm_single | 63 | 203.97454799990555 | 232.99705599993104 |
| single_pass_1 | 32 | 211.15663899990977 | 269.6514000001571 |
| single_pass_2 | 32 | 197.41307499998584 | 220.34529600000496 |

## Métadonnées

```json
{
  "timestamp_utc": "2026-11-07T13:53:30.232920+00:00",
  "git_commit": "4e0d58566744528f6f161f7bab9e62085a4af806",
  "hostname": "devin-box",
  "cpu": "Intel(R) Xeon(R) Processor",
  "python": "3.11.17"
}
```
