"""Point d'entrée de préparation d'une leçon Blender."""

import argparse
import asyncio
import json
import logging
import re
import time
from pathlib import Path

from prep.compile import HoloCompiler
from prep.ingest import ingest
from prep.prover import prove_lesson
from prep.sandbox import BlenderSandbox
from prep.ui_map import dump_ui_map


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Préparer et prouver un tutoriel Blender")
    result.add_argument("source")
    result.add_argument("--out", required=True, type=Path)
    result.add_argument("--blender", default="blender")
    result.add_argument("--language")
    result.add_argument("--source-version")
    result.add_argument("--lesson-id")
    result.add_argument("--holo-model", default="holo4-35b-a3b")
    result.add_argument("--holo-fallback-model", default="holo4-27b")
    return result


async def prepare(args: argparse.Namespace) -> int:
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    lesson_id = args.lesson_id or out.name
    if not re.fullmatch(r"[A-Za-z0-9_-]+", lesson_id):
        raise ValueError("Identifiant de leçon non sûr")
    timings = {}
    started = time.perf_counter()
    try:
        stage = time.perf_counter()
        transcript = await ingest(args.source, work_dir=out / "ingest", language=args.language)
        timings["ingest"] = time.perf_counter() - stage
        timings["gladia"] = transcript.latencies
        (out / "transcript.json").write_text(json.dumps(transcript.to_dict(), indent=2))
        async with BlenderSandbox(args.blender) as sandbox:
            stage = time.perf_counter()
            target = await dump_ui_map(sandbox)
            version = target["blender_version"]
            source_version = args.source_version or version
            if not re.fullmatch(r"\d+\.\d+\.\d+", source_version):
                raise ValueError("Version source invalide")
            source_path = Path.home() / ".cache/hcompany-prep/ui_maps" / f"{source_version}.json"
            source = (
                target
                if source_version == version
                else (json.loads(source_path.read_text()) if source_path.exists() else None)
            )
            if source and source.get("blender_version") != source_version:
                source = None
            timings["ui_map"] = time.perf_counter() - stage
            async with HoloCompiler(
                model=args.holo_model, fallback_model=args.holo_fallback_model
            ) as compiler:
                stage = time.perf_counter()
                lesson = await compiler.compile(
                    transcript,
                    target,
                    lesson_id=lesson_id,
                    blender_version=version,
                )
                timings["compile"] = time.perf_counter() - stage
                (out / "compile_report.json").write_text(
                    json.dumps(
                        {
                            "rejections": compiler.rejections,
                            "metrics": compiler.metrics,
                        },
                        indent=2,
                    )
                )
                stage = time.perf_counter()
                lesson = await prove_lesson(
                    lesson,
                    sandbox,
                    source,
                    target,
                    out,
                    reselect=compiler.reselect,
                    rejected_steps=compiler.rejections,
                )
                timings["prove"] = time.perf_counter() - stage
                timings["holo"] = compiler.metrics
        proven = sum(step["proof"]["status"] == "proven" for step in lesson["steps"])
        print(
            f"Leçon {lesson_id} : {lesson['status']} — "
            f"{proven}/{len(lesson['steps'])} étapes prouvées."
        )
        return 0 if lesson["status"] == "proven" else 2
    finally:
        timings["total"] = time.perf_counter() - started
        (out / "timings.json").write_text(json.dumps(timings, indent=2))


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s : %(message)s")
    args = parser().parse_args()
    try:
        return asyncio.run(prepare(args))
    except (ValueError, TimeoutError, RuntimeError, OSError) as exc:
        print(f"Préparation impossible : {exc}")
        return 1
    except Exception as exc:
        print(f"Préparation impossible : {type(exc).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
