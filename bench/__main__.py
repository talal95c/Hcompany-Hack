import argparse
import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bench import addon
from bench.common import write_report


async def unavailable(**kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError("Suite non implémentée à cette étape")


SUITES: dict[str, Callable] = {
    "addon": addon.run,
    "holo": unavailable,
    "jev": unavailable,
    "gladia": unavailable,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmarks réels, rapports JSON et Markdown")
    parser.add_argument("suite", choices=[*SUITES, "all"])
    parser.add_argument("--out", type=Path, default=Path("bench/results"))
    parser.add_argument("--operations", type=int, default=50, help="Opérations de la sonde addon")
    parser.add_argument("--blender", default="/opt/blender/blender")
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    names = list(SUITES) if args.suite == "all" else [args.suite]
    if any(SUITES[name] is unavailable for name in names):
        parser.error("Suites holo, jev et gladia non implémentées à cette étape")
    for name in names:
        try:
            report = asyncio.run(
                SUITES[name](operations=args.operations, blender=args.blender, timeout=args.timeout)
            )
        except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
            parser.exit(1, f"Erreur benchmark : {exc}\n")
        print(write_report(name, report, args.out))


if __name__ == "__main__":
    main()
