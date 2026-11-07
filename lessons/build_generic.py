"""Génère la leçon de tableur et son compagnon générique strict."""

import hashlib
import json
from pathlib import Path

from build_writer import author_writer
from generic_authoring import target, write

ROOT = Path(__file__).resolve().parent
FRAME = "Sans nom 1 - LibreOffice Calc"
BASE = [f"frame:{FRAME}", "panel:", "panel:", f"root pane:{FRAME}", "panel:"]
GRID = BASE + [
    "scroll pane:",
    "document spreadsheet:Sans nom 1 - Classeurs LibreOffice",
    "table:Feuille Feuille1",
]
BAR = BASE + ["tool bar:Formatage"]


def cell(name):
    return target("table cell", name, GRID, f"Cellule {name} de la première feuille")


def button(name, role="push button"):
    return target(role, name, BAR, f"Bouton {name} de la barre Formatage")


def value(name, text):
    return {"name": "element_value", "params": {"target": cell(name), "value": text}}


def visual(question):
    return {
        "name": "visual_assert",
        "params": {
            "assertion": question,
            "min_confidence": 0.8,
            "region": {"x": 0, "y": 140, "w": 250, "h": 220},
        },
    }


def click(t, modifiers=None):
    action = {"kind": "click", "target": t}
    if modifiers:
        action["modifiers"] = modifiers
    return action


def enter(name, text):
    return [click(cell(name)), {"kind": "type", "text": text}, {"kind": "key", "keys": "Return"}]


def schema():
    contract = json.loads((ROOT.parent / "contracts/lesson.schema.json").read_text())
    names = {"element_exists", "element_value", "element_state", "window_title", "visual_assert"}
    checks = [
        c
        for c in contract["$defs"]["check"]["oneOf"]
        if c["properties"]["name"].get("const") in names
    ]

    def strict(properties, required=None):
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False,
        }

    string = {"type": "string", "minLength": 1}
    action = {
        "oneOf": [
            strict(
                {
                    "kind": {"const": "click"},
                    "target": {"$ref": "#/$defs/generic_target"},
                    "modifiers": {
                        "type": "array",
                        "items": {"enum": ["shift", "ctrl", "alt"]},
                        "uniqueItems": True,
                    },
                },
                ["kind", "target"],
            ),
            strict({"kind": {"const": "key"}, "keys": string}),
            strict({"kind": {"const": "type"}, "text": string}),
        ]
    }
    actions = {"type": "array", "minItems": 1, "items": action}
    check = {"$ref": "#/$defs/check"}
    step = strict(
        {
            "goal": string,
            "help_ladder": strict({str(i): string for i in range(1, 5)}),
            "expected_actions": actions,
            "checks": {"type": "array", "items": check},
            "known_errors_extra": {
                "type": "array",
                "items": strict(
                    {"code": string, "check": check, "hint": string, "mistake_actions": actions}
                ),
            },
            "mistake_actions": {"type": "object", "additionalProperties": actions},
        }
    )
    step["properties"]["artifact_checks"] = {
        "type": "array",
        "minItems": 1,
        "items": strict(
            {
                "filename": {"type": "string", "pattern": r"^[a-z0-9-]+\.odt$"},
                "mimetype": {"const": "application/vnd.oasis.opendocument.text"},
                "heading": strict(
                    {
                        "text": string,
                        "style_name": string,
                        "outline_level": {"type": "integer", "minimum": 1, "maximum": 10},
                    }
                ),
            }
        ),
    }
    write(
        ROOT / "generic-steps.schema.json",
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Compagnon générique à entrées réelles",
            "type": "object",
            "minProperties": 1,
            "patternProperties": {"^[a-z][a-z0-9_]*$": step},
            "additionalProperties": False,
            "$defs": {
                "generic_target": contract["$defs"]["generic_target"],
                "check": {"oneOf": checks},
            },
        },
    )


def author():
    directory = ROOT / "tableur-somme"
    directory.mkdir(exist_ok=True)
    source = directory / "SOURCE.md"
    source.write_text(
        "# Source — Additionner des montants\n\n"
        "Leçon originale en français, rédigée pour LibreOffice Calc 7.3.7.\n"
        "Données fictives : 12, 30 et 8. Aucune source distante ni donnée personnelle.\n"
        "Les libellés et chemins proviennent de l'arbre AT-SPI de la version française.\n",
        encoding="utf-8",
    )
    bold = button("Gras", "toggle button")
    currency = button("Monnaie")
    specs = [
        (
            "saisir_entete",
            "Saisis Montant en A1.",
            cell("A1"),
            value("A1", "Montant"),
            [],
            enter("A1", "Montant"),
            "Un en-tête explicite donne un sens aux nombres de la colonne.",
            [
                (
                    "wrong_header",
                    value("A1", "Total"),
                    "Écris Montant, pas Total, en A1.",
                    enter("A1", "Total"),
                )
            ],
        ),
        (
            "saisir_valeurs",
            "Saisis 12 en A2, 30 en A3 et 8 en A4.",
            cell("A2"),
            value("A2", "12"),
            [value("A3", "30"), value("A4", "8")],
            enter("A2", "12") + enter("A3", "30") + enter("A4", "8"),
            "Une valeur par cellule permet de réutiliser toute la plage dans un calcul.",
            [
                (
                    "wrong_value",
                    value("A3", "3"),
                    "A3 doit contenir 30, pas 3.",
                    enter("A2", "12") + enter("A3", "3") + enter("A4", "8"),
                )
            ],
        ),
        (
            "formule_somme",
            "En A5, saisis =SOMME(A2:A4) : le résultat est 50. "
            "Dans Excel ou LibreOffice en anglais, SOMME se nomme SUM.",
            cell("A5"),
            value("A5", "50"),
            [],
            enter("A5", "=SOMME(A2:A4)"),
            "Le signe = déclenche le calcul ; A2:A4 inclut les trois montants. "
            "La fonction française SOMME correspond à SUM dans les interfaces anglaises.",
            [
                (
                    "missing_equals",
                    value("A5", "SOMME(A2:A4)"),
                    "Ajoute le signe = au début pour calculer au lieu d'afficher du texte.",
                    enter("A5", "SOMME(A2:A4)"),
                ),
                (
                    "wrong_range",
                    value("A5", "42"),
                    "Étends la plage jusqu'à A4 : les 8 doivent aussi être additionnés.",
                    enter("A5", "=SOMME(A2:A3)"),
                ),
            ],
        ),
        (
            "entete_gras",
            "Sélectionne A1 et active Gras (Ctrl+G dans Calc/Excel en français).",
            bold,
            {"name": "element_state", "params": {"target": bold, "states": ["checked"]}},
            [value("A1", "Montant")],
            [click(cell("A1")), {"kind": "key", "keys": "ctrl+g"}],
            "Le gras distingue l'en-tête des données ; "
            "vérifie la cellule sélectionnée avant le geste.",
            [
                (
                    "wrong_bold_cell",
                    {
                        "name": "element_state",
                        "params": {"target": bold, "absent_states": ["checked"]},
                    },
                    "Le gras concerne A1, pas A2. Sélectionne l'en-tête avant Ctrl+G.",
                    [click(cell("A2")), {"kind": "key", "keys": "ctrl+g"}, click(cell("A1"))],
                )
            ],
        ),
        (
            "format_monetaire",
            "Sélectionne A2:A5 puis le bouton Monnaie de Formatage "
            "(Format monétaire) : A5 doit afficher 50,00 €.",
            currency,
            visual(
                "La cellule A5 affiche-t-elle exactement 50,00 € "
                "avec deux décimales et un symbole € ?"
            ),
            [
                visual(
                    f"La cellule {name} affiche-t-elle exactement {amount},00 € "
                    "avec deux décimales et un symbole € ?"
                )
                for name, amount in [("A2", "12"), ("A3", "30"), ("A4", "8")]
            ]
            + [value("A5", "50")],
            [click(cell("A2")), click(cell("A5"), ["shift"]), click(currency)],
            "Le format monétaire change l'affichage, pas la somme : "
            "applique-le aux quatre cellules.",
            [
                (
                    "only_total_formatted",
                    visual(
                        "La cellule A2 affiche-t-elle exactement 12 sans aucune décimale "
                        "et sans symbole € ?"
                    ),
                    "Sélectionne toute la plage A2:A5, pas seulement le total.",
                    [click(cell("A5")), click(currency)],
                )
            ],
        ),
    ]
    steps, sidecar = [], {}
    hints = {
        "saisir_entete": "Repère A1, à l'intersection de la colonne A et de la ligne 1 ; "
        "saisis Montant puis Entrée.",
        "saisir_valeurs": "Repère les trois cellules sous Montant : A2 = 12, A3 = 30, A4 = 8.",
        "formule_somme": "Repère A5 sous les trois montants ; commence par = puis "
        "SOMME(A2:A4), sans oublier A4.",
        "entete_gras": "Repère A1 puis le bouton Gras dans Formatage ; Ctrl+G agit "
        "sur la cellule sélectionnée.",
        "format_monetaire": "Repère A2:A5 puis Monnaie dans Formatage ; sélectionne "
        "les quatre cellules avant de cliquer.",
    }
    for sid, instruction, t, check, checks, actions, why, errors in specs:
        steps.append(
            {
                "id": sid,
                "skill_id": sid,
                "instruction": instruction,
                "preconditions": {"window_title": FRAME},
                "target": t,
                "check": check,
                "why": why,
                "audio_ref": None,
                "known_errors": [
                    {"code": code, "check": c, "hint": hint} for code, c, hint, _ in errors
                ],
                "procedure_ref": f"tableur-somme/{sid}",
                "proof": {
                    "status": "draft",
                    "method": "accessibility",
                    "evidence_ref": f"proof/{sid}.json",
                    "ui_path_verified": False,
                },
            }
        )
        sidecar[sid] = {
            "goal": instruction,
            "help_ladder": {
                "1": f"① Voix : {instruction}",
                "2": "② Surlignage et menu : " + hints[sid],
                "3": f"③ Pointeur : suis le repère sur {t['description']}, puis fais le geste.",
                "4": "④ Démo : avec ton accord, je rejoue cette étape dans une copie, "
                "puis tu recommences sans aide.",
            },
            "expected_actions": actions,
            "checks": checks,
            "known_errors_extra": [],
            "mistake_actions": {code: a for code, _, _, a in errors},
        }
    write(
        directory / "lesson.json",
        {
            "schema_version": "2.0",
            "lesson_id": "tableur-somme",
            "revision": 1,
            "title": "Additionner et présenter des montants",
            "language": "fr-FR",
            "app": {
                "id": "libreoffice-calc",
                "name": "LibreOffice Calc",
                "version": "7.3.7",
                "sensor": "auto",
            },
            "status": "draft",
            "source": {
                "uri": "authored://lessons/tableur-somme/SOURCE.md",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            },
            "skills": [s["skill_id"] for s in steps],
            "steps": steps,
            "proof": {
                "method": "per_step",
                "evidence_ref": "proof/manifest.json",
                "ui_path_verified": False,
            },
        },
    )
    write(directory / "steps.json", sidecar)
    print("tableur-somme: revision 1, draft; real proof required")


if __name__ == "__main__":
    schema()
    author()
    author_writer()
