# Benchmark jev

Mesuré le 2026-11-07T13:52:34.372178+00:00

| Mesure | Valeur |
|---|---|
| logical_calls | 69 |
| http_attempts | 69 |
| http_errors | 0 |
| http_429 | 0 |
| input_tokens | 45889 |
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
| batch8 | 4 | 32 | 100.0% | 0 | 302.95040800001516 | 371.2854719999541 | 37.868801000001895 |
| all | 1 | 32 | 100.0% | 0 | 539.9854050001522 | 539.9854050001522 | 16.874543906254758 |

## Par étiquette (correct / total)

| Label | single | batch8 | all |
|---|---:|---:|---:|
| why | 8/8 | 4/4 | 4/4 |
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
  "all": []
}
```

## Latence de chaque batch

- batch8 : 308.2392449998679 ms ; amorti 38.529905624983485 ms/phrase.
- batch8 : 302.95040800001516 ms ; amorti 37.868801000001895 ms/phrase.
- batch8 : 212.12613700004113 ms ; amorti 26.51576712500514 ms/phrase.
- batch8 : 371.2854719999541 ms ; amorti 46.41068399999426 ms/phrase.
- all : 539.9854050001522 ms ; amorti 16.874543906254758 ms/phrase.

## Stabilité et connexion persistante

| Condition | Appels | p50 ms | p95 ms |
|---|---:|---:|---:|
| warm_single | 63 | 203.97454799990555 | 232.99705599993104 |
| single_pass_1 | 32 | 211.15663899990977 | 269.6514000001571 |
| single_pass_2 | 32 | 197.41307499998584 | 220.34529600000496 |

## Métadonnées

```json
{
  "timestamp_utc": "2026-11-07T13:52:34.372178+00:00",
  "git_commit": "5331932dd74365b3548b5e6c0371a784fe801106",
  "hostname": "devin-box",
  "cpu": "Intel(R) Xeon(R) Processor",
  "python": "3.11.17"
}
```
