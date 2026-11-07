# Services IA cloud
## Raccordement de production
`python -m engine` construit les clients réels lorsque leurs clés sont présentes :
`HAI_API_KEY`, `CODIV_API_KEY`, `GLADIA_API_KEY`, `LINKUP_API_KEY`. Les adaptateurs
`engine/services/adapters.py` conservent les clients batch/fichier pour prep et bench,
et exposent les Protocols du direct dans `engine/interfaces.py` (localize, decide,
transcribe, search). Tous sont fermés à l'arrêt. Une clé absente désactive seulement
le service concerné ; une dépendance manquante avec clé présente échoue explicitement.

Le pointage utilise `holo4-27b` par défaut ; `ENGINE_HOLO_MODEL` le remplace.
Le choix est distinct du modèle de compilation. Les intentions texte non triviales
passent par Jev ; `question` lit le pourquoi préécrit de l'étape sans appel LLM supplémentaire.
Le STT du raccordement actuel convertit PCM mono en WAV et utilise le traitement fichier
Gladia : ce n'est pas encore le streaming avec endpointing décrit ci-dessous, et le délai
du direct peut donc expirer et proposer le clavier. Linkup est injecté dans le moteur
mais aucune recherche automatique n'est ajoutée sur le chemin critique.

Tous les délais ci-dessous sont des politiques initiales (est.), pas des SLA mesurés. Les retries ont backoff et jitter, jamais de répétition aveugle d'action native. Propager timeout, unavailable, quota et invalid_response distinctement.
| Service / secret | Rôle et appel exact prévu | Délai / secours | Prix et quota |
|---|---|---|---|
| Holo4 35B-A3B / HAI_API_KEY | client OpenAI-compatible base_url https://api.hcompany.ai/v1 ; messages système stable + capture recadrée + description ; thinking off, temperature 0 ; structured output ou outil click, un appel pour localiser | localisation 5 s (est.), zone/menu si timeout ; compilation 60 s (est.), artefact pending ; computer use 10 s par tour (est.), stop puis proposition bpy | $0.30/M tokens entrée, $0.03/M cached, $2/M sortie ; crédits Pro, quota réel à vérifier |
| Jev via Codiv / nom de clé TBD | client HTTP persistant ; état facturé une fois ; questions simples groupées, intention isolée ; spéculation sur partiel, confirmation sur final | 800 ms avant règle locale ; réponse tardive ignorée ; ne pas dépasser 60 req/min | 60 req/min ; prix effectif à confirmer, aucun coût inventé |
| Gladia / GLADIA_API_KEY | ouvrir session live Solaria-1 puis envoyer audio, recevoir partiels/finals et endpointing ; fichiers via tâche async Solaria-3 puis suivi du job | live sans texte 2 s après fin parole (est.) → clavier ; job fichier 120 s (est.) → pending, reprise par job_id | live €0.68/h ; async €0.16/h ; endpointing défaut 0.05 s |
| Linkup / LINKUP_API_KEY | requête recherche ciblée doc Blender et version, récupérer passages et URLs, compiler candidat non fiable | 15 s (est.) → OBSERVE/pending ; pas de blocage du direct | tarif et quota à relever avant activation |
| Devin / DEVIN_API_KEY | créer tâche avec check manquant ou procédure cassée, contrat, fixture, résultat attendu ; récupérer PR et statut | asynchrone, état pending ; relance manuelle si échec, jamais attente dans la boucle live | coût et quota à confirmer |
| TTS / TBD | fournisseur non choisi ; texte compilé → audio indexé par hash texte, voix, langue, version | texte visible si absent ; aucune dépendance cachée à Gladia pour la synthèse | question ouverte, tarif et droits à vérifier |
## Holo comme LLM et agent
Compilation et réponses « pourquoi » hors script utilisent aussi Holo, pas un autre LLM implicite. Pré-écrire les pourquoi et pré-voicer à la compilation ; en live, lire le cache, sinon texte/stream. Computer use : capture → une action structurée → backend natif → nouvelle capture, avec leçon en contexte et check indépendant. Valider bornes [0,1000], cible visible et action autorisée avant injection.
## Jev : mesures et limites
Mesures publiques : médiane serveur 184 ms ; ~460–560 ms depuis un laptop, dont plancher TCP ~200 ms. Plusieurs questions dans un appel ≈ même latence, état facturé une fois. Ce ne sont pas des mesures de notre application ni du réseau de salle. Connexion persistante, token bucket partagé pour direct et spéculation ; limiter les révisions partielles et réserver du quota au final. API précise Codiv et nom de variable restent à figer, sans recopier de clés dans les docs.
## Coûts
Coût Holo = tokens entrée non cachés/1M × 0.30 + cached/1M × 0.03 + sortie/1M × 2 dollars. Audio Gladia = durée heures × tarif du mode. Mesurer tokens et durée dans bench ; pas de total par leçon annoncé comme acquis. Ne pas confondre euros et dollars.
## Secrets et observabilité
Variables injectées au runtime, jamais dans git, lesson.json, WebView, prompt ou trace. Logguer service, request_id, durée, statut, tokens si fournis ; pas l'audio, la capture ou le texte privé par défaut. Les conditions de rétention de chaque fournisseur restent à vérifier.
