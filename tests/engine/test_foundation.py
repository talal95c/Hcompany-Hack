import json
from pathlib import Path

import pytest
from jsonschema import ValidationError

from engine.bus import EventBus, Topic
from engine.bus.validation import validate
from engine.config import EngineConfig
from engine.interfaces import FakeClock, LocalizeResult
from engine.lesson import Session, load_lesson

ROOT = Path(__file__).resolve().parents[2]


def test_config(monkeypatch, caplog):
    monkeypatch.delenv("ENGINE_SESSION_TOKEN", raising=False)
    config = EngineConfig.from_env()
    assert config.port == config.addon_port == config.debug_port == 0
    assert config.session_token not in repr(config)
    assert config.session_token not in caplog.text
    monkeypatch.setenv("ENGINE_PORT", "70000")
    with pytest.raises(ValueError):
        EngineConfig.from_env()


def test_clock_and_coordinates():
    clock = FakeClock()
    clock.advance(20)
    assert clock.monotonic() == 20
    with pytest.raises(ValueError):
        clock.advance(-1)
    assert LocalizeResult(0, 1000, None, 0).y == 1000
    with pytest.raises(ValueError):
        LocalizeResult(-1, 0, None, 0)


async def test_bus():
    reports = []
    bus = EventBus(1, reports.append)
    queue = bus.subscribe(Topic.EVENT)
    await bus.publish(Topic.COMMAND, "sans abonné")
    assert queue.empty()
    await bus.publish(Topic.EVENT, 1)
    await bus.publish(Topic.EVENT, 2)
    assert await queue.get() == 2
    assert bus.dropped == len(reports) == 1
    bus.unsubscribe(Topic.EVENT, queue)
    with pytest.raises(ValueError):
        EventBus(0)


def test_validation_references():
    example = ROOT / "contracts/examples/desktop-ws/valid/command.json"
    message = json.loads(example.read_text())
    validate("desktop-ws", message)
    message["payload"]["type"] = "inconnu"
    with pytest.raises(ValidationError):
        validate("desktop-ws", message)


def lesson_path():
    return next((ROOT / "contracts/examples/lesson/valid").glob("*.json"))


def test_lesson(tmp_path):
    lesson = load_lesson(lesson_path())
    session = Session("s1", lesson)
    assert not session.observe("invalide")
    assert session.observe(session.step["preconditions"]["mode"])
    with pytest.raises(ValueError):
        session.transition("COMPLETE")
    session.transition("CHECKING")
    session.transition("PASSED")
    assert session.advance(0)
    assert not session.advance(0)
    assert not session.accept(0)
    session.resync()
    assert session.generation == 2
    lesson["status"] = "draft"
    path = tmp_path / "lesson.json"
    path.write_text(json.dumps(lesson))
    with pytest.raises(ValueError):
        load_lesson(path)
    assert load_lesson(path, allow_unproven=True)["status"] == "draft"
    lesson["schema_version"] = "2.0"
    path.write_text(json.dumps(lesson))
    with pytest.raises(ValidationError):
        load_lesson(path, allow_unproven=True)
