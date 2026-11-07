"""Capteur Blender ; l'import hors Blender reste sans effet."""

bl_info = {
    "name": "Œil — capteur de leçon",
    "author": "Hcompany Hack",
    "version": (1, 0, 0),
    "blender": (4, 5, 0),
    "category": "System",
}

_runtime = None


def register() -> None:
    global _runtime
    if _runtime is None:
        from .runtime import Runtime

        _runtime = Runtime.from_environment()
        _runtime.start()


def unregister() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.stop()
        _runtime = None
