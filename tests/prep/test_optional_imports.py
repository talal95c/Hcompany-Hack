import subprocess
import sys
from pathlib import Path


def test_packages_import_without_network_extras():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib
import importlib.abc
import sys
from pathlib import Path

class WithoutExtras(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'httpx', 'openai'}:
            raise ModuleNotFoundError(fullname, name=fullname)

sys.meta_path.insert(0, WithoutExtras())
for path in Path('prep').rglob('__init__.py'):
    importlib.import_module('.'.join(path.parent.parts))
""",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
