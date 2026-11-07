import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "blender: exécution réelle de Blender en arrière-plan")
