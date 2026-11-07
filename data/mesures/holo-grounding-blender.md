# Holo sur des cibles Blender publiques (2026-11-07)

Mesure ponctuelle, faite hors du dépôt. Ce n'est pas encore une commande de `bench/`.

- Cibles : 71 ScreenSpot-Pro (Blender, Windows 2560×1440) et 60 GroundCUA (tirées au hasard dans
  20 captures Blender, dont une partie en résolution Mac Retina).
- Réussite : le point renvoyé par Holo tombe dans la bbox annotée.
- 262 appels (2 modèles × 131 cibles), aucune erreur HTTP ; coût calculé ≈ 0,36 $ aux tarifs du bench
  (passe principale et essai de zoom), pas une facture.

| Pointage du premier coup | holo4-27b | holo4-35b-a3b |
|---|---:|---:|
| ScreenSpot-Pro (71) | 71,8 % | 73,2 % |
| GroundCUA (60) | 66,7 % | 80,0 % |
| Latence p50 | 520–860 ms | 450–820 ms |

- GroundCUA : 35b réussit 9 cibles que 27b rate, l'inverse 1 fois (p ≈ 0,02). ScreenSpot-Pro : 5 contre 4.
- Zoom en deux passes (recadrer autour du premier point, redemander) : gain net de −10 à +1,7 point.
  Inutile à l'aveugle.

## Ce que ça implique pour le graphe
- La vision seule rate environ 1 petite cible sur 4 : le graphe doit fournir un `menu_id` ou une zone
  connue avant d'appeler Holo.
- Le recadrage doit venir d'une zone connue (add-on, graphe), pas du premier point de Holo.
