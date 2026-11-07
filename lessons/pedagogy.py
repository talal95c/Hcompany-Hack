"""Textes pédagogiques rédigés étape par étape, sans génération de prose."""

CONTENT = {
    "donut": {
        "add_torus": (
            "Le tore donne directement l'anneau de pâte : inutile de creuser un cylindre.",
            [
                "Commence par une forme en anneau.",
                "Surligne Ajouter dans la vue 3D : Maj+A › Maillage › Tore.",
                "Pointe Tore, puis règle 48 segments majeurs, 12 mineurs et les rayons "
                "à 1 m et 0,25 m.",
                "Démo de 4 s : un anneau apparaît au centre ; annule, puis ajoute "
                "toi-même le tore.",
            ],
        ),
        "adjust_torus_redo": (
            "Règle la primitive avant toute autre action : le panneau de dernière opération "
            "ne permet ensuite plus de reprendre ces paramètres.",
            [
                "Épaissis la pâte sans agrandir le trou de manière incontrôlée.",
                "Surligne le panneau de dernière opération en bas à gauche ; F9 le rouvre.",
                "Pointe Rayon majeur : 1 m, puis Rayon mineur : 0,45 m ; garde 48 et 12 segments.",
                "Démo de 3 s : le petit rayon passe de 0,25 à 0,45 m ; annule ce "
                "réglage et refais-le.",
            ],
        ),
        "add_subdivision": (
            "La subdivision arrondit la surface sans alourdir le maillage que tu édites à la main.",
            [
                "Arrondis la silhouette en gardant peu de sommets à manipuler.",
                "Surligne la vue 3D puis les modificateurs ; Ctrl+2 ajoute une "
                "subdivision de niveau 2.",
                "Pointe Subdivision de surface : vérifie Niveaux de vue à 2, sans "
                "appliquer le modificateur.",
                "Démo de 4 s : Ctrl+2 adoucit le contour ; annule l'ajout, puis refais "
                "le raccourci.",
            ],
        ),
        "shade_smooth": (
            "L'ombrage lissé efface les facettes d'éclairage sans modifier les "
            "sommets ni la silhouette.",
            [
                "Fais disparaître les facettes de lumière sur la pâte.",
                "Surligne le menu de l'objet : clic droit › Ombrage lissé.",
                "Pointe Ombrage lissé sur le tore sélectionné en mode Objet, pas Lisser par angle.",
                "Démo de 3 s : les reflets deviennent continus ; annule l'ombrage et "
                "refais le geste.",
            ],
        ),
        "proportional_tweak": (
            "Une petite déformation avec les sommets voisins donne l'irrégularité "
            "organique d'un vrai donut.",
            [
                "Soulève doucement la pâte plutôt que de tirer une pointe isolée.",
                "Surligne l'édition proportionnelle : Tab, sélection d'un sommet, O "
                "puis G Z ; molette pour le rayon.",
                "Pointe le sommet le plus à droite : déplace-le de 0,12 m en Z, rayon "
                "0,5 m, influence douce ; Tab pour sortir.",
                "Démo de 5 s : un sommet entraîne ses voisins ; annule la translation, "
                "puis recrée cette bosse douce.",
            ],
        ),
        "icing_separate": (
            "Dupliquer puis séparer conserve la pâte entière et crée un glaçage qui "
            "épouse exactement sa surface.",
            [
                "Prélève une copie du dessus, sans trouer la pâte.",
                "Surligne la sélection de faces en mode Édition : Maj+D, clic droit, "
                "puis P › Sélection.",
                "Pointe les faces dont le centre est au-dessus de Z = 0 ; duplique sans "
                "déplacement et sépare la sélection.",
                "Démo de 5 s : le dessus copié devient un second objet ; annule "
                "séparation et duplication, puis refais les deux.",
            ],
        ),
        "solidify_icing": (
            "Solidifier donne une épaisseur au glaçage sans devoir modéliser sa face intérieure.",
            [
                "Donne une fine tranche au glaçage, pas à la pâte.",
                "Surligne les modificateurs du glaçage : Ajouter un modificateur › "
                "Générer › Solidifier.",
                "Pointe Épaisseur du modificateur Solidifier sur le glaçage et saisis 0,035 m.",
                "Démo de 4 s : un bord fin apparaît sur le glaçage ; annule le "
                "modificateur et reconstruis cette épaisseur.",
            ],
        ),
        "donut_material": (
            "Une teinte beige distingue la pâte cuite du glaçage et permet de "
            "vérifier leur affectation séparée.",
            [
                "Réserve une couleur chaude à la pâte.",
                "Surligne Matériau sur le donut : Nouveau › Surface › Couleur de base.",
                "Pointe la couleur du Principled BSDF de la pâte : RGBA linéaire 0,65 ; "
                "0,36 ; 0,15 ; 1.",
                "Démo de 4 s : seule la pâte reçoit le beige ; annule l'affectation, "
                "puis recrée son matériau.",
            ],
        ),
        "icing_material": (
            "Un matériau rose indépendant laisse le glaçage modifiable sans recolorer la pâte.",
            [
                "Ajoute le rose uniquement à la couche du dessus.",
                "Surligne Matériau sur le glaçage : Nouveau › Surface › Couleur de base.",
                "Pointe le Principled BSDF du glaçage : RGBA linéaire 0,8 ; 0,16 ; 0,36 "
                "; 1, sans partager le beige.",
                "Démo de 4 s : le dessus devient rose et la pâte reste beige ; annule "
                "puis refais l'affectation rose.",
            ],
        ),
    },
    "mini-cube": {
        "add_cube": (
            "Le cube fournit six faces simples pour observer ensuite l'effet du "
            "biseau et de l'ombrage.",
            [
                "Pose un volume simple au centre de la scène.",
                "Surligne Ajouter : Maj+A › Maillage › Cube.",
                "Pointe Cube dans Maillage et garde une taille de 2 m, sans déplacement.",
                "Démo de 3 s : un cube apparaît à l'origine ; annule sa création, puis "
                "ajoute-le toi-même.",
            ],
        ),
        "add_bevel": (
            "Le biseau casse les arêtes trop parfaites du cube et leur permet "
            "d'accrocher la lumière.",
            [
                "Adoucis les arêtes sans remplacer le cube par une sphère.",
                "Surligne les modificateurs : Ajouter un modificateur › Générer › Biseau.",
                "Pointe Biseau sur le cube actif ; conserve sa largeur initiale de 0,1 "
                "m et un segment.",
                "Démo de 4 s : les arêtes reçoivent une petite bande ; annule le biseau "
                "et ajoute-le à nouveau.",
            ],
        ),
        "shade_smooth": (
            "L'ombrage lissé change l'éclairage des faces ; il ne remplace pas le "
            "biseau qui change la géométrie.",
            [
                "Compare maintenant un éclairage continu aux faces plates.",
                "Surligne le menu contextuel du cube : clic droit › Ombrage lissé.",
                "Pointe Ombrage lissé en mode Objet pour l'appliquer aux six faces du cube.",
                "Démo de 3 s : l'éclairage change sans ajouter de sommets ; annule, "
                "puis lisse le cube toi-même.",
            ],
        ),
    },
}
