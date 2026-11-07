"""Lecture seule d'un document ODF réellement enregistré par l'interface."""

import hashlib
import xml.etree.ElementTree as ET
import zipfile

NS = {"text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0"}


def inspect_document(directory, specification):
    filename = specification["filename"]
    path = directory / filename
    if path.parent != directory or not path.is_file():
        return {"file": filename, "status": "fail", "exists": False}
    result = {
        "file": filename,
        "exists": True,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    try:
        with zipfile.ZipFile(path) as archive:
            if any(
                archive.getinfo(name).file_size > 5_000_000 for name in ("mimetype", "content.xml")
            ):
                raise ValueError("Document trop grand")
            mimetype = archive.read("mimetype").decode("ascii")
            content = archive.read("content.xml")
        root = ET.fromstring(content)
        headings = [
            {
                "text": "".join(node.itertext()),
                "style_name": node.get("{" + NS["text"] + "}style-name"),
                "outline_level": node.get("{" + NS["text"] + "}outline-level"),
            }
            for node in root.findall(".//text:h", NS)
        ]
        expected = specification["heading"]
        matching = any(
            h["text"] == expected["text"]
            and h["style_name"] == expected["style_name"]
            and h["outline_level"] == str(expected["outline_level"])
            for h in headings
        )
        return {
            **result,
            "status": "pass" if matching and mimetype == specification["mimetype"] else "fail",
            "mimetype": mimetype,
            "headings": headings,
            "content_sha256": hashlib.sha256(content).hexdigest(),
        }
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return {**result, "status": "unknown", "error": "invalid_document"}
