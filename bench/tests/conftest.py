import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: nécessite les applications ou services réels")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.option.markexpr == "live" or os.environ.get("BENCH_LIVE") == "1":
        return
    for item in items:
        if "live" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="Use -m live or BENCH_LIVE=1"))
