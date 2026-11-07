import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "live: appels réels aux services cloud (clés requises)")


def pytest_collection_modifyitems(config, items):
    expression = config.option.markexpr
    enabled = os.getenv("RUN_LIVE") == "1" or expression.strip() == "live"
    if not enabled:
        marker = pytest.mark.skip(
            reason="Appels cloud désactivés ; sélectionner -m live ou RUN_LIVE=1",
        )
        for item in items:
            if "live" in item.keywords:
                item.add_marker(marker)
