"""Point d'entrée de préparation : tutoriel → leçon prouvée pour une application."""

import argparse
import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path

from prep.apps import PROFILES, AppProfile, get_profile
from prep.compile import HoloCompiler
from prep.ingest import ingest
from prep.prover import prove_lesson
from prep.sandbox import BlenderSandbox
from prep.ui_map import dump_ui_map

LOGGER = logging.getLogger(__name__)
UI_MAP_CACHE = Path.home() / ".cache/hcompany-prep/ui_maps"
PREVIEW_SUFFIXES = {".csv", ".txt", ".md", ".tsv"}


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Préparer et prouver un tutoriel")
    result.add_argument("source")
    result.add_argument("--out", required=True, type=Path)
    result.add_argument(
        "--app",
        default="blender",
        help=f"Profil d'application ({', '.join(PROFILES)}) ou identifiant avec --app-command",
    )
    result.add_argument("--app-command", help="Lancement d'une application sans profil ({file})")
    result.add_argument("--app-accessible-name", help="Nom AT-SPI/AX/UIA de l'application")
    result.add_argument("--fixture", type=Path, help="Document initial (copié, jamais modifié)")
    result.add_argument("--max-turns", type=int, default=10)
    result.add_argument("--blender", default="blender")
    result.add_argument("--language")
    result.add_argument("--source-version")
    result.add_argument("--lesson-id")
    result.add_argument("--holo-model", default="holo4-35b-a3b")
    result.add_argument("--holo-fallback-model", default="holo4-27b")
    return result


def profile_for(args: argparse.Namespace) -> AppProfile:
    return get_profile(args.app, command=args.app_command, accessible_name=args.app_accessible_name)


def fixture_preview(path: Path | None, limit: int = 6000) -> str | None:
    if path is None or path.suffix.lower() not in PREVIEW_SUFFIXES:
        return None
    text = path.read_text(errors="replace")
    return text if len(text) <= limit else text[:limit] + "\n[…tronqué]"


async def prepare(args: argparse.Namespace) -> int:
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    lesson_id = args.lesson_id or out.name
    if not re.fullmatch(r"[A-Za-z0-9_-]+", lesson_id):
        raise ValueError("Identifiant de leçon non sûr")
    profile = profile_for(args)
    if profile.generic:
        return await prepare_generic(args, profile, out, lesson_id)
    return await prepare_blender(args, out, lesson_id)


async def prepare_generic(
    args: argparse.Namespace, profile: AppProfile, out: Path, lesson_id: str
) -> int:
    from prep.compile.generic import GenericCompiler
    from prep.docs_search import search_docs
    from prep.prover.generic import file_sha256, prove_generic_lesson
    from prep.prover.holo_desktop import HoloDesktopAgent
    from prep.sandbox.desktop import DesktopSandbox
    from prep.ui_map.accessibility import build_ui_map, diff_ui_maps

    timings: dict = {}
    started = time.perf_counter()
    try:
        async with DesktopSandbox(profile) as sandbox:
            stage = time.perf_counter()
            version = await sandbox.version()
            fixture = await sandbox.prepare_fixture(args.fixture)
            await sandbox.open(fixture, sha256=file_sha256(fixture))
            snapshot = await sandbox.snapshot()
            if not snapshot.get("nodes"):
                LOGGER.warning("Arbre d'accessibilité vide : checks visuels seulement")
            app = {"id": profile.id, "name": profile.name, "version": version}
            target = build_ui_map(snapshot, app=app)
            cache = UI_MAP_CACHE / profile.id / f"{version}.json"
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(target, indent=2, ensure_ascii=False))
            (out / "ui_map.json").write_text(json.dumps(target, indent=2, ensure_ascii=False))
            source_version = args.source_version or version
            source_path = UI_MAP_CACHE / profile.id / f"{source_version}.json"
            source = (
                target
                if source_version == version
                else (json.loads(source_path.read_text()) if source_path.exists() else None)
            )
            (out / "ui_map_diff.json").write_text(json.dumps(diff_ui_maps(source, target)))
            timings["ui_map"] = time.perf_counter() - stage
            stage = time.perf_counter()
            transcript = await ingest(
                args.source, work_dir=out / "ingest", language=args.language, ui_map=target
            )
            timings["ingest"] = time.perf_counter() - stage
            timings["gladia"] = transcript.latencies
            (out / "transcript.json").write_text(json.dumps(transcript.to_dict(), indent=2))
            async with GenericCompiler(
                profile, model=args.holo_model, fallback_model=args.holo_fallback_model
            ) as compiler:
                stage = time.perf_counter()
                lesson = await compiler.compile(
                    transcript,
                    target,
                    lesson_id=lesson_id,
                    app_version=version,
                    fixture_preview=fixture_preview(args.fixture),
                )
                timings["compile"] = time.perf_counter() - stage
                timings["holo_compile"] = compiler.metrics
                (out / "compile_report.json").write_text(
                    json.dumps(
                        {
                            "rejections": compiler.rejections,
                            "unresolved_targets": compiler.unresolved,
                            "dropped_known_errors": compiler.dropped_errors,
                            "metrics": compiler.metrics,
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
            search = None
            if profile.docs_domains and os.environ.get("LINKUP_API_KEY"):

                async def search(query: str) -> list[dict]:
                    return await search_docs(query, domains=profile.docs_domains)

            async with HoloDesktopAgent(model=args.holo_model) as operator:
                stage = time.perf_counter()
                lesson = await prove_generic_lesson(
                    lesson,
                    sandbox,
                    operator,
                    out,
                    fixture=fixture,
                    source_map=source,
                    target_map=target,
                    search=search,
                    rejected_steps=compiler.rejections,
                    max_turns=args.max_turns,
                )
                timings["prove"] = time.perf_counter() - stage
                timings["holo_operator"] = operator.metrics
            timings["sandbox"] = sandbox.metrics
        proven = sum(step["proof"]["status"] == "proven" for step in lesson["steps"])
        print(
            f"Leçon {lesson_id} ({profile.name} {version}) : {lesson['status']} — "
            f"{proven}/{len(lesson['steps'])} étapes prouvées."
        )
        return 0 if lesson["status"] == "proven" else 2
    finally:
        timings["total"] = time.perf_counter() - started
        (out / "timings.json").write_text(json.dumps(timings, indent=2))


async def prepare_blender(args: argparse.Namespace, out: Path, lesson_id: str) -> int:
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
