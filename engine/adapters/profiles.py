"""Profils d'application : vocabulaire STT, contexte Jev, domaines de documentation."""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "profiles"


@dataclass(frozen=True)
class AppProfile:
    id: str
    name: str
    vocabulary: tuple[str, ...] = ()
    jev_context: str = ""
    docs_domains: tuple[str, ...] = ()
    shortcut_hint: str | None = None
    process_names: tuple[str, ...] = ()

    def matches(self, app_id: str, name: str = "") -> bool:
        """Identité d'une fenêtre `app.focus` (id ou nom de processus, sans la casse)."""
        candidates = {self.id.casefold(), self.name.casefold(),
                      *(p.casefold() for p in self.process_names)}
        return app_id.casefold() in candidates or name.casefold() in candidates

    def service_context(self) -> dict:
        return {"app_id": self.id, "app_name": self.name, "context": self.jev_context}


@cache
def _known(app_id: str) -> AppProfile | None:
    path = ROOT / f"{app_id}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text())
    if data["id"] != app_id:
        raise ValueError(f"Profil incohérent : {path.name}")
    return AppProfile(
        id=data["id"], name=data["name"], vocabulary=tuple(data.get("vocabulary", ())),
        jev_context=data.get("jev_context", ""),
        docs_domains=tuple(data.get("docs_domains", ())),
        shortcut_hint=data.get("shortcut_hint"),
        process_names=tuple(data.get("process_names", ())),
    )


def load_profile(app: dict) -> AppProfile:
    """Profil de `lesson.app` ; une application inconnue reçoit un profil minimal neutre."""
    if not ROOT.joinpath(f"{app['id']}.json").resolve().is_relative_to(ROOT):
        raise ValueError("Identifiant d'application invalide")
    return _known(app["id"]) or AppProfile(
        id=app["id"], name=app["name"], vocabulary=(app["name"],),
        jev_context=f"Application de bureau {app['name']}.", process_names=(app["id"],),
    )
