# Benchmark addon

Mesuré le 2026-11-07T13:29:36.159336+00:00

| Mesure | Valeur |
|---|---|
| startup_to_hello_ms | 263.4212160000118 |
| one_way | {"hello": {"count": 1, "p50_ms": 0.4614869999932125, "p95_ms": 0.4614869999932125, "max_ms": 0.4614869999932125}, "snapshot": {"count": 51, "p50_ms": 0.12511799999629147, "p95_ms": 0.17108400000142865, "max_ms": 0.8258330000389833}, "operator.executed": {"count": 50, "p50_ms": 0.12676499999361113, "p95_ms": 0.2756999999983236, "max_ms": 0.33099200000287965}, "scene.changed": {"count": 50, "p50_ms": 0.34448699999484234, "p95_ms": 0.5394519999972545, "max_ms": 0.628182000014931}, "heartbeat": {"count": 50, "p50_ms": 0.6332730000140145, "p95_ms": 0.8155239999759942, "max_ms": 0.9340870000014547}, "command.result": {"count": 50, "p50_ms": 0.4024820000049658, "p95_ms": 0.552811000001384, "max_ms": 0.6975220000022091}} |
| rtt | {"count": 50, "p50_ms": 0.6060439999941991, "p95_ms": 0.8861840000236043, "max_ms": 0.9584490000236201} |
| counts | {"hello": 1, "snapshot": 51, "operator.executed": 50, "scene.changed": 50, "heartbeat": 50, "command.result": 50} |
| invalid_events | 0 |
| invalid_commands | 0 |

Sonde autonome, pas le véritable add-on ni le moteur de production.
Linux : CLOCK_MONOTONIC partagé entre processus sur le même hôte ; aucune comparaison inter-hôtes. Réception horodatée avant validation.
Percentiles nearest-rank ; aucune latence simulée. RTT = request_snapshot → snapshot puis command.result.
Événements émis directement après chaque opération bpy réelle ; ces mesures excluent les observateurs du véritable add-on.

## Métadonnées

```json
{
  "timestamp_utc": "2026-11-07T13:29:36.159336+00:00",
  "git_commit": "84db8dfa60e946cc304654060869307226b39782",
  "hostname": "devin-box",
  "cpu": "Intel(R) Xeon(R) Processor",
  "python": "3.11.17",
  "blender_version": "4.5.9 LTS"
}
```
