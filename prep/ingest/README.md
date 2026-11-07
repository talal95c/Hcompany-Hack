# prep/ingest/

## Responsabilité
Ingestion.

## Entrées
source vidéo/doc.

## Sorties
transcription horodatée et empreinte.

## Dépend de
Contrats v1, interfaces documentées et composants amont ; aucune dépendance de modèle local. Les appels bpy restent dans addon et les accès natifs dans desktop. Voir [conception détaillée](../../docs/architecture/preparation.md) et [guide des agents](../../AGENTS.md).

## État et validation
`await ingest(source, work_dir=Path(...), language="fr")` accepte fichiers et URL HTTP(S).
Texte UTF-8 direct ; audio/vidéo converti par ffmpeg en WAV mono 16 kHz puis Gladia v2
(clé GLADIA_API_KEY). Téléchargement borné en taille et durée, polling limité à 120 s,
job conservé dans gladia-job.json. Transcript typé avec SHA-256, mots horodatés et
latences upload/transcription. `ui_map=` enrichit le vocabulaire. Tests stubs et live
sur narration synthétisée ; silence, fichier vide, erreur et timeout sont explicites.
