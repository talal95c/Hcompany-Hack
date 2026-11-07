"""Mesures locales AT-SPI sur une feuille Calc vierge et privée."""

import asyncio
import platform
from collections import Counter
from typing import Any

from bench.a11y_session import A11ySession
from bench.common import Timer, metadata, statistics

TARGET_GROUPS = (
    ("Bold", "Gras"),
    ("Italic", "Italique"),
    ("Underline", "Souligné"),
    ("Align Center", "Center Horizontally", "Centrer"),
    ("Sort Ascending", "Tri croissant"),
    ("Sum", "AutoSum", "Select Function", "Somme"),
    ("Insert Chart", "Chart", "Diagramme"),
)


def select_targets(buttons: list[dict[str, Any]]) -> list[str]:
    names = {
        button["name"].casefold(): button["name"]
        for button in buttons
        if button["bounds"][2] > 0 and button["bounds"][3] > 0
    }
    return list(
        dict.fromkeys(
            names[alias.casefold()]
            for aliases in TARGET_GROUPS
            for alias in aliases
            if alias.casefold() in names
        )
    )


def latency(values: list[float]) -> dict[str, Any]:
    return {
        key: round(value, 3) if isinstance(value, float) else value
        for key, value in {**statistics(values), "min_ms": min(values) if values else None}.items()
    }


def summarize(
    samples: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    startups: list[dict[str, Any]],
    iterations: int,
) -> dict[str, Any]:
    operations = ("snapshot", "find", "read_cell")
    snapshots = [sample["result"] for sample in samples if sample["operation"] == "snapshot"]
    reads = [sample for sample in samples if sample["operation"] == "read_cell"]
    targets = sorted({sample["name"] for sample in samples if sample["operation"] == "find"})
    return {
        "iterations_requested": iterations,
        "iterations_completed": sum(sample["result"]["correct"] for sample in reads),
        "failures": len(failures),
        "failure_reasons": dict(Counter(failure["reason"] for failure in failures)),
        "sessions": len(startups),
        "time_to_bus": latency([startup["time_to_bus_ms"] for startup in startups]),
        "time_to_window": latency([startup["time_to_window_ms"] for startup in startups]),
        **{
            operation: latency(
                [sample["latency_ms"] for sample in samples if sample["operation"] == operation]
            )
            for operation in operations
        },
        "find_by_name": {
            target: latency(
                [sample["latency_ms"] for sample in samples if sample.get("name") == target]
            )
            for target in targets
        },
        "cell_reads_correct": sum(sample["result"]["correct"] for sample in reads),
        "cell_reads_total": len(reads),
        "tree_node_count": {
            "min": min((s["node_count"] for s in snapshots), default=None),
            "max": max((s["node_count"] for s in snapshots), default=None),
        },
        "tree_max_depth": max((s["max_depth"] for s in snapshots), default=None),
        "tree_roles_last": snapshots[-1]["roles"] if snapshots else {},
        "truncated_snapshots": sum(s["truncated"] for s in snapshots),
    }


async def run(
    iterations: int = 30,
    timeout: float = 15,
    max_nodes: int = 1200,
    max_depth: int = 12,
    restart_each_iteration: bool = False,
    plugin: str = "gtk3",
) -> dict[str, Any]:
    if iterations < 1 or timeout <= 0 or max_nodes < 1 or max_depth < 1:
        raise ValueError("Itérations, délais et limites doivent être positifs")
    if plugin not in ("gtk3", "gen"):
        raise ValueError("Plugin VCL non autorisé")
    version_process = await asyncio.create_subprocess_exec(
        "localc",
        "--version",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        version_output, _ = await asyncio.wait_for(version_process.communicate(), timeout)
    finally:
        if version_process.returncode is None:
            version_process.kill()
            await version_process.wait()
    if version_process.returncode:
        raise RuntimeError("Version Calc indisponible")
    samples: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    startups: list[dict[str, Any]] = []
    discoveries: list[dict[str, Any]] = []
    session = None
    targets: list[str] = []
    recovery = restart_each_iteration
    for iteration in range(iterations):
        operation = "start"
        try:
            if session is None:
                session = A11ySession(timeout=timeout, plugin=plugin)
                await session.__aenter__()
                startup = await session.launch_calc()
                startups.append({"iteration": iteration, **startup})
                operation = "discover"
                buttons = (await session.request("discover"))["result"]
                targets = select_targets(buttons)
                discoveries.append({"iteration": iteration, "buttons": buttons, "targets": targets})
                if not targets:
                    raise RuntimeError("toolbar_targets_unavailable")
            plan = [("snapshot", {"max_nodes": max_nodes, "max_depth": max_depth})]
            plan.extend(("find", {"name": target}) for target in targets)
            plan.extend([("write_cell", {}), ("read_cell", {})])
            for operation, arguments in plan:
                timer = Timer()
                response = await session.request(operation, **arguments)
                sample = {
                    "iteration": iteration,
                    "operation": operation,
                    "ipc_ms": timer.elapsed_ms,
                    **arguments,
                    **response,
                }
                if operation == "find" and response["result"] is None:
                    raise RuntimeError("target_not_found:" + arguments["name"])
                samples.append(sample)
                if operation == "read_cell" and not response["result"]["correct"]:
                    raise RuntimeError("cell_value_mismatch")
        except (OSError, ValueError, RuntimeError, TimeoutError) as error:
            failures.append(
                {
                    "iteration": iteration,
                    "operation": operation,
                    "reason": type(error).__name__ + ":" + str(error),
                    "mitigation": "Nouvelle session et nouveau profil à l'itération suivante.",
                }
            )
            recovery = True
        except BaseException:
            if session is not None:
                await session.close()
                session = None
            raise
        finally:
            if session is not None and (recovery or iteration == iterations - 1):
                await session.close()
                session = None
        if failures and operation == "start" and len(failures) >= 3:
            break
    return {
        "metadata": {
            **metadata(),
            "calc_version": version_output.decode().strip(),
            "system_python": startups[0]["system_python"] if startups else None,
            "platform": platform.platform(),
        },
        "configuration": {
            "iterations": iterations,
            "timeout_seconds": timeout,
            "startup_timeout_seconds": 60,
            "max_nodes": max_nodes,
            "max_depth": max_depth,
            "plugin": plugin,
            "restart_each_iteration": restart_each_iteration,
            "display_size": [1600, 1000],
            "test_value": "424242",
            "environment": {
                "GTK_MODULES": "gail:atk-bridge",
                "NO_AT_BRIDGE": "0",
                "GNOME_ACCESSIBILITY": "1",
            },
        },
        "summary": summarize(samples, failures, startups, iterations),
        "startups": startups,
        "discoveries": discoveries,
        "raw_samples": samples,
        "failures": failures,
        "notes": [
            "Feuille vierge, profil et bus privés ; aucune donnée utilisateur ni capture.",
            "Sonde /usr/bin/python3, pyatspi système ; nouveau client par requête, "
            "même Calc entre itérations sans échec.",
            "Latences AT-SPI après connexion au bus ; ipc_ms inclut création du client "
            "et transport JSON.",
            "Recherche exacte sans menus ni cellules ; noms, rôles, états et rectangles "
            "écran conservés dans le JSON.",
            "À défaut de Sum/AutoSum, Select Function mesure le choix de fonction, "
            "pas un équivalent fonctionnel prouvé.",
            "Snapshot en largeur borné en profondeur/nœuds : "
            "pas la taille exhaustive du tableur virtuel.",
            "Temps vers bus/fenêtre depuis lancement Calc, polling 500 ms "
            "et démarrage du client inclus.",
            "A1 reçoit uniquement 424242 via xdotool ; lecture AT-SPI après Entrée, "
            "sans conserver d'autre valeur.",
            "Timeout RPC AT-SPI 1 500 ms (3 000 ms au démarrage RPC) ; "
            "requête subprocess et attente parent bornées.",
            "Après échec : nouvelle session entre itérations ; "
            "trois échecs de démarrage arrêtent la suite.",
        ],
    }
