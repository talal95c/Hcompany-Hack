# Icône du socle

`icon.png` est un carré RGBA 32×32, couleur #18202e, généré pour satisfaire le contexte Tauri sur Linux et macOS. Il ne constitue pas l'identité visuelle finale. Même avec le packaging désactivé, `generate_context!` requiert cette icône.

`icon.ico` est dérivé du même PNG pour les ressources Windows : `tauri-build`
requiert ce fichier même avec le packaging désactivé. Régénération :
`convert icon.png icon.ico`.
