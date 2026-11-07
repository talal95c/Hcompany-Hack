# Benchmark pointer

Mesuré le 2026-11-07T16:34:38.479606+00:00

| Mesure | Valeur |
|---|---|
| calls | 54 |
| failures | 0 |

Modèles : holo4-27b ; 9 cibles, 3 répétitions.
| Méthode | N | Hit | Clic fonctionnel | Distance p50/p95 px | Latence p50/p95 ms | Mur p50/p95 ms | Échecs |
|---|---:|---:|---:|---:|---:|---:|---:|
| a11y | 27 | 100.0% | 100.0% (9) | 0.71/0.71 | 180.09/220.26 | 180.09/220.26 | 0 |
| holo:holo4-27b | 27 | 88.9% | 100.0% (9) | 6.50/38.58 | 249.67/376.18 | 376.25/35599.59 | 0 |
AT-SPI : recherche exacte + conversion, transport et création du client inclus. Holo : dernière requête HTTP ; mur = pacing et retries inclus, hors capture/clic.
Distances en pixels physiques, origine de fenêtre soustraite avant normalisation. PNG réduit : les millièmes restent ceux de la fenêtre entière, sans double DPI.
Hit géométrique auto-référencé pour AT-SPI ; test indépendant par vrai clic xdotool sur Gras/Italique/Souligné, lecture AT-SPI, puis restauration vérifiée.
Dénominateur fonctionnel : tous les essais des trois cibles de formatage, y compris les pointeurs manquants ; aucune action sur les autres cibles.
Les erreurs de protocole comptent comme échecs ; un miss ou un clic sans effet est un résultat incorrect, pas une erreur de protocole.

## Métadonnées

```json
{
  "timestamp_utc": "2026-11-07T16:34:38.479606+00:00",
  "git_commit": "ffa6935640564c843e4c40d26b8a521db7afdb17",
  "hostname": "devin-box",
  "cpu": "Intel(R) Xeon(R) Processor",
  "python": "3.11.18"
}
```
