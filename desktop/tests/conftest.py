def pytest_configure(config):
    config.addinivalue_line("markers", "live: requires a native desktop and real local transport")
