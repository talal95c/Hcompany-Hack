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

Holo renvoie aussi `visible`. Aucun pointeur pour une cible explicitement invisible,
un point sur/hors des bornes de la capture ou une confiance fournie inférieure à 0,5.
Sans rectangle attendu d'adaptateur, confiance finie et visibilité explicite sont
obligatoires. Sinon, nouvelle surbrillance et instruction textuelle. La limite de capture
reste 1 048 576 pixels : les grandes fenêtres échouent explicitement.

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
