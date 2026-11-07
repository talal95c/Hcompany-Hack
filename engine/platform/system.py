"""Small, explicit OS capability boundary."""

import platform
from typing import Literal


def operating_system() -> Literal["macos", "linux", "windows", "unsupported"]:
    return {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(
        platform.system(), "unsupported"
    )
