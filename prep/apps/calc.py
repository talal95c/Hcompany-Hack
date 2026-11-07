"""Adaptateur Calc : résultats du document ODS, jamais état d'un bouton du ruban."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from decimal import Decimal, InvalidOperation
from typing import Any

from prep.ui_map.accessibility import find_nodes

CHECKS = ("calc.cell_formula", "calc.range_bold", "calc.chart_source")
SPECS = {
    "calc.cell_formula": "{sheet: nom exact, cell: B6, formula: '=SUM(B2:B5)', value: nombre}",
    "calc.range_bold": "{sheet: nom exact, range: 'A1:B1', bold?: bool=true}; CHAQUE cellule",
    "calc.chart_source": "{sheet: nom exact, range: 'A1:B5'}; plage exacte du graphique enregistré",
}
COMPILER_RULES = (
    "Pour Calc, vérifie les RÉSULTATS dans le document avec les checks calc.* : "
    "calc.cell_formula pour une formule ET sa valeur, calc.range_bold pour TOUTES les cellules "
    "de l'en-tête, calc.chart_source pour la plage source EXACTE du graphique. "
    "Jamais l'état du bouton Gras, jamais une simple présence visuelle du graphique. "
    "sheet est le nom réel de la feuille, visible dans la carte (table:Sheet ventes signifie "
    "sheet ventes). L'instruction doit nommer les cellules/plages exactes du tutoriel. "
    "L'adaptateur sélectionne cette plage dans la zone de nom AVANT le premier geste Holo. "
)
CELL = re.compile(r"^([A-Z]{1,3})([1-9][0-9]{0,6})$")
NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "chart": "urn:oasis:names:tc:opendocument:xmlns:chart:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
}


def attr(element: ET.Element, prefix: str, name: str, default: str = "") -> str:
    return element.get(f"{{{NS[prefix]}}}{name}", default)


def position(cell: str) -> tuple[int, int]:
    match = CELL.fullmatch(cell)
    if not match:
        raise ValueError("Référence de cellule invalide")
    column = 0
    for char in match[1]:
        column = column * 26 + ord(char) - ord("A") + 1
    return int(match[2]), column


def area(value: str) -> tuple[int, int, int, int]:
    first, last = value.split(":")
    row, col = position(first)
    end_row, end_col = position(last)
    if end_row < row or end_col < col or (end_row - row + 1) * (end_col - col + 1) > 10000:
        raise ValueError("Plage non prise en charge")
    return row, col, end_row, end_col


def formula(value: str) -> str:
    value = re.sub(r"^[A-Za-z0-9_]+:=", "=", value)
    return re.sub(r"\s+", "", value.replace("[.", "").replace(":.", ":").replace("]", "")).upper()


class Document:
    def __init__(self, data: bytes):
        self.archive = zipfile.ZipFile(io.BytesIO(data))
        self.content = ET.fromstring(self.archive.read("content.xml"))
        self.styles = ET.fromstring(self.archive.read("styles.xml"))
        self.named_styles = {
            attr(style, "style", "name"): style
            for root in (self.styles, self.content)
            for style in root.findall(".//style:style", NS)
        }

    def sheet(self, name: str) -> ET.Element:
        matches = [
            table
            for table in self.content.findall(".//office:spreadsheet/table:table", NS)
            if attr(table, "table", "name") == name
        ]
        if len(matches) != 1:
            raise ValueError("Feuille absente ou ambiguë")
        return matches[0]

    def cell(self, sheet: ET.Element, row: int, col: int) -> tuple[ET.Element, str]:
        row_index = 1
        column_style = ""
        column_index = 1
        for column in sheet.findall("table:table-column", NS):
            count = int(attr(column, "table", "number-columns-repeated", "1"))
            if column_index <= col < column_index + count:
                column_style = attr(column, "table", "default-cell-style-name")
                break
            column_index += count
        for line in sheet.findall("table:table-row", NS):
            count = int(attr(line, "table", "number-rows-repeated", "1"))
            if row_index <= row < row_index + count:
                col_index = 1
                for cell in line:
                    if cell.tag not in {
                        f"{{{NS['table']}}}table-cell",
                        f"{{{NS['table']}}}covered-table-cell",
                    }:
                        continue
                    repeated = int(attr(cell, "table", "number-columns-repeated", "1"))
                    if col_index <= col < col_index + repeated:
                        style = (
                            attr(cell, "table", "style-name")
                            or attr(line, "table", "default-cell-style-name")
                            or column_style
                        )
                        return cell, style
                    col_index += repeated
                break
            row_index += count
        return ET.Element(f"{{{NS['table']}}}table-cell"), column_style

    def weight(self, name: str, seen: frozenset[str] = frozenset()) -> str:
        if not name:
            defaults = self.styles.findall(".//style:default-style", NS)
            default = next(
                (s for s in defaults if attr(s, "style", "family") == "table-cell"), None
            )
            props = default.find("style:text-properties", NS) if default is not None else None
            return attr(props, "fo", "font-weight", "normal") if props is not None else "normal"
        if name in seen or name not in self.named_styles:
            raise ValueError("Style inconnu ou cyclique")
        style = self.named_styles[name]
        props = style.find("style:text-properties", NS)
        if props is not None and attr(props, "fo", "font-weight"):
            return attr(props, "fo", "font-weight")
        return self.weight(attr(style, "style", "parent-style-name"), seen | {name})

    def bold(self, cell: ET.Element, style: str) -> bool:
        weights = [self.weight(style)]
        for span in cell.findall(".//text:span", NS):
            if attr(span, "text", "style-name"):
                weights.append(self.weight(attr(span, "text", "style-name")))
        return all(w == "bold" or (w.isdigit() and int(w) >= 700) for w in weights)

    def chart_ranges(self, sheet: ET.Element) -> list[str]:
        ranges = []
        for obj in sheet.findall(".//draw:object", NS):
            href = attr(obj, "xlink", "href").removeprefix("./")
            if not href or ".." in href.split("/"):
                raise ValueError("Objet incorporé invalide")
            root = ET.fromstring(self.archive.read(f"{href}/content.xml"))
            for chart in root.findall(".//chart:chart", NS):
                plot = chart.find("chart:plot-area", NS)
                if plot is None or not attr(plot, "table", "cell-range-address"):
                    raise ValueError("Source du graphique non exposée")
                ranges.append(attr(plot, "table", "cell-range-address"))
        return ranges


def evaluate_document(check: dict[str, Any], data: bytes) -> dict[str, Any]:
    try:
        document = Document(data)
        params = check["params"]
        sheet = document.sheet(params["sheet"])
        if check["name"] == "calc.cell_formula":
            cell, _ = document.cell(sheet, *position(params["cell"]))
            actual_formula = attr(cell, "table", "formula")
            actual_value = attr(cell, "office", "value")
            ok = (
                formula(actual_formula) == formula(params["formula"])
                and bool(actual_value)
                and Decimal(actual_value) == Decimal(str(params["value"]))
            )
            evidence = {"cell": params["cell"], "formula": actual_formula, "value": actual_value}
        elif check["name"] == "calc.range_bold":
            row, col, end_row, end_col = area(params["range"])
            weights = [
                document.bold(*document.cell(sheet, r, c))
                for r in range(row, end_row + 1)
                for c in range(col, end_col + 1)
            ]
            ok = all(w == params.get("bold", True) for w in weights)
            evidence = {"range": params["range"], "bold_cells": weights}
        elif check["name"] == "calc.chart_source":
            area(params["range"])
            ranges = document.chart_ranges(sheet)
            if len(ranges) > 1:
                raise ValueError("Graphique ambigu")
            expected_start, expected_end = params["range"].split(":")
            expected = f"{params['sheet']}.{expected_start}:{params['sheet']}.{expected_end}"
            actual = ranges[0].replace("$", "").replace("'", "") if ranges else ""
            actual = actual.replace(":.", f":{params['sheet']}.")
            ok = actual == expected
            evidence = {"source_ranges": ranges, "expected_range": expected}
        else:
            return {"result": "unknown", "reason": "Check Calc non autorisé"}
        return {"result": "pass" if ok else "fail", "sensor": "document", **evidence}
    except (ValueError, KeyError, InvalidOperation, ET.ParseError, zipfile.BadZipFile) as exc:
        return {"result": "unknown", "sensor": "document", "reason": str(exc)}


class CalcAdapter:
    checks = CHECKS
    specs = SPECS
    compiler_rules = COMPILER_RULES

    @staticmethod
    def validate_success(check: dict[str, Any], ui_map: dict) -> None:
        if check.get("name") not in CHECKS:
            raise ValueError(
                "Calc exige un check de résultat calc.*, pas un état de toolbar/vision"
            )
        sheets = CalcAdapter.sheet_names(ui_map)
        if sheets and check.get("params", {}).get("sheet") not in sheets:
            raise ValueError("Nom de feuille absent de la carte d'accessibilité")

    @staticmethod
    def sheet_names(ui_map: dict) -> list[str]:
        return [
            node["name"].removeprefix("Sheet ")
            for node in ui_map.get("managed_containers", [])
            if node["role"] == "table"
        ]

    @staticmethod
    def compiler_context(ui_map: dict) -> str:
        return "\nNoms EXACTS des feuilles pour params.sheet (ne pas inventer Sheet1) : " + repr(
            CalcAdapter.sheet_names(ui_map)
        )

    def __init__(self, sandbox: Any):
        self.sandbox = sandbox

    async def evaluate(self, check: dict[str, Any]) -> dict[str, Any]:
        if check.get("name") not in self.checks:
            return {"result": "unknown", "reason": "Check Calc non autorisé"}
        return evaluate_document(check, await self.sandbox.document_snapshot())

    async def prepare_step(self, check: dict[str, Any]) -> str:
        params = check["params"]
        selection = params.get("cell") or params["range"]
        snapshot = await self.sandbox.snapshot()
        nodes = self.name_boxes(snapshot)
        if not snapshot.get("complete") or snapshot.get("error") or len(nodes) != 1:
            raise RuntimeError("Zone de nom indisponible ou ambiguë")
        await self.sandbox.focus_text(ancestor_role="tool bar", ancestor_name="Formula Tool Bar")
        await self.sandbox.key(["ctrl", "a"])
        await self.sandbox.type_text(f"'{params['sheet']}'.{selection}")
        await self.sandbox.key(["enter"])
        selected = await self.sandbox.snapshot()
        boxes = self.name_boxes(selected)
        if (
            not selected.get("complete")
            or selected.get("error")
            or len(boxes) != 1
            or boxes[0].get("value") != selection
        ):
            raise RuntimeError("Sélection de la plage non confirmée par la zone de nom")
        return (
            f"The exact target {params['sheet']}.{selection} is already selected in the Name Box. "
            "Keep this selection; apply the operation, finish any wizard, then call done. "
            "Do not select another cell/range or change the chart's data range."
        )

    @staticmethod
    def name_boxes(snapshot: dict[str, Any]) -> list[dict]:
        return [
            node
            for node in find_nodes(snapshot, {"role": "text", "path": ["toolbar:Formula Tool Bar"]})
            if "editable" in node.get("states", [])
            and re.fullmatch(r"[A-Z]+[0-9]+(?::[A-Z]+[0-9]+)?", node.get("value", ""))
        ]
