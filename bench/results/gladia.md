# Benchmark gladia

Mesuré le 2026-11-07T13:55:38.722154+00:00

| Mesure | Valeur |
|---|---|
| sessions | 12 |
| audio_seconds | 27.620624999999997 |
| cost_eur_computed | 0.005217229166666666 |
| wer | 0.15625 |
| cer | 0.05389221556886228 |
| missing_partials | 0 |

Mesures réelles sur voix française synthétique offline Piper siwis medium, pas sur des apprenants ni un microphone réel. Coût calculé à 0,68 €/h audio, pas une facture ni une mesure de tarification/minimum fournisseur.
PCM brut 16 kHz mono 16-bit, blocs 100 ms (dernier bloc éventuellement court). Horloge monotone locale ; onset = premier sample |amplitude| ≥ 500, sur la timeline audio ancrée au premier envoi. Pas une détection VAD clinique.
Fin audio = retour du dernier send PCM, pas stop_recording ni fin acoustique. Final = dernier transcript final reçu ; segments dédupliqués par ID. Une valeur négative signifie un final reçu pendant l'envoi (silence de fin possible). Les partiels absents restent null, jamais remplacés par un final.
WER/CER : distance de Levenshtein, Unicode NFC/minuscules, ponctuation et apostrophes remplacées par espaces, accents conservés ; CER espaces inclus. Agrégat pondéré par longueur des références, sans correction métier.
## Latences

| Mesure | N | p50 ms | p95 ms |
|---|---:|---:|---:|
| init_ms | 12 | 192.28336800006218 | 1021.8939500000488 |
| connect_ms | 12 | 486.4333909999914 | 508.11374799991427 |
| first_audio_to_partial_ms | 12 | 768.2449700000689 | 866.3325459999669 |
| onset_to_partial_ms | 12 | 684.0792900000652 | 727.9324700000689 |
| audio_end_to_final_ms | 12 | 509.8760610001136 | 678.4358180000254 |
| audio_end_to_session_end_ms | 12 | 1195.7736809999915 | 2122.4259220000476 |

## Transcriptions

| Clip / répétition | Référence | Final | WER | CER |
|---|---|---|---:|---:|
| extrude / 1 | Comment je fais un extrude sur cette face ? |  Comment je fais un extrude sur cette face ? | 0.0% | 0.0% |
| extrude / 2 | Comment je fais un extrude sur cette face ? |  Comment je fais un extrude sur cette face ? | 0.0% | 0.0% |
| extrude / 3 | Comment je fais un extrude sur cette face ? |  Comment je fais un extrude sur cette face ? | 0.0% | 0.0% |
| torus / 1 | Ajoute un torus avec Shift A. |  Ajoute un torus avec Shifta. | 33.3% | 3.6% |
| torus / 2 | Ajoute un torus avec Shift A. |  Ajoute un torus avec Shifta. | 33.3% | 3.6% |
| torus / 3 | Ajoute un torus avec Shift A. |  Ajoute un torus avec Shifta. | 33.3% | 3.6% |
| viewport / 1 | Euh, je ne trouve plus la barre dans le viewport. |  Heure, je ne trouve plus la barre dans le vieux pote. | 30.0% | 17.0% |
| viewport / 2 | Euh, je ne trouve plus la barre dans le viewport. |  Heure, je ne trouve plus la barre dans le vieux pote. | 30.0% | 17.0% |
| viewport / 3 | Euh, je ne trouve plus la barre dans le viewport. |  Heure, je ne trouve plus la barre dans le vieux pote. | 30.0% | 17.0% |
| bevel / 1 | Pourquoi appliquer la scale avant le modifier bevel ? |  Pourquoi appliquer la scale avant le modifier bevel ? | 0.0% | 0.0% |
| bevel / 2 | Pourquoi appliquer la scale avant le modifier bevel ? |  Pourquoi appliquer la scale avant le modifier bevel ? | 0.0% | 0.0% |
| bevel / 3 | Pourquoi appliquer la scale avant le modifier bevel ? |  Pourquoi appliquer la scale avant le modifier bevel ? | 0.0% | 0.0% |

## Métadonnées

```json
{
  "timestamp_utc": "2026-11-07T13:55:38.722154+00:00",
  "git_commit": "d6d3ca69dbb70d844ee412d98fe6213eb0d258aa",
  "hostname": "devin-box",
  "cpu": "Intel(R) Xeon(R) Processor",
  "python": "3.11.17"
}
```
