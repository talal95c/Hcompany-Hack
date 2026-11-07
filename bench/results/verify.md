# Benchmark verify

Mesuré le 2026-11-07T16:27:05.434953+00:00

| Mesure | Valeur |
|---|---|
| calls | 80 |
| accuracy | 0.875 |
| yes_precision | 0.8947368421052632 |
| yes_recall | 0.85 |
| unknown_rate | 0.0 |
| failures | 0 |
| confusion | {"yes": {"yes": 34, "no": 6, "unknown": 0, "failure": 0}, "no": {"yes": 4, "no": 36, "unknown": 0, "failure": 0}} |
| latency | {"count": 80, "p50_ms": 9868.342221000148, "p95_ms": 45399.03599399986, "max_ms": 350185.070776} |
| request_latency | {"count": 80, "p50_ms": 272.90915799994764, "p95_ms": 665.3513879998627, "max_ms": 1659.7711069998695} |
| http_attempts | 100 |
| http_429 | 4 |

Modèles : holo4-27b ; 20 scènes, 40 questions, 2 répétitions ; thinking désactivé.
## Précision par application

| Groupe | Appels | Accuracy | Précision yes | Rappel yes | Unknown | Échecs | p50 ms | p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| global | 80 | 87.5% | 89.5% | 85.0% | 0.0% | 0 | 9868.3 | 45399.0 |
| calc | 40 | 75.0% | 77.8% | 70.0% | 0.0% | 0 | 9924.1 | 85354.4 |
| blender | 40 | 100.0% | 100.0% | 100.0% | 0.0% | 0 | 9748.0 | 10384.7 |
Labels provenant uniquement d'AT-SPI/bpy avant capture ; aucun label fourni à Holo.
Accuracy sur tous les appels : unknown et échecs ne sont pas corrects. Précision/rappel calculés avec yes comme classe positive.
Confiance minimale 0.8 : verdicts sous le seuil traités comme unknown.
Latence = durée murale du client par appel logique, pacing et retries inclus ; request_latency isole la dernière tentative HTTP.
Répétitions du même dataset, pas des observations indépendantes. Petit jeu synthétique, pas une validation du moteur pédagogique.

## Métadonnées

```json
{
  "timestamp_utc": "2026-11-07T16:27:05.434953+00:00",
  "git_commit": "589feae32db77e8d11f929670889b8dbbe2cd22e",
  "hostname": "devin-box",
  "cpu": "Intel(R) Xeon(R) Processor",
  "python": "3.11.18"
}
```
