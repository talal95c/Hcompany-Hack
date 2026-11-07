import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "blender: exécution réelle de Blender en arrière-plan")
    config.addinivalue_line("markers", "a11y: exécution réelle via AT-SPI et affichage privé")
    config.addinivalue_line("markers", "live: appel réel à un service cloud")
