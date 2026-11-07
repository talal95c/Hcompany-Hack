"""Comparaison des pointeurs sur une fenêtre Calc privée."""

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

from PIL import Image

from bench import holo
from bench.a11y_session import A11ySession
from bench.common import statistics
from bench.verify_assets import optimize

TARGETS = [
    ("Bold", "the button that makes the selected cell text bold", True),
    ("Italic", "le bouton qui met le texte de la cellule en italique", True),
    ("Underline", "the toolbar button for underlining the selected cell text", True),
    ("Align Center", "le bouton pour centrer horizontalement le contenu de la cellule", False),
    ("Sort Ascending", "the toolbar button that sorts spreadsheet data in ascending order", False),
    ("Chart", "le bouton de la barre d'outils pour insérer un graphique", False),
    (
        "Select Function",
        "the small dropdown button with a sigma symbol for selecting a function",
        False,
    ),
    ("Wrap Text", "le bouton qui active le retour automatique à la ligne dans une cellule", False),
    ("Merge Cells", "the toolbar button for merging cells without centering their contents", False),
]


def normalize(point: tuple[float, float], capture: list[int]) -> tuple[float, float]:
    x, y, width, height = capture
    if width <= 0 or height <= 0:
        raise ValueError("Dimensions de capture invalides")
    return ((point[0] - x) * 1000 / width, (point[1] - y) * 1000 / height)


def physical(point: tuple[float, float], capture: list[int]) -> tuple[int, int]:
    x, y, width, height = capture
    if width <= 0 or height <= 0 or any(not math.isfinite(v) or not 0 <= v <= 1000 for v in point):
        raise ValueError("Pointeur invalide")
    return (round(x + point[0] * width / 1000), round(y + point[1] * height / 1000))


def evaluate(point: tuple[float, float], bounds: list[int], capture: list[int]) -> dict[str, Any]:
    px, py = physical(point, capture)
    x, y, width, height = bounds
    return {
        "point_normalized": point,
        "point_screen": [px, py],
        "hit": x <= px < x + width and y <= py < y + height,
        "distance_px": math.hypot(px - (x + width / 2), py - (y + height / 2)),
    }


def aggregate(samples: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(samples)
    functional = [s for s in samples if s["functional_eligible"]]
    distances = [s["distance_px"] for s in samples if s.get("distance_px") is not None]
    return {
        "calls": count,
        "hit_rate": sum(s.get("hit", False) for s in samples) / count if count else None,
        "functional_trials": len(functional),
        "functional_click_success_rate": sum(s.get("functional_success", False) for s in functional)
        / len(functional)
        if functional
        else None,
        "distance_px": {
            "count": len(distances),
            "p50": statistics(distances)["p50_ms"],
            "p95": statistics(distances)["p95_ms"],
        },
        "latency": statistics(
            [s["latency_ms"] for s in samples if s.get("latency_ms") is not None]
        ),
        "wall_latency": statistics(
            [s["wall_time_ms"] for s in samples if s.get("wall_time_ms") is not None]
        ),
        "failures": sum(s.get("failure") is not None for s in samples),
        "functional_failures": sum(not s.get("functional_success", False) for s in functional),
    }


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    groups = {
        method: aggregate([s for s in samples if s["method"] == method])
        for method in sorted({s["method"] for s in samples})
    }
    lines = [
        "| Méthode | N | Hit | Clic fonctionnel | Distance p50/p95 px | "
        "Latence p50/p95 ms | Mur p50/p95 ms | Échecs |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for method, metrics in groups.items():

        def percent(key):
            value = metrics[key]
            return f"{value:.1%}" if value is not None else "—"

        distance = metrics["distance_px"]
        latency, wall = metrics["latency"], metrics["wall_latency"]

        def pair(a, b):
            return f"{a:.2f}/{b:.2f}" if a is not None and b is not None else "—"

        lines.append(
            f"| {method} | {metrics['calls']} | {percent('hit_rate')} | "
            f"{percent('functional_click_success_rate')} ({metrics['functional_trials']}) | "
            f"{pair(distance['p50'], distance['p95'])} | "
            f"{pair(latency['p50_ms'], latency['p95_ms'])} | "
            f"{pair(wall['p50_ms'], wall['p95_ms'])} | {metrics['failures']} |"
        )
    return {
        "summary": {"calls": len(samples), "failures": sum(g["failures"] for g in groups.values())},
        "by_method": groups,
        "raw_samples": samples,
        "notes": [
            "\n".join(lines),
            "AT-SPI : recherche exacte + conversion, transport et création du client inclus. "
            "Holo : dernière requête HTTP ; mur = pacing et retries inclus, hors capture/clic.",
            "Distances en pixels physiques, origine de fenêtre soustraite avant normalisation. "
            "PNG réduit : les millièmes restent ceux de la fenêtre entière, sans double DPI.",
            "Hit géométrique auto-référencé pour AT-SPI ; test indépendant par vrai clic "
            "xdotool sur Gras/Italique/Souligné, lecture AT-SPI, puis restauration vérifiée.",
            "Dénominateur fonctionnel : tous les essais des trois cibles de formatage, "
            "y compris les pointeurs manquants ; aucune action sur les autres cibles.",
            "Les erreurs de protocole comptent comme échecs ; un miss ou un clic sans "
            "effet est un résultat incorrect, pas une erreur de protocole.",
        ],
    }


async def run(
    out: Path,
    models: list[str] | None = None,
    repeats: int = 3,
    timeout: float = 30,
    limit: int | None = None,
) -> dict[str, Any]:
    models = models or ["holo4-27b"]
    if (
        repeats < 1
        or timeout <= 0
        or any(m not in holo.MODELS for m in models)
        or (limit is not None and not 1 <= limit <= len(TARGETS))
    ):
        raise ValueError("Options pointer invalides")
    client = holo.Client(timeout)
    root = out / "pointer_assets"
    root.mkdir(parents=True, exist_ok=True)
    samples, captures, startups = [], [], []
    try:
        with (out / "pointer-calls.jsonl").open("w") as log:
            for repeat in range(repeats):
                async with A11ySession() as session:
                    startups.append(await session.launch_calc())
                    await session.request("configure_cell")
                    for index, (name, prompt, toggle) in enumerate(TARGETS[:limit]):
                        path = root / f"calc-{repeat:02d}-{index:02d}.png"
                        captured = (await session.request("capture", path=str(path.resolve())))[
                            "result"
                        ]
                        bounds = captured["bounds"]
                        with Image.open(path) as source:
                            if list(source.size) != bounds[2:]:
                                raise ValueError("Capture différente de la géométrie fenêtre")
                        size = optimize(path)
                        capture = {
                            "id": path.stem,
                            "image": path.name,
                            **captured,
                            "image_size": list(size),
                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        }
                        captures.append(capture)
                        started = time.perf_counter()
                        found = await session.request("find", name=name)
                        target = found["result"]
                        if target is None:
                            raise RuntimeError(f"Cible inaccessible : {name}")
                        x, y, w, h = target["bounds"]
                        point = normalize((x + w / 2, y + h / 2), bounds)
                        elapsed = (time.perf_counter() - started) * 1000
                        common = {
                            "repeat": repeat,
                            "target": name,
                            "prompt": prompt,
                            "capture_id": capture["id"],
                            "capture_bounds": bounds,
                            "target_evidence": target,
                            "functional_eligible": toggle,
                        }
                        candidates = [
                            {
                                "method": "a11y",
                                "point": point,
                                "latency_ms": elapsed,
                                "wall_time_ms": elapsed,
                                "sensor_latency_ms": found["latency_ms"],
                                "failure": None,
                            }
                        ]
                        with Image.open(path) as source:
                            image = source.convert("RGB")
                        for model in models:
                            response = await client.call(holo.request_body(model, image, prompt))
                            candidates.append(
                                {
                                    "method": "holo:" + model,
                                    **response,
                                    "point": response["point_normalized"],
                                    "failure": None
                                    if response["point_normalized"] is not None
                                    and response["status"] == 200
                                    else "invalid_pointer",
                                }
                            )
                        for candidate in candidates:
                            # A fresh sensor query guards against layout changes while Holo runs.
                            current = await session.find_element(name)
                            geometry = (
                                await session.request(
                                    "capture", path=str((root / "geometry.png").resolve())
                                )
                            )["result"]
                            if (
                                current is None
                                or current["bounds"] != target["bounds"]
                                or geometry != captured
                            ):
                                raise RuntimeError("Capture invalidée : géométrie modifiée")
                            sample = {**common, **candidate}
                            if candidate["point"] is not None:
                                sample.update(
                                    evaluate(candidate["point"], target["bounds"], bounds)
                                )
                                if toggle:
                                    result = (
                                        await session.request(
                                            "click_toggle",
                                            name=name,
                                            x=sample["point_screen"][0],
                                            y=sample["point_screen"][1],
                                        )
                                    )["result"]
                                    sample.update(
                                        functional_success=result["success"],
                                        functional_evidence=result,
                                    )
                            samples.append(sample)
                            log.write(json.dumps(sample, ensure_ascii=False) + "\n")
                            log.flush()
    finally:
        await client.http.aclose()
    (root / "geometry.png").unlink(missing_ok=True)
    manifest = {
        "captures": captures,
        "startups": startups,
        "targets": [
            {"name": name, "prompt": prompt, "functional": toggle}
            for name, prompt, toggle in TARGETS[:limit]
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    report = summarize(samples)
    report["configuration"] = {
        "models": models,
        "repeats": repeats,
        "timeout_seconds": timeout,
        "targets": len(TARGETS[:limit]),
        "thinking": False,
    }
    report["notes"].insert(
        0, f"Modèles : {', '.join(models)} ; {len(TARGETS[:limit])} cibles, {repeats} répétitions."
    )
    return report
