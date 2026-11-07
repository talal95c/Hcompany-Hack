import argparse
import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from bench import a11y, addon, gladia, holo, jev, pointer, verify
from bench.common import write_report


async def unavailable(**kwargs: Any) -> dict[str, Any]:
    raise NotImplementedError("Suite non implémentée à cette étape")


SUITES: dict[str, Callable] = {
    "addon": addon.run,
    "holo": holo.run,
    "jev": jev.run,
    "gladia": gladia.run,
    "a11y": a11y.run,
    "verify": verify.run,
    "pointer": pointer.run,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmarks réels, rapports JSON et Markdown")
    parser.add_argument("suite", choices=[*SUITES, "all"])
    parser.add_argument("--out", type=Path, default=Path("bench/results"))
    parser.add_argument("--operations", type=int, default=50, help="Opérations de la sonde addon")
    parser.add_argument("--blender", default="/opt/blender/blender")
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--models", nargs="+", choices=holo.MODELS, default=None)
    parser.add_argument("--concurrency", type=int, choices=[1], default=1)
    parser.add_argument("--batches-only", action="store_true", help="Jev : conserver les singles")
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--max-nodes", type=int, default=1200)
    parser.add_argument("--max-depth", type=int, default=12)
    parser.add_argument("--restart-each-iteration", action="store_true")
    parser.add_argument("--vcl-plugin", choices=["gtk3", "gen"], default="gtk3")
    parser.add_argument("--repeats", type=int, default=None)
    parser.add_argument("--reuse-assets", action="store_true")
    args = parser.parse_args()
    names = list(SUITES) if args.suite == "all" else [args.suite]
    if any(SUITES[name] is unavailable for name in names):
        parser.error("Suite gladia non implémentée à cette étape")
    for name in names:
        try:
            options = {
                "blender": args.blender,
                "timeout": args.timeout or (30 if name == "holo" else 60),
            }
            if name == "holo":
                options.update(
                    out=args.out, models=args.models or holo.MODELS, concurrency=args.concurrency
                )
            elif name == "verify":
                options = {
                    "out": args.out,
                    "blender": args.blender,
                    "models": args.models or ["holo4-27b"],
                    "repeats": args.repeats if args.repeats is not None else 2,
                    "reuse_assets": args.reuse_assets,
                    "timeout": args.timeout or 30,
                }
            elif name == "pointer":
                options = {
                    "out": args.out,
                    "models": args.models or ["holo4-27b"],
                    "repeats": args.repeats if args.repeats is not None else 3,
                    "timeout": args.timeout or 30,
                }
            elif name == "jev":
                options = {
                    "out": args.out,
                    "timeout": args.timeout or 60,
                    "batches_only": args.batches_only,
                }
            elif name == "gladia":
                options = {"out": args.out, "timeout": args.timeout or 30}
            elif name == "a11y":
                options = {
                    "iterations": args.iterations,
                    "timeout": args.timeout or 15,
                    "max_nodes": args.max_nodes,
                    "max_depth": args.max_depth,
                    "restart_each_iteration": args.restart_each_iteration,
                    "plugin": args.vcl_plugin,
                }
            else:
                options.update(operations=args.operations)
            report = asyncio.run(SUITES[name](**options))
        except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
            parser.exit(1, f"Erreur benchmark : {exc}\n")
        print(write_report(name, report, args.out))
        if name in ("a11y", "verify", "pointer") and report["summary"]["failures"]:
            parser.exit(1, "Échecs conservés dans le rapport.\n")


if __name__ == "__main__":
    main()
