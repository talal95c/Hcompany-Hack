def pytest_configure(config):
    config.addinivalue_line("markers", "live: intégration exécutée dans un vrai processus Blender")
    config.addinivalue_line("markers", "blender: nécessite Blender 4.5 LTS")
