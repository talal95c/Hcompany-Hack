"""Erreurs pédagogiques et gestes reproductibles associés."""

from copy import deepcopy
from typing import Any


def check(name: str, **params: Any) -> dict:
    return {"name": name, "params": params}


def errors(lesson_id: str, sid: str, actions: list[dict]) -> list[dict]:
    mistake = deepcopy(actions)
    if sid == "add_torus":
        code = "thin_ring"
        mistake[0]["properties"]["minor_radius"] = 0.1
        error_check = check(
            "torus_dimensions",
            major_radius=1,
            minor_radius=0.1,
            major_segments=48,
            minor_segments=12,
            tolerance=0.002,
        )
        hint = "L'anneau est trop fin : garde le rayon mineur initial à 0,25 m."
    elif sid == "adjust_torus_redo":
        code = "minor_radius_unchanged"
        mistake[0]["properties"]["minor_radius"] = 0.25
        error_check = check(
            "torus_dimensions",
            major_radius=1,
            minor_radius=0.25,
            major_segments=48,
            minor_segments=12,
            tolerance=0.002,
        )
        hint = "Le petit rayon est resté à 0,25 m : saisis 0,45 m dans la dernière opération."
    elif sid == "add_subdivision":
        code = "subdivision_level_one"
        mistake[0]["properties"]["level"] = 1
        error_check = check("modifier", target="torus", type="SUBSURF", levels=1)
        hint = "Le niveau de vue vaut 1 : passe-le à 2 dans Subdivision de surface."
    elif sid == "shade_smooth":
        code = "flat_faces_remaining"
        mistake = []
        error_check = check("flat_faces", target="torus" if lesson_id == "donut" else "cube")
        hint = (
            "Des faces gardent un ombrage plat : en mode Objet, "
            "choisis Ombrage lissé sur l'objet entier."
        )
    elif sid == "proportional_tweak":
        code = "proportional_disabled"
        mistake[1]["properties"]["use_proportional_edit"] = False
        error_check = check("vertex_spike", major_radius=1, minor_radius=0.45, threshold=0.005)
        hint = "Un seul sommet fait une pointe : annule, active O et règle le rayon à 0,5 m."
    elif sid == "icing_separate":
        code = "duplicate_not_separated"
        mistake = [action for action in mistake if action.get("idname") != "MESH_OT_separate"]
        error_check = check("torus_extra_faces")
        hint = "La copie reste dans la pâte : sélectionne les faces dupliquées puis P › Sélection."
    elif sid == "solidify_icing":
        code = "icing_too_thick"
        mistake[1]["value"] = 0.1
        error_check = check(
            "modifier", target="icing", type="SOLIDIFY", thickness_min=0.09, thickness_max=0.11
        )
        hint = "Le glaçage est trop épais : remplace 0,1 m par 0,035 m dans Solidifier."
    elif sid == "donut_material":
        code = "pink_dough"
        mistake[0]["value"] = [0.8, 0.16, 0.36, 1]
        error_check = check(
            "material_color", target="torus", rgba=mistake[0]["value"], tolerance=0.01
        )
        hint = "La pâte est rose : réserve ce matériau au glaçage et mets le beige sur le donut."
    elif sid == "icing_material":
        code = "beige_icing"
        mistake[0]["value"] = [0.65, 0.36, 0.15, 1]
        error_check = check(
            "material_color", target="icing", rgba=mistake[0]["value"], tolerance=0.01
        )
        hint = "Le glaçage a la couleur de la pâte : crée son matériau rose indépendant."
    elif sid == "add_cube":
        code = "torus_instead_of_cube"
        mistake = [
            {
                "kind": "operator",
                "idname": "MESH_OT_primitive_torus_add",
                "properties": {
                    "major_segments": 48,
                    "minor_segments": 12,
                    "major_radius": 1,
                    "minor_radius": 0.25,
                },
            }
        ]
        error_check = check("object_exists", type="MESH", primitive="torus")
        hint = "Tu as créé un anneau : supprime-le et choisis Cube dans Ajouter › Maillage."
    elif sid == "add_bevel":
        code = "subdivision_instead_of_bevel"
        mistake = [
            {"kind": "operator", "idname": "OBJECT_OT_subdivision_set", "properties": {"level": 2}}
        ]
        error_check = check("modifier", target="cube", type="SUBSURF", levels=2)
        hint = "La subdivision arrondit tout le cube : annule et ajoute Biseau, pas Subdivision."
    else:
        raise ValueError(sid)
    return [{"code": code, "check": error_check, "hint": hint, "mistake_actions": mistake}]
