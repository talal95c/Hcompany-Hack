def pytest_configure(config):
    config.addinivalue_line("markers", "live: appels réseau avec clé explicite")
