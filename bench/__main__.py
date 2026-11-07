import argparse
import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bench import addon, holo
from bench.common import write_report


async def unavailable(**kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError("Suite non implémentée à cette étape")


SUITES: dict[str, Callable] = {
    "addon": addon.run,
    "holo": holo.run,
    "jev": unavailable,
    "gladia": unavailable,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmarks réels, rapports JSON et Markdown")
    parser.add_argument("suite", choices=[*SUITES, "all"])
    parser.add_argument("--out", type=Path, default=Path("bench/results"))
    parser.add_argument("--operations", type=int, default=50, help="Opérations de la sonde addon")
    parser.add_argument("--blender", default="/opt/blender/blender")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--models", nargs="+", choices=holo.MODELS, default=holo.MODELS)
    parser.add_argument("--concurrency", type=int, choices=[1], default=1)
    args = parser.parse_args()
    names = list(SUITES) if args.suite == "all" else [args.suite]
    if any(SUITES[name] is unavailable for name in names):
        parser.error("Suites jev et gladia non implémentées à cette étape")
    for name in names:
        try:
            options = {
                "blender": args.blender,
                "timeout": args.timeout or (30 if name == "holo" else 60),
            }
            if name == "holo":
                options.update(out=args.out, models=args.models, concurrency=args.concurrency)
            else:
                options.update(operations=args.operations)
            report = asyncio.run(SUITES[name](**options))
        except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
            parser.exit(1, f"Erreur benchmark : {exc}\n")
        print(write_report(name, report, args.out))


if __name__ == "__main__":
    main()
