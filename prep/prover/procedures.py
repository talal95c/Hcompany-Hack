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
