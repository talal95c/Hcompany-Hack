"""Petits constructeurs partagés par les générateurs de leçons génériques."""

import json


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def target(role, name, path, description):
    return {
        "description": description,
        "role": role,
        "name": name,
        "path": path,
        "app_region": path[-1],
    }
