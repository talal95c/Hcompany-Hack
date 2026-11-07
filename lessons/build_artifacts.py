"""Écriture reproductible des leçons rédigées et du schéma compagnon."""

import hashlib
import json
from pathlib import Path
from typing import Any

from error_cases import errors
from pedagogy import CONTENT

ROOT = Path(__file__).resolve().parent
MENU_IDS = {
    "add_torus": "VIEW3D_MT_mesh_add",
    "add_cube": "VIEW3D_MT_mesh_add",
    "adjust_torus_redo": "TOPBAR_MT_edit",
    "add_subdivision": "OBJECT_MT_modifier_add_generate",
    "add_bevel": "OBJECT_MT_modifier_add_generate",
    "shade_smooth": "VIEW3D_MT_object_shading",
    "proportional_tweak": "VIEW3D_MT_transform",
    "icing_separate": "VIEW3D_MT_edit_mesh",
    "solidify_icing": "OBJECT_MT_modifier_add_generate",
}


def write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def check(name: str, **params: Any) -> dict:
    return {"name": name, "params": params}


def op(idname: str, **properties: Any) -> dict:
    return {"kind": "operator", "idname": idname, "properties": properties}


def prop(target: str, path: str, value: Any) -> dict:
    return {"kind": "property", "target": target, "path": path, "value": value}


def strict(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
        "additionalProperties": False,
    }


def schema() -> None:
    string = {"type": "string", "minLength": 1}
    number = {"type": "number"}
    integer = {"type": "integer", "minimum": 1}
    role = {"enum": ["torus", "icing", "cube"]}
    rgba = {"type": "array", "items": number, "minItems": 4, "maxItems": 4}
    variants = []
    definitions = {
        "object_exists": {"type": {"const": "MESH"}, "primitive": {"enum": ["torus", "cube"]}},
        "torus_dimensions": {
            "major_radius": number,
            "minor_radius": number,
            "major_segments": integer,
            "minor_segments": integer,
            "tolerance": number,
        },
        "modifier": {
            "target": role,
            "type": {"enum": ["SUBSURF", "SOLIDIFY", "BEVEL"]},
            "levels": integer,
            "thickness_min": number,
            "thickness_max": number,
        },
        "shade_smooth": {"target": role},
        "flat_faces": {"target": role},
        "vertex_spike": {"major_radius": number, "minor_radius": number, "threshold": number},
        "torus_extra_faces": {},
        "mesh_deformed": {"major_radius": number, "minor_radius": number, "threshold": number},
        "derived_part": {"fraction_min": number, "fraction_max": number, "epsilon": number},
        "material_color": {"target": role, "rgba": rgba, "tolerance": number},
    }
    for name, params in definitions.items():
        if name == "modifier":
            for modifier_type, fields in {
                "SUBSURF": {"levels": integer},
                "SOLIDIFY": {"thickness_min": number, "thickness_max": number},
                "BEVEL": {},
            }.items():
                variants.append(
                    strict(
                        {
                            "name": {"const": name},
                            "params": strict(
                                {"target": role, "type": {"const": modifier_type}, **fields}
                            ),
                        }
                    )
                )
        else:
            variants.append(strict({"name": {"const": name}, "params": strict(params)}))
    check_schema = {"oneOf": variants}
    operators = {
        "MESH_OT_primitive_torus_add": {
            "major_segments": integer,
            "minor_segments": integer,
            "major_radius": number,
            "minor_radius": number,
        },
        "MESH_OT_primitive_cube_add": {"size": number},
        "OBJECT_OT_mode_set": {"mode": {"enum": ["OBJECT", "EDIT"]}},
        "OBJECT_OT_subdivision_set": {"level": integer},
        "OBJECT_OT_shade_smooth": {},
        "OBJECT_OT_modifier_add": {"type": {"enum": ["SOLIDIFY", "BEVEL", "SUBSURF"]}},
        "TRANSFORM_OT_translate": {
            "value": {"type": "array", "items": number, "minItems": 3, "maxItems": 3},
            "use_proportional_edit": {"type": "boolean"},
            "proportional_size": number,
            "proportional_edit_falloff": {"const": "SMOOTH"},
        },
        "MESH_OT_duplicate": {},
        "MESH_OT_separate": {"type": {"const": "SELECTED"}},
    }
    actions = [
        strict({"kind": {"const": kind}, "idname": {"const": name}, "properties": strict(params)})
        for name, params in operators.items()
        for kind in (
            ["operator", "redo"] if name == "MESH_OT_primitive_torus_add" else ["operator"]
        )
    ]
    actions.extend(
        [
            strict(
                {
                    "kind": {"const": "property"},
                    "target": role,
                    "path": {"const": 'modifiers["Solidify"].thickness'},
                    "value": number,
                }
            ),
            strict(
                {
                    "kind": {"const": "property"},
                    "target": role,
                    "path": {"const": "material.base_color"},
                    "value": rgba,
                }
            ),
            strict(
                {
                    "kind": {"const": "select"},
                    "target": role,
                    "rule": {
                        "oneOf": [
                            strict({"vertex": {"const": "max_x"}}),
                            strict({"faces_z_above": number}),
                        ]
                    },
                }
            ),
        ]
    )
    step = strict(
        {
            "goal": string,
            "help_ladder": strict({str(i): string for i in range(1, 5)}),
            "expected_actions": {"type": "array", "minItems": 1, "items": {"oneOf": actions}},
            "checks": {"type": "array", "items": check_schema},
            "known_errors_extra": {
                "type": "array",
                "items": strict(
                    {
                        "code": string,
                        "check": check_schema,
                        "hint": string,
                        "mistake_actions": {"type": "array", "items": {"oneOf": actions}},
                    }
                ),
            },
        }
    )
    write(
        ROOT / "steps.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Compagnon de leçon",
            "type": "object",
            "minProperties": 1,
            "patternProperties": {"^[a-z][a-z0-9_]*$": step},
            "additionalProperties": False,
        },
    )


def author() -> None:
    torus = check("object_exists", type="MESH", primitive="torus")
    cube = check("object_exists", type="MESH", primitive="cube")
    mode_object = op("OBJECT_OT_mode_set", mode="OBJECT")
    specs = [
        (
            "add_torus",
            "Ajouter › Maillage › Tore",
            "Ajoute un tore de 48 × 12 segments.",
            [
                op(
                    "MESH_OT_primitive_torus_add",
                    major_segments=48,
                    minor_segments=12,
                    major_radius=1.0,
                    minor_radius=0.25,
                )
            ],
            [],
            "OBJECT",
        ),
        (
            "adjust_torus_redo",
            "Édition › Ajuster la dernière opération",
            "Dans le panneau de dernière opération, règle les rayons à 1 m et 0,45 m.",
            [
                {
                    "kind": "redo",
                    "idname": "MESH_OT_primitive_torus_add",
                    "properties": {
                        "major_segments": 48,
                        "minor_segments": 12,
                        "major_radius": 1.0,
                        "minor_radius": 0.45,
                    },
                }
            ],
            [
                check(
                    "torus_dimensions",
                    major_radius=1.0,
                    minor_radius=0.45,
                    major_segments=48,
                    minor_segments=12,
                    tolerance=0.002,
                )
            ],
            "OBJECT",
        ),
        (
            "add_subdivision",
            "Objet › Subdivision › Niveau 2",
            "Ajoute une subdivision de surface de niveau 2.",
            [op("OBJECT_OT_subdivision_set", level=2)],
            [check("modifier", target="torus", type="SUBSURF", levels=2)],
            "OBJECT",
        ),
        (
            "shade_smooth",
            "Objet › Ombrage lissé",
            "Lisse toutes les faces du donut.",
            [op("OBJECT_OT_shade_smooth")],
            [check("shade_smooth", target="torus")],
            "OBJECT",
        ),
        (
            "proportional_tweak",
            "Maillage › Transformer › Déplacer",
            "En mode Édition, déplace un sommet de 0,12 m en Z avec édition proportionnelle, "
            "rayon 0,5 m.",
            [
                {"kind": "select", "target": "torus", "rule": {"vertex": "max_x"}},
                op(
                    "TRANSFORM_OT_translate",
                    value=[0, 0, 0.12],
                    use_proportional_edit=True,
                    proportional_size=0.5,
                    proportional_edit_falloff="SMOOTH",
                ),
                mode_object,
            ],
            [check("mesh_deformed", major_radius=1.0, minor_radius=0.45, threshold=0.005)],
            "EDIT",
        ),
        (
            "icing_separate",
            "Maillage › Dupliquer puis Séparer › Sélection",
            "Sélectionne les faces supérieures, duplique-les puis sépare-les "
            "pour former le glaçage.",
            [
                {"kind": "select", "target": "torus", "rule": {"faces_z_above": 0.0}},
                op("MESH_OT_duplicate"),
                op("MESH_OT_separate", type="SELECTED"),
                mode_object,
            ],
            [check("derived_part", fraction_min=0.3, fraction_max=0.7, epsilon=0.00001)],
            "EDIT",
        ),
        (
            "solidify_icing",
            "Modificateurs › Ajouter › Générer › Solidifier",
            "Ajoute au glaçage Solidifier avec une épaisseur de 0,035 m.",
            [
                op("OBJECT_OT_modifier_add", type="SOLIDIFY"),
                prop("icing", 'modifiers["Solidify"].thickness', 0.035),
            ],
            [
                check(
                    "modifier",
                    target="icing",
                    type="SOLIDIFY",
                    thickness_min=0.025,
                    thickness_max=0.05,
                )
            ],
            "OBJECT",
        ),
        (
            "donut_material",
            "Propriétés › Matériau › Surface › Couleur de base",
            "Crée un matériau beige pour la pâte (RGBA : 0,65 ; 0,36 ; 0,15 ; 1).",
            [prop("torus", "material.base_color", [0.65, 0.36, 0.15, 1.0])],
            [check("material_color", target="torus", rgba=[0.65, 0.36, 0.15, 1.0], tolerance=0.01)],
            "OBJECT",
        ),
        (
            "icing_material",
            "Propriétés › Matériau › Surface › Couleur de base",
            "Crée un matériau rose pour le glaçage (RGBA : 0,8 ; 0,16 ; 0,36 ; 1).",
            [prop("icing", "material.base_color", [0.8, 0.16, 0.36, 1.0])],
            [check("material_color", target="icing", rgba=[0.8, 0.16, 0.36, 1.0], tolerance=0.01)],
            "OBJECT",
        ),
    ]
    mini = [
        (
            "add_cube",
            "Ajouter › Maillage › Cube",
            "Ajoute un cube de 2 m.",
            [op("MESH_OT_primitive_cube_add", size=2)],
            [],
            "OBJECT",
        ),
        (
            "add_bevel",
            "Modificateurs › Ajouter › Générer › Biseau",
            "Ajoute un modificateur Biseau au cube.",
            [op("OBJECT_OT_modifier_add", type="BEVEL")],
            [check("modifier", target="cube", type="BEVEL")],
            "OBJECT",
        ),
        (
            "shade_smooth",
            "Objet › Ombrage lissé",
            "Lisse toutes les faces du cube.",
            [op("OBJECT_OT_shade_smooth")],
            [check("shade_smooth", target="cube")],
            "OBJECT",
        ),
    ]
    for lesson_id, title, entries, subject in [
        ("donut", "Mon premier donut", specs, torus),
        ("mini-cube", "Un cube en trois étapes", mini, cube),
    ]:
        directory = ROOT / lesson_id
        source = directory / "SOURCE.md"
        source.write_text(
            f"# Source — {title}\n\n"
            "Leçon originale rédigée dans le style du tutoriel débutant classique "
            "Blender Guru donut, partie 1 : gestes simples et progression guidée. "
            "Aucun contenu vidéo n'a été copié. Les droits d'usage et les références "
            "à la marque restent à vérifier avant diffusion.\n",
            encoding="utf-8",
        )
        steps = []
        companion = {}
        for index, (sid, menu, instruction, actions, checks, mode) in enumerate(entries):
            why, ladder = CONTENT[lesson_id][sid]
            if sid == "add_torus":
                checks = [
                    check(
                        "torus_dimensions",
                        major_radius=1.0,
                        minor_radius=0.25,
                        major_segments=48,
                        minor_segments=12,
                        tolerance=0.002,
                    )
                ]
            preconditions = {"mode": mode}
            if index == 0:
                preconditions["scene"] = "empty"
            else:
                preconditions["active"] = (
                    "icing"
                    if sid in {"solidify_icing", "icing_material"}
                    else ("torus" if lesson_id == "donut" else "cube")
                )
            steps.append(
                {
                    "id": sid,
                    "skill_id": sid,
                    "instruction": instruction,
                    "preconditions": preconditions,
                    "check": subject,
                    "target": {
                        "description": menu,
                        "area_type": "VIEW_3D",
                        "region_type": "WINDOW",
                    },
                    "why": why,
                    "audio_ref": None,
                    "known_errors": (
                        [
                            {
                                "code": "cube_instead_of_torus",
                                "check": cube,
                                "hint": "Supprime le cube et choisis Ajouter › Maillage › Tore.",
                            }
                        ]
                        if lesson_id == "donut" and sid == "add_torus"
                        else []
                    ),
                    "procedure_ref": f"{lesson_id}/{sid}",
                    "proof": {
                        "status": "proven",
                        "method": "bpy",
                        "evidence_ref": f"proof/{sid}.json",
                        "ui_path_verified": False,
                    },
                }
            )
            companion[sid] = {
                "goal": instruction,
                "help_ladder": {str(i): text for i, text in enumerate(ladder, start=1)},
                "expected_actions": actions,
                "checks": checks,
                "known_errors_extra": errors(lesson_id, sid, actions),
            }
            if sid in MENU_IDS:
                steps[-1]["help"] = {"menu_id": MENU_IDS[sid]}
        write(
            directory / "lesson.json",
            {
                "schema_version": "2.0",
                "lesson_id": lesson_id,
                "revision": 2,
                "title": title,
                "language": "fr-FR",
                "blender_version": "4.5.9",
                "app": {
                    "id": "blender",
                    "name": "Blender",
                    "version": "4.5.9",
                    "sensor": "addon",
                },
                "status": "proven",
                "source": {
                    "uri": f"authored://lessons/{lesson_id}/SOURCE.md",
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                },
                "skills": [entry[0] for entry in entries],
                "steps": steps,
                "proof": {
                    "method": "per_step",
                    "evidence_ref": "proof/manifest.json",
                    "ui_path_verified": False,
                },
            },
        )
        write(directory / "steps.json", companion)


if __name__ == "__main__":
    author()
    schema()
