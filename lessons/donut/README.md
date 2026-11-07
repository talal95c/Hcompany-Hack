# Mon premier donut

Leçon originale inspirée du style débutant de la partie 1 du donut classique,
sans copie vidéo ; voir [SOURCE.md](SOURCE.md) pour les limites de droits.
Blender **4.5.9**, langue **fr-FR**, neuf étapes prouvées par `bpy` :

1. Ajouter un tore de 48 × 12 segments.
2. Ajuster la dernière opération : rayons 1 m et 0,45 m.
3. Subdivision de niveau 2.
4. Ombrage lissé.
5. Déformation proportionnelle d'un sommet : déplacement Z de 0,12 m, rayon 0,5 m.
6. Dupliquer les faces supérieures et séparer le glaçage.
7. Solidifier le glaçage : épaisseur 0,035 m.
8. Matériau beige de la pâte.
9. Matériau rose du glaçage.

Le lanceur vide la scène initiale. Les préconditions de mode et de rôle actif sont
préparées avant chaque étape. Les sélections manuelles sont remplacées par une
règle géométrique explicite dans `steps.json`. Les preuves sont dans `proof/`.

Depuis la racine :

```sh
python tests/lessons/prove.py lessons/donut lessons/donut/proof-run.json
```

Voir [les checks et commandes de validation](../README.md).
Le contrat reste limité à l'existence du sujet ; le compagnon valide les gestes
réels. `ui_path_verified=false` : ni menus ni pointeur ni rendu visuel vérifiés.
