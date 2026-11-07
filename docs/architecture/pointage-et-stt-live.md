# Pointage dévoilé et transcription live

## Capture corrélée

La leçon porte `help.menu_id` pour un chemin de menu. `prep.ui_map.operator_menu`
retrouve le conteneur direct d'un opérateur ; le compilateur renseigne cette aide.
Les leçons fournies ont été repassées dans le prover Blender réel ; leurs manifestes
incluent les nouveaux SHA256 et les durées réellement mesurées.

La policy ne connaît pas d'identifiant de menu applicatif : `HelpContext.reveal_target`
est une capacité optionnelle. L'adaptateur add-on ouvre le menu, attend son
`command.result`, laisse le popup se dessiner, puis fournit `screen_rect` de la région.
Le moteur émet `capture.request` avec identifiant, révision UI et génération. Le desktop
capture ce rectangle sans reprendre les champs manuels du pill. Une capture de pointage
doit correspondre à la demande, à la génération et à l'époque de capture ; délai maximal
10 secondes. Le cache est également isolé par identifiant de demande.

Un adaptateur peut ne pas proposer `reveal_target` : `crop: null` demande au desktop
le rectangle d'une fenêtre applicative. Ce fallback est actuellement disponible sur
Linux, en excluant les fenêtres de notre processus. Sur les autres plateformes, un
adaptateur doit fournir le rectangle : échec explicite plutôt qu'une capture du bureau
entier. Le choix de l'application cible et les backends multi-app complets restent à
formaliser dans la prochaine refonte ; l'évaluation pédagogique reste liée à l'add-on.

Holo renvoie aussi `visible` : il doit être explicitement vrai. Les coordonnées doivent
être finies et strictement intérieures à la capture. La confiance logprob n'est pas
une probabilité calibrée de bon pointage : elle ne suffit plus à accepter un point.
Le moteur exige des bornes a11y prouvées contenant le point, ou une vérification locale
indépendante qui identifie le rectangle de la cellule/ligne de menu demandée. Dans ce
second cas, réponse `yes/direct`, rectangle valide et point intérieur avec une marge
de deux pixels encodés sont tous requis ; réponse ambiguë ou malformée = refus.
Les refus conservent la consigne textuelle et sont journalisés par motif, sans image.

Au début d'étape et après dévoilement, la pré-localisation utilise la priorité
spéculative uniquement après opt-in explicite de l'apprenant à l'assistance vision
cloud : `ENGINE_CLOUD_VISION_PRELOAD=1` (ou `EngineConfig.cloud_vision_preload=True`).
La valeur par défaut est désactivée ; la permission de capture écran n'est pas un
consentement à cet envoi cloud. Sans opt-in, la pré-localisation a11y reste locale et
Holo n'est appelé pour le pointage qu'à l'escalade demandant effectivement le pointeur.
L'opt-in n'annule aucune vérification de permission, génération ou fraîcheur.
La pré-localisation cloud consentie utilise la priorité
spéculative du planificateur partagé. Le niveau 2 dévoile et prépare ; l'escalade
suivante affiche le point si le cache est prêt. Le cache comprend cible, génération,
révisions UI/capture et contexte de région, d'échelle et d'application. Une référence
a11y fraîche a priorité sur un point visuel préchargé. Les changements observés
annulent les spéculations. Juste avant affichage, le desktop relit la ref a11y, ou
compare les pixels de la zone de preuve à la capture d'origine : un changement dans
cette zone, même non signalé, invalide le point malgré un hit du cache.

Les crops natifs peuvent atteindre 16 mégapixels mais le PNG transmis est réduit à
1 048 576 pixels et 8192 pixels par axe, sans agrandissement. `crop` reste physique ;
`image_size` décrit le PNG. Les coordonnées normalisées restent rapportées au crop
physique, puis à l'origine intérieure et à l'échelle du WebView. Sous Linux, les
bounds AT-SPI Window sont traduits par l'origine cliente native validée du frame ;
les hit-tests de tables utilisent ce même repère Window.

Limite de calibration : le petit jeu réel `tests/engine/fixtures/pointer-labelled.json`
ne démontre pas encore une vérification visuelle utilisable. Le verdict seul a accepté
deux négatifs ; la règle stricte par rectangle n'a accepté aucun positif. Ce verrou
reste fermé : zéro faux accepté sur ces exemples n'est pas une garantie générale,
et un rappel nul n'est pas une réussite du pointage Holo.
Sans preuve locale, nouvelle surbrillance et instruction textuelle. La limite de
1 048 576 pixels porte sur le PNG transmis, non sur le rectangle physique conservé.

**Limites de validation :** le rectangle du popup lui-même n'est pas encore exposé ;
la validation géométrique porte donc sur la région. La conversion écran de l'add-on
et la qualité par cible nécessitent encore la recette graphique complète et la matrice
d'au moins trois essais par cible. Une présence dans un menu ne prouve pas que toutes
les propriétés décrites par une cible sont visibles dans ce menu.

## Gladia live

Au premier `audio.chunk`, une session Gladia live est ouverte. Les chunks PCM s16le
mono sont transmis au fil de l'arrivée, avec file bornée, numérotation, limite de taille,
délais et annulation à la déconnexion. `ptt.stop` ferme l'entrée puis attend les finals,
sans convertir le flux en WAV pour une transcription fichier. Les partiels et finals
sont diffusés dans `lesson.state` (`transcript`, `transcript_final`) ; chaque final passe
à Jev pour l'intention. Le desktop affiche le transcript dans une zone `aria-live`.

Le vocabulaire de service n'a plus de liste applicative intégrée. La configuration
`ENGINE_STT_VOCABULARY` fournit des termes séparés par des virgules, transmis à la session
live. Exemple de configuration d'une leçon : `tore,torus`. Une application différente
fournit son propre vocabulaire. Aucun service TTS n'est implémenté.

La recette synthétique utilise Piper uniquement pour fabriquer un WAV français de test,
injecté en temps réel par le protocole desktop `audio.chunk`. Les traces de cette recette
sont conservées hors dépôt sous `/home/ubuntu/e2e2/`. L'instant de fin de parole mesuré est
l'envoi du dernier chunk audio du WAV, pas une annotation acoustique humaine.
