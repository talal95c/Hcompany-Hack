"""Exécution isolée des scripts Blender de confiance."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from prep.prover.procedures import PROCEDURE_LIBRARY


class BlenderSandbox:
    def __init__(self, executable: str = "blender", timeout: float = 60) -> None:
        self.executable = executable
        self.timeout = timeout
        self._workspace = tempfile.TemporaryDirectory(prefix="hcompany-blender-")
        self.root = Path(self._workspace.name)

    def close(self) -> None:
        self._workspace.cleanup()

    async def __aenter__(self) -> "BlenderSandbox":
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.close()

    async def invoke(self, operation: str, **args: Any) -> dict:
        with tempfile.TemporaryDirectory(dir=self.root) as directory:
            root = Path(directory)
            source, result = root / "args.json", root / "result.json"
            source.write_text(
                json.dumps({"operation": operation, "fingerprint_cache": str(self.root), **args})
            )
            process = await asyncio.create_subprocess_exec(
                self.executable,
                "-b",
                "--factory-startup",
                "--python-exit-code",
                "1",
                "--python",
                str(Path(__file__).with_name("worker.py")),
                "--",
                str(source),
                str(result),
                cwd=root,
                env={k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), self.timeout)
            except (TimeoutError, asyncio.CancelledError):
                process.kill()
                await process.wait()
                raise
            if process.returncode or not result.exists():
                message = (stderr + stdout).decode()
                raise RuntimeError(f"Blender a échoué : {message[:4000]}\n{message[-4000:]}")
            return json.loads(result.read_text())

    async def version(self) -> str:
        return (await self.invoke("version"))["blender_version"]

    async def reset(self) -> Path:
        checkpoint = self.root / "empty.blend"
        await self.invoke("reset", checkpoint_out=str(checkpoint))
        return checkpoint

    async def run_step(
        self,
        checkpoint_in: str | Path,
        procedure: str,
        check: dict,
        checkpoint_out: str | Path,
    ) -> dict:
        if procedure not in PROCEDURE_LIBRARY:
            raise ValueError("Procédure non autorisée")
        return await self.invoke(
            "step",
            checkpoint_in=str(Path(checkpoint_in).resolve()),
            checkpoint_out=str(Path(checkpoint_out).resolve()),
            procedure=procedure,
            check=check,
            procedures=PROCEDURE_LIBRARY,
        )
