"""Prépare une capture lisible sans changer son contenu."""

import math
import struct
import subprocess


def png_dimensions(path):
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("Capture PNG invalide")
    width, height = struct.unpack(">II", header[16:24])
    if min(width, height) <= 0:
        raise ValueError("Capture vide")
    return {"width": width, "height": height}


def scaled_dimensions(width, height, minimum=600):
    if min(width, height, minimum) <= 0:
        raise ValueError("Dimensions invalides")
    factor = max(1, minimum / min(width, height))
    return {"width": math.ceil(width * factor), "height": math.ceil(height * factor)}


def prepare_image(original, sent):
    dimensions = png_dimensions(original)
    desired = scaled_dimensions(**dimensions)
    subprocess.run(["convert", str(original), "-resize",
                    f"{desired['width']}x{desired['height']}!", str(sent)],
                   check=True, timeout=15)
    actual = png_dimensions(sent)
    if actual != desired:
        raise RuntimeError("Dimensions de capture envoyée incompatibles")
    return {"original_dimensions": dimensions, "sent_dimensions": actual}
