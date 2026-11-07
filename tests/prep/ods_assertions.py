"""Lecture indépendante des sorties ODS pour la recette (sans le vérificateur produit)."""

import xml.etree.ElementTree as ET
from zipfile import ZipFile

NAMESPACES = {
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
    "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    "chart": "urn:oasis:names:tc:opendocument:xmlns:chart:1.0",
    "draw": "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0",
    "xlink": "http://www.w3.org/1999/xlink",
}


def q(prefix, name):
    return f"{{{NAMESPACES[prefix]}}}{name}"


def assert_tutorial_ods(path):
    with ZipFile(path) as archive:
        content = ET.fromstring(archive.read("content.xml"))
        styles = ET.fromstring(archive.read("styles.xml"))
        sheet = content.find(".//table:table[@table:name='ventes']", NAMESPACES)
        assert sheet is not None
        cells = {}
        row_index = 1
        for row in sheet.findall("table:table-row", NAMESPACES):
            row_repeat = int(row.get(q("table", "number-rows-repeated"), "1"))
            column_index = 1
            for cell in row:
                if cell.tag not in {q("table", "table-cell"), q("table", "covered-table-cell")}:
                    continue
                repeat = int(cell.get(q("table", "number-columns-repeated"), "1"))
                for r in range(row_index, min(row_index + row_repeat, 7)):
                    for c in range(column_index, min(column_index + repeat, 3)):
                        cells[r, c] = cell
                column_index += repeat
            row_index += row_repeat
            if row_index > 6:
                break
        by_name = {
            node.get(q("style", "name")): node
            for tree in (styles, content)
            for node in tree.findall(".//style:style", NAMESPACES)
        }
        snippets = []
        for label, coords in (("A1", (1, 1)), ("B1", (1, 2))):
            cell = cells[coords]
            style_name = cell.get(q("table", "style-name"))
            chain = []
            while style_name:
                assert style_name not in chain, "Cycle dans les styles"
                chain.append(style_name)
                style = by_name[style_name]
                properties = style.find("style:text-properties", NAMESPACES)
                weight = properties.get(q("fo", "font-weight")) if properties is not None else None
                if weight:
                    break
                style_name = style.get(q("style", "parent-style-name"))
            else:
                weight = None
            assert weight == "bold" or (weight and weight.isdigit() and int(weight) >= 700), label
            snippets.append(f"{label}: {ET.tostring(cell, encoding='unicode')}")
            snippets.append(ET.tostring(by_name[style_name], encoding="unicode"))
        total = cells[6, 2]
        assert total.get(q("office", "value")) == "465"
        assert total.get(q("table", "formula")) == "of:=SUM([.B2:.B5])"
        snippets.append(f"B6: {ET.tostring(total, encoding='unicode')}")
        charts = []
        for obj in sheet.findall(".//draw:object", NAMESPACES):
            member = obj.get(q("xlink", "href")).removeprefix("./") + "/content.xml"
            chart = ET.fromstring(archive.read(member))
            for plot in chart.findall(".//chart:plot-area", NAMESPACES):
                address = plot.get(q("table", "cell-range-address"))
                assert address is not None
                normalized = address.replace("$", "").replace("'", "").replace(":.", ":ventes.")
                assert normalized == "ventes.A1:ventes.B5", address
                charts.append(address)
                snippets.append(f'chart: table:cell-range-address="{address}"')
        assert len(charts) == 1
        return snippets
