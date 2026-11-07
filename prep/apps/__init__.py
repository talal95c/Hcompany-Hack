"""Profils d'application de la préparation : adaptateur dédié ou capteurs génériques.

Un profil `adapter="blender"` garde le chemin historique (add-on, checks `blender.*`).
Tout autre profil passe par le chemin générique : instantané d'accessibilité, checks
`element_*`/`window_title`/`visual_assert`, rejeu Holo computer use en bac à sable.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from typing import Literal

from prep.apps.calc import CalcAdapter

Sensor = Literal["addon", "accessibility", "vision"]
GENERIC_CHECKS = (
    "element_exists",
    "element_value",
    "element_state",
    "window_title",
    "visual_assert",
)
APP_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class AppProfile:
    id: str
    name: str
    sensor: Sensor
    adapter: str = "generic"
    command: tuple[str, ...] = ()
    """Lancement ; `{file}` = document de travail, `{profile}` = profil utilisateur isolé."""
    accessible_name: str = ""
    window_title: str = ""
    version_command: tuple[str, ...] = ()
    version_pattern: str = r"(\d+(?:\.\d+)+)"
    document_suffix: str = ""
    convert_command: tuple[str, ...] = ()
    """Conversion d'une fixture brute (ex. CSV) vers `document_suffix` ; `{src}`, `{outdir}`."""
    convertible_suffixes: tuple[str, ...] = ()
    save_keys: tuple[str, ...] = ("ctrl", "s")
    env: dict[str, str] = field(default_factory=dict)
    app_checks: tuple[str, ...] = ()
    outcome_adapter: type | None = None
    docs_domains: tuple[str, ...] = ()

    @property
    def checks(self) -> tuple[str, ...]:
        return GENERIC_CHECKS + self.app_checks

    @property
    def generic(self) -> bool:
        return self.adapter == "generic"


LIBREOFFICE_ENV = {
    "SAL_USE_VCLPLUGIN": "gtk3",
    "GTK_MODULES": "gail:atk-bridge",
    "NO_AT_BRIDGE": "0",
}


def _libreoffice(
    app_id: str, name: str, module: str, suffix: str, sources: tuple[str, ...]
) -> AppProfile:
    return AppProfile(
        id=app_id,
        name=name,
        sensor="accessibility",
        command=(
            "soffice",
            f"--{module}",
            "--norestore",
            "--nologo",
            "--nofirststartwizard",
            "-env:UserInstallation=file://{profile}",
            "{file}",
        ),
        accessible_name="soffice",
        window_title=f"LibreOffice {name.split()[-1]}",
        version_command=("soffice", "--version"),
        version_pattern=r"LibreOffice (\d+(?:\.\d+)+)",
        document_suffix=suffix,
        convert_command=(
            "soffice",
            "--headless",
            "-env:UserInstallation=file://{profile}",
            "--infilter=CSV:44,34,76,1",
            "--convert-to",
            suffix.lstrip("."),
            "--outdir",
            "{outdir}",
            "{src}",
        ),
        convertible_suffixes=sources,
        env=LIBREOFFICE_ENV,
        app_checks=CalcAdapter.checks if module == "calc" else (),
        outcome_adapter=CalcAdapter if module == "calc" else None,
        docs_domains=("help.libreoffice.org",),
    )


PROFILES: dict[str, AppProfile] = {
    "blender": AppProfile(id="blender", name="Blender", sensor="addon", adapter="blender"),
    "libreoffice-calc": _libreoffice(
        "libreoffice-calc", "LibreOffice Calc", "calc", ".ods", (".csv", ".xlsx", ".xls")
    ),
    "libreoffice-writer": _libreoffice(
        "libreoffice-writer", "LibreOffice Writer", "writer", ".odt", (".txt", ".docx")
    ),
}


def get_profile(
    app_id: str,
    *,
    command: str | None = None,
    accessible_name: str | None = None,
    name: str | None = None,
    sensor: Sensor | None = None,
) -> AppProfile:
    """Profil connu, ou profil générique construit depuis une commande de lancement."""
    if not APP_ID.fullmatch(app_id):
        raise ValueError(f"Identifiant d'application invalide : {app_id!r}")
    known = PROFILES.get(app_id)
    if known is not None and command is None:
        return known
    if known is not None and not known.generic:
        raise ValueError("Une application avec adaptateur dédié ne prend pas --app-command")
    if not command:
        raise ValueError(
            f"Application {app_id!r} sans profil : préciser --app-command (ex. 'gedit {{file}}')"
        )
    argv = tuple(shlex.split(command))
    return AppProfile(
        id=app_id,
        name=name or app_id,
        sensor=sensor or "accessibility",
        command=argv,
        accessible_name=accessible_name or argv[0].rsplit("/", 1)[-1],
        version_command=(argv[0], "--version"),
    )
