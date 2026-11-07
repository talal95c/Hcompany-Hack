"""Leçon originale de rédaction, utilisant le contrat et le compagnon communs."""

import hashlib
from pathlib import Path

from generic_authoring import target, write

ROOT = Path(__file__).resolve().parent
FRAME = "Sans nom 1 - LibreOffice Writer"
BASE = [f"frame:{FRAME}", "panel:", "panel:", f"root pane:{FRAME}", "panel:"]
DOCUMENT = BASE + ["scroll pane:"]
STYLE = BASE + [
    "tool bar:Formatage",
    "panel:Style de paragraphe",
    "panel:",
    "filler:",
    "panel:",
    "panel:",
    "filler:",
    "filler:",
]


def key(keys):
    return {"kind": "key", "keys": keys}


def typing(text):
    return {"kind": "type", "text": text}


def save(filename):
    return [
        key("ctrl+shift+s"),
        key("ctrl+l"),
        typing("{output_dir}/" + filename),
        key("Return"),
        key("Return"),
        key("ctrl+s"),
    ]


def author_writer():
    directory = ROOT / "texte-titre"
    directory.mkdir(exist_ok=True)
    source = directory / "SOURCE.md"
    source.write_text(
        "# Source — Un titre structuré\n\n"
        "Leçon originale française pour Writer 7.3.7.\n"
        "Texte fictif : Rapport mensuel. Aucune donnée personnelle.\n"
        "Cibles relevées sur l'arbre AT-SPI français réel.\n",
        encoding="utf-8",
    )
    document = target(
        "document text",
        "Sans nom 1 - Document LibreOffice",
        DOCUMENT,
        "Document de rédaction vierge",
    )
    paragraph = {
        "description": "Unique paragraphe du document encore sans style de titre",
        "role": "paragraph",
        "path": DOCUMENT + ["document text:" + document["name"]],
        "app_region": DOCUMENT[-1],
    }
    style = {
        "description": "Texte du sélecteur Style de paragraphe de Formatage",
        "role": "text",
        "path": STYLE,
        "app_region": "panel:Style de paragraphe",
    }
    save_button = target(
        "push button",
        "Enregistrer sous...",
        BASE + ["tool bar:Standard"],
        "Commande Enregistrer sous de la barre Standard",
    )

    def value(t, text):
        return {"name": "element_value", "params": {"target": t, "value": text, "timeout_ms": 2000}}

    def title(filename):
        return {"name": "window_title", "params": {"value": filename}}

    specs = [
        (
            "type_title",
            "Saisis Rapport mensuel dans le document vierge.",
            document,
            value(paragraph, "Rapport mensuel"),
            [typing("Rapport mensuel")],
            "Un intitulé explicite situe le document avant toute mise en forme.",
            [
                (
                    "wrong_title",
                    value(paragraph, "Brouillon"),
                    "Remplace Brouillon par Rapport mensuel.",
                    [typing("Brouillon")],
                )
            ],
        ),
        (
            "apply_heading",
            "Place le curseur dans le titre et applique Titre 1 avec Ctrl+1.",
            style,
            value(style, "Titre 1"),
            [key("ctrl+Home"), key("ctrl+1")],
            "Un style de titre crée une structure navigable ; le gras seul ne crée pas de section.",
            [
                (
                    "bold_only",
                    {
                        "name": "visual_assert",
                        "params": {
                            "assertion": "Le texte Rapport mensuel est-il en gras ET le "
                            "sélecteur de style en haut à gauche affiche-t-il « Style de "
                            "paragraphe » (libellé tronqué), et NON « Titre 1 » ?",
                            "region": {"x": 0, "y": 0, "w": 750, "h": 400},
                            "min_confidence": 0.8,
                        },
                    },
                    "Utilise Ctrl+1 : le gras seul ne suffit pas.",
                    [key("ctrl+Home"), key("ctrl+shift+End"), key("ctrl+g"), key("ctrl+Home")],
                ),
                (
                    "wrong_paragraph",
                    value(
                        {
                            **paragraph,
                            "role": "heading",
                            "description": "Paragraphe de corps devenu titre "
                            "au lieu du premier paragraphe",
                        },
                        "Corps du rapport.",
                    ),
                    "Applique Titre 1 au premier paragraphe, pas à la ligne suivante.",
                    [
                        key("ctrl+End"),
                        key("Return"),
                        typing("Corps du rapport."),
                        key("ctrl+1"),
                        key("ctrl+Home"),
                    ],
                ),
            ],
        ),
        (
            "save_document",
            "Enregistre sous rapport-mensuel.odt avec Ctrl+Maj+S. "
            "Garde le format Texte ODF (.odt).",
            save_button,
            title("rapport-mensuel.odt"),
            save("rapport-mensuel.odt"),
            "Le nom identifie le livrable ; ODT conserve la structure de titre, "
            "pas seulement son aspect.",
            [
                (
                    "wrong_filename",
                    title("brouillon.odt"),
                    "Enregistre le fichier sous le nom exact rapport-mensuel.odt.",
                    save("brouillon.odt"),
                )
            ],
        ),
    ]
    steps, companion = [], {}
    hints = {
        "type_title": "Repère la page blanche et saisis Rapport mensuel sur la première ligne.",
        "apply_heading": "Repère Style de paragraphe dans Formatage ; Ctrl+Début puis Ctrl+1 "
        "doit y afficher Titre 1.",
        "save_document": "Ouvre Fichier › Enregistrer sous ; indique rapport-mensuel.odt "
        "et conserve Texte ODF.",
    }
    for sid, instruction, t, check, actions, why, errors in specs:
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
                "procedure_ref": "texte-titre/" + sid,
                "proof": {
                    "status": "draft",
                    "method": "accessibility",
                    "evidence_ref": f"proof/{sid}.json",
                    "ui_path_verified": False,
                },
            }
        )
        companion[sid] = {
            "goal": instruction,
            "help_ladder": {
                "1": "① Voix : " + instruction,
                "2": "② Surlignage et menu : " + hints[sid],
                "3": "③ Pointeur : suis le repère, puis effectue le geste toi-même.",
                "4": "④ Démo : avec ton accord, je montre ce geste dans une copie, "
                "puis tu le refais.",
            },
            "expected_actions": actions,
            "checks": [],
            "known_errors_extra": [],
            "mistake_actions": {code: a for code, _, _, a in errors},
        }
    companion["save_document"]["artifact_checks"] = [
        {
            "filename": "rapport-mensuel.odt",
            "mimetype": "application/vnd.oasis.opendocument.text",
            "heading": {
                "text": "Rapport mensuel",
                "outline_level": 1,
                "style_name": "Heading_20_1",
            },
        }
    ]
    write(
        directory / "lesson.json",
        {
            "schema_version": "2.0",
            "lesson_id": "texte-titre",
            "revision": 1,
            "title": "Rédiger et enregistrer un titre structuré",
            "language": "fr-FR",
            "app": {
                "id": "libreoffice-writer",
                "name": "LibreOffice Writer",
                "version": "7.3.7",
                "sensor": "auto",
            },
            "status": "draft",
            "source": {
                "uri": "authored://lessons/texte-titre/SOURCE.md",
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
    write(directory / "steps.json", companion)
    print("texte-titre: revision 1, draft; real proof required")
