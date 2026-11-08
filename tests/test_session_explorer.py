import runpy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "h-tutor/tools/session_explorer.py"


@pytest.fixture(scope="module")
def explorer():
    return runpy.run_path(str(SCRIPT))


def test_empty_session_pages(explorer, tmp_path):
    session = explorer["Session"]("empty", tmp_path, {}, {}, [])
    session.stats = explorer["compute_stats"](session)
    assert "Rio sessions" in explorer["build_index"]([])
    assert "No events." in explorer["build_session"](session, "../index.html")
    assert session.stats["steps"] == 0


def test_session_pages_escape_learner_content(explorer, tmp_path):
    session = explorer["Session"](
        "example",
        tmp_path,
        {"title": "<private title>", "outcome": "completed"},
        {"milestones": [{"id": "m1", "goal": "Make a chart", "done_when": "Chart visible"}]},
        [
            {"type": "milestone_start", "milestone": "m1", "goal": "Make a chart"},
            {
                "type": "step",
                "milestone": "m1",
                "action": {"name": "click", "args": {"instruction": "<click here>"}},
                "reasoning": "<reasoning>",
            },
            {"type": "ask_learner", "question": "<question>", "options": ["<option>"]},
            {"type": "milestone_done", "milestone": "m1", "evidence": "Chart visible", "t": 1.0},
        ],
    )
    session.stats = explorer["compute_stats"](session)
    index = explorer["build_index"]([session])
    page = explorer["build_session"](session, "../index.html")
    assert "&lt;private title&gt;" in index
    assert "&lt;click here&gt;" in page
    assert "&lt;reasoning&gt;" in page
    assert "&lt;question&gt;" in page
    assert "&lt;option&gt;" in page
    assert "Milestone done" in page


def test_missing_and_malformed_session_data(explorer, tmp_path):
    path = tmp_path / "events.jsonl"
    assert explorer["read_json"](path, {}) == {}
    assert explorer["read_events"](path) == []
    path.write_text('not json\n{"type": "learner_question"}\n', encoding="utf-8")
    assert explorer["read_json"](path, {}) == {}
    assert explorer["read_events"](path) == [{"type": "learner_question"}]


@pytest.mark.parametrize("response", ["<response>", {"text": "<response>"}, None])
def test_model_response_rendering(explorer, response):
    page = explorer["model_call_html"]({"response": response}, "Model call")
    assert "<summary>Response</summary>" in page
    assert "<response>" not in page
