"""Catalogue de procédures de confiance."""

PRIMITIVES = (
    "cube",
    "uv_sphere",
    "ico_sphere",
    "cylinder",
    "cone",
    "torus",
    "plane",
    "monkey",
    "circle",
    "grid",
)
PROCEDURE_LIBRARY = {
    f"add_primitive/{name}": {
        "operator_id": f"mesh.primitive_{name}_add",
        "preconditions": {"mode": "OBJECT"},
    }
    for name in PRIMITIVES
}
CHECK_LIBRARY = ["object_exists"]

FRENCH_LABELS = {
    "cube": "Cube",
    "uv_sphere": "Sphère UV",
    "ico_sphere": "Icosphère",
    "cylinder": "Cylindre",
    "cone": "Cône",
    "torus": "Tore",
    "plane": "Plan",
    "monkey": "Singe",
    "circle": "Cercle",
    "grid": "Grille",
}


def target_description(signature: dict) -> str:
    labels = {"Add": "Ajouter", "Mesh": "Maillage", "UV Sphere": "Sphère UV"}
    for primitive, french in FRENCH_LABELS.items():
        labels[primitive.replace("_", " ").title()] = french
        labels[f"add_primitive/{primitive}"] = french
    return " › ".join(labels.get(label, label) for label in signature["ui_paths"][0].split(" › "))
