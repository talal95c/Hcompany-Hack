"""Tests live : appels réels H Company, Codiv, Gladia et Linkup ; écrivent results/*.json."""

from __future__ import annotations

import asyncio
import base64
import wave

import pytest

from engine.services.gladia import GladiaSttClient, decode_audio_chunk
from engine.services.holo import HoloCloudClient
from engine.services.jev import CodivJevClient
from engine.services.latency import LatencyRecorder
from engine.services.linkup import LinkupSearchClient
from engine.services.protocols import HoloAction, Intent

from .conftest import FIXTURES, RESULTS, contract_example, require_env, validate_contract

pytestmark = pytest.mark.live

SCREENSHOT = FIXTURES / "blender_4.5.9_layout_1600x900.png"
AUDIO = FIXTURES / "fr_ajoute_un_tore_16k.wav"
AUDIO_TEXT = "Ajoute un tore dans la scène Blender, puis ouvre le menu « Ajouter »."

# Boîtes de vérité terrain mesurées sur la capture 1600x900, normalisées [0, 1000].
HOLO_TARGETS: dict[str, tuple[int, int, int, int]] = {
    "the File menu in the top bar": (19, 4, 39, 27),
    "the Layout workspace tab": (175, 6, 206, 31),
    "the Add menu in the 3D viewport header": (164, 31, 188, 58),
    "the Object Mode dropdown": (30, 31, 103, 58),
    "the Cube item in the outliner": (866, 131, 906, 156),
    "the Move tool in the left toolbar": (7, 186, 28, 221),
    "the cube object in the 3D viewport": (371, 383, 457, 552),
    "the Scale X field in the properties panel": (906, 667, 964, 692),
    "the play animation button in the timeline": (415, 905, 438, 930),
}
HIT_TOLERANCE = 8
ADD_MENU = HOLO_TARGETS["the Add menu in the 3D viewport header"]

JEV_SENTENCES: list[tuple[str, Intent]] = [
    ("Pourquoi on utilise un tore ici ?", Intent.QUESTION),
    ("C'est quoi la différence entre un mesh et un objet ?", Intent.QUESTION),
    ("Comment je fais pour tourner la vue ?", Intent.QUESTION),
    ("À quoi sert le modificateur subdivision ?", Intent.QUESTION),
    ("Vas-y, fais-le toi-même.", Intent.FAIS_LE),
    ("Tu peux le faire à ma place ?", Intent.FAIS_LE),
    ("Montre-moi en le faisant, je n'y arrive pas.", Intent.FAIS_LE),
    ("Fais l'extrusion pour moi s'il te plaît.", Intent.FAIS_LE),
    ("Putain, ça marche pas !", Intent.FRUSTRATION),
    ("J'en ai marre, rien ne fonctionne.", Intent.FRUSTRATION),
    ("C'est super frustrant, j'ai encore tout cassé.", Intent.FRUSTRATION),
    ("Franchement ce logiciel me rend fou.", Intent.FRUSTRATION),
    ("Chut, laisse-moi réfléchir.", Intent.CHUT),
    ("Tais-toi s'il te plaît.", Intent.CHUT),
    ("Arrête de parler deux minutes.", Intent.CHUT),
    ("Silence, je me concentre.", Intent.CHUT),
    ("Je vais prendre un café.", Intent.OTHER),
    ("Il fait beau aujourd'hui.", Intent.OTHER),
    ("Hmm, voyons voir...", Intent.OTHER),
    ("Mon chat vient de sauter sur le clavier.", Intent.OTHER),
]


def _inside(x: float, y: float, box: tuple[int, int, int, int]) -> bool:
    x0, y0, x1, y1 = box
    t = HIT_TOLERANCE
    return x0 - t <= x <= x1 + t and y0 - t <= y <= y1 + t


async def test_holo_locates_blender_elements_and_acts() -> None:
    require_env("HAI_API_KEY")
    png = SCREENSHOT.read_bytes()
    rec = LatencyRecorder()
    rounds = 2
    results = []
    async with HoloCloudClient(recorder=rec) as holo:
        for _ in range(rounds):
            for target, box in HOLO_TARGETS.items():
                loc = await holo.locate_detailed(png, target)
                pointer = contract_example("commands", "pointer")
                pointer["payload"] = loc.pointer_payload("cap_live", 1)
                validate_contract("commands", pointer)
                results.append(
                    {
                        "target": target,
                        "x": loc.x,
                        "y": loc.y,
                        "confidence": loc.confidence,
                        "hit": _inside(loc.x, loc.y, box),
                    }
                )
        actions = []
        for _ in range(3):
            action = await holo.act(
                png,
                "Add a torus mesh to the scene",
                lesson_context="Blender 4.5.9, Object Mode, Layout workspace",
            )
            actions.append(action)
            if action.type != "done":
                cmd = contract_example("commands", "input.action")
                cmd["payload"] = action.input_action_payload("cap_live", "live-test")
                validate_contract("commands", cmd)
    hits = sum(r["hit"] for r in results)
    act_ok = [_first_step_ok(a) for a in actions]
    cached = [r.cached_tokens for r in rec.records if r.cached_tokens]
    rec.write_bench(
        RESULTS / "holo.json",
        extra={
            "model": "holo4-35b-a3b",
            "fixture": SCREENSHOT.name,
            "locate_hit_rate": round(hits / len(results), 3),
            "locate_results": results,
            "act_actions": [a.native() if a.type != "done" else {"type": "done"} for a in actions],
            "act_first_step_ok": act_ok,
            "cached_tokens_seen": bool(cached),
        },
    )
    assert hits / len(results) >= 0.75, results
    assert all(act_ok), actions


def _first_step_ok(action: HoloAction) -> bool:
    """Première étape plausible pour « ajouter un tore » : menu Add ou Shift+A."""
    if action.type == "click":
        assert action.x is not None and action.y is not None
        return _inside(action.x, action.y, ADD_MENU)
    return action.type == "key" and action.keys == ("shift", "a")


async def test_jev_classifies_twenty_french_sentences() -> None:
    require_env("CODIV_API_KEY")
    rec = LatencyRecorder()
    rows = []
    async with CodivJevClient(recorder=rec) as jev:
        http_version = await jev.warm_up()
        for text, expected in JEV_SENTENCES:
            decision = await jev.classify_intent(text, context="Leçon : ajouter un tore")
            rows.append(
                {
                    "text": text,
                    "expected": expected.value,
                    "choice": decision.choice,
                    "probability": round(decision.probability, 4),
                }
            )
        batched = []
        for state in (
            {
                "step": "add_torus",
                "idle_s": 75,
                "failed_attempts": 4,
                "recent_events": ["undo", "undo", "add cube", "delete"],
                "expected": "torus added",
                "observed": "no torus, cube deleted",
            },
            {
                "step": "add_torus",
                "idle_s": 6,
                "failed_attempts": 0,
                "recent_events": ["open Add menu"],
                "expected": "torus added",
                "observed": "torus added, rotated",
            },
            {
                "step": "add_torus",
                "idle_s": 20,
                "failed_attempts": 1,
                "recent_events": ["add uv sphere"],
                "expected": "torus added",
                "observed": "uv sphere instead",
            },
        ):
            out = await jev.assess(state)
            batched.append(
                {
                    q: {"choice": d.choice, "probability": round(d.probability, 4)}
                    for q, d in out.items()
                }
            )
    accuracy = sum(r["expected"] == r["choice"] for r in rows) / len(rows)
    rec.write_bench(
        RESULTS / "jev.json",
        extra={
            "model": "openjev-latest",
            "http_version": http_version,
            "timeout_ms": 800,
            "intent_accuracy": accuracy,
            "intent_results": rows,
            "batched_assessments": batched,
        },
    )
    assert http_version == "HTTP/2"
    assert accuracy >= 0.8, rows
    assert batched[0]["stuck_or_thinking"]["choice"] == "stuck"
    assert batched[1]["stuck_or_thinking"]["choice"] == "thinking"
    assert batched[0]["deviation"]["choice"] == "major"
    assert all(r.status == "ok" for r in rec.records)


def _normalize(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum() or c == " ")


async def test_gladia_file_and_live_transcription() -> None:
    require_env("GLADIA_API_KEY")
    rec = LatencyRecorder()
    audio = AUDIO.read_bytes()
    with wave.open(str(AUDIO)) as w:
        sample_rate, pcm = w.getframerate(), w.readframes(w.getnframes())
    async with GladiaSttClient(recorder=rec) as stt:
        files = [await stt.transcribe_file(audio, filename=AUDIO.name) for _ in range(3)]
        live_runs = []
        for _ in range(2):
            live_runs.append(await _stream(stt, pcm, sample_rate))
    for tr in files:
        norm = _normalize(tr.text)
        assert "tore" in norm and "blender" in norm, tr.text
        assert tr.words and all(w.end >= w.start for w in tr.words)
    for partials, finals in live_runs:
        assert partials, "aucun partiel"
        assert "blender" in _normalize(" ".join(finals)), finals
    rec.write_bench(
        RESULTS / "gladia.json",
        extra={
            "fixture": AUDIO.name,
            "fixture_audio_s": round(len(pcm) / 2 / sample_rate, 2),
            "reference_text": AUDIO_TEXT,
            "file_transcripts": [t.text for t in files],
            "file_words_first": [[w.word, w.start, w.end] for w in files[0].words[:4]],
            "live_finals": [f for _, f in live_runs],
            "live_partial_counts": [len(p) for p, _ in live_runs],
            "note": "live_final_after_last_chunk = délai entre le dernier chunk audio envoyé "
            "(audio temps réel, 1 s de silence final) et la réception du final",
        },
    )


async def _stream(
    stt: GladiaSttClient, pcm: bytes, sample_rate: int
) -> tuple[list[str], list[str]]:
    session = await stt.open_live(sample_rate=sample_rate, endpointing_s=0.3)
    step = sample_rate * 2 // 10
    chunks = [pcm[i : i + step] for i in range(0, len(pcm), step)] + [b"\x00\x00" * sample_rate]

    async def feed() -> None:
        for seq, chunk in enumerate(chunks):
            msg = contract_example("desktop-ws", "audio.chunk")
            msg["payload"] = {
                "utterance_id": "u_live",
                "sequence": seq,
                "encoding": "pcm_s16le",
                "sample_rate": sample_rate,
                "data_base64": base64.b64encode(chunk).decode(),
            }
            validate_contract("desktop-ws", msg)
            await session.send_audio(decode_audio_chunk(msg, sample_rate=sample_rate))
            await asyncio.sleep(0.1)
        await asyncio.sleep(1.5)
        await session.stop()

    feeder = asyncio.create_task(feed())
    partials: list[str] = []
    finals: list[str] = []
    try:
        async with asyncio.timeout(40):
            async for ev in session.events():
                if ev.kind == "partial":
                    partials.append(ev.text)
                elif ev.kind == "final":
                    finals.append(ev.text)
                elif ev.kind == "error":
                    pytest.fail(ev.text)
    finally:
        await feeder
        await session.aclose()
    return partials, finals


async def test_linkup_returns_blender_docs() -> None:
    require_env("LINKUP_API_KEY")
    rec = LatencyRecorder()
    queries = [
        "How do I add a torus mesh in Blender 4.5?",
        "Blender 4.5 extrude faces shortcut in Edit Mode",
        "Blender 4.5 Subdivision Surface modifier levels viewport",
    ]
    rows = []
    async with LinkupSearchClient(recorder=rec) as lk:
        for q in queries:
            res = await lk.search(q)
            rows.append(
                {
                    "query": q,
                    "answer": res.answer,
                    "data": dict(res.data or {}),
                    "sources": [s.url for s in res.sources[:5]],
                }
            )
            assert res.answer
            assert res.sources and all("docs.blender.org" in s.url for s in res.sources)
    rec.write_bench(RESULTS / "linkup.json", extra={"depth": "standard", "results": rows})
    assert "torus" in (rows[0]["answer"] or "").lower()
