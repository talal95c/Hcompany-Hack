import json

import pytest

from engine.learner import LearnerMemory


def test_srs_persistence_and_delegation(tmp_path):
    path = tmp_path / "profile.json"
    memory = LearnerMemory(path)
    assert memory.skills == {}
    assert not memory.can_delegate("mesh", confirmed=False, wants_to_learn=False)
    assert memory.can_delegate("mesh", confirmed=True, wants_to_learn=False)
    assert not memory.can_delegate("mesh", confirmed=True, wants_to_learn=True)
    skill = memory.review("mesh", passed=True, help_level=2, now=0)
    assert not skill.unlocked
    skill = memory.review("mesh", passed=True, help_level=0, challenge=True, now=100)
    assert skill.unlocked and skill.successes_without_help == 1
    assert skill.interval == 6 and skill.due_at == 100 + 6 * 86400
    assert memory.can_delegate("mesh", confirmed=True, wants_to_learn=True)
    assert LearnerMemory(path).skills == memory.skills
    memory.review("mesh", passed=False, help_level=4, now=200)
    assert skill.interval == 1 and skill.max_help_level_used == 4
    assert not list(tmp_path.glob(".learner-*"))
    with pytest.raises(ValueError):
        memory.review("mesh", passed=True, help_level=5)


@pytest.mark.parametrize("data", ["{", "[]", '{"mesh":{"ease":0}}'])
def test_corrupt_backup(tmp_path, caplog, data):
    path = tmp_path / "profile.json"
    path.write_text(data)
    assert LearnerMemory(path).skills == {}
    assert not path.exists()
    assert next(tmp_path.glob("*.corrupt-*")).read_text() == data
    assert "corrompue" in caplog.text


def test_atomic_replace_failure_preserves_old(tmp_path, monkeypatch):
    memory = LearnerMemory(tmp_path / "profile.json")
    memory.review("a", passed=True, help_level=0)
    before = json.loads(memory.path.read_text())

    def fail(*args):
        raise OSError("disque indisponible")

    monkeypatch.setattr("engine.learner.os.replace", fail)
    with pytest.raises(OSError):
        memory.review("b", passed=True, help_level=1)
    assert json.loads(memory.path.read_text()) == before
    assert not list(tmp_path.glob(".learner-*"))
