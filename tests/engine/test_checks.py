import pytest

from engine.checks import SceneState, evaluate, progress_signature


def snapshot(objects=None, revision=1):
    state = SceneState()
    state.apply({"type": "snapshot", "scene_revision": revision, "payload": {
        "mode": "OBJECT", "active": None, "objects": objects or [],
    }})
    return state


@pytest.mark.parametrize("name,params,obj", [
    ("object_exists", {"type": "MESH", "primitive": "torus"},
     {"type": "MESH", "primitive_provenance": "torus",
                       "mesh": {"verts": 576, "edges": 1152, "polys": 576}}),
    ("object_count", {"type": "MESH", "count": 1}, {"type": "MESH"}),
    ("modifier_present", {"modifier_type": "SUBSURF", "params": {"levels": 2}},
     {"modifiers": [{"type": "SUBSURF", "levels": 2}]}),
    ("material_color", {"color": [1, 0, 0, 1]}, {"materials": [{"base_color": [1, 0, 0, 1]}]}),
    ("shading_smooth", {}, {"mesh": {"shading_smooth": True}}),
    ("object_transform", {"location": [0, 0, 0], "scale": [1, 1, 1]},
     {"location": [0, 0, 0], "scale": [1, 1, 1]}),
])
def test_checks_nominal_empty_unknown(name, params, obj):
    assert evaluate(name, snapshot([{"id": "a", **obj}]), params).status == "pass"
    assert evaluate(name, snapshot(), params).status == "fail"
    assert evaluate(name, SceneState(), params).status == "unknown"


@pytest.mark.parametrize("name,params", [
    ("object_exists", {"type": "MESH", "primitive": "torus"}),
    ("modifier_present", {"modifier_type": "SUBSURF"}),
    ("material_color", {"color": [1, 0, 0, 1]}),
    ("shading_smooth", {}), ("object_transform", {"location": [0, 0, 0]}),
])
def test_missing_property_not_proof(name, params):
    assert evaluate(name, snapshot([{"id": "a", "type": "MESH", "name": "Torus"}]),
                    params).status == "unknown"


def test_checks_fail_tolerance_and_registry():
    state = snapshot([{"id": "a", "type": "MESH", "primitive_provenance": "cube",
                      "mesh": {"verts": 8, "edges": 12, "polys": 6},
                       "location": [0.001, 0, 0], "modifiers": [], "materials": [],
                       "shading_smooth": False}])
    for name, params in [
        ("object_exists", {"primitive": "torus"}),
        ("modifier_present", {"modifier_type": "SUBSURF"}),
        ("material_color", {"color": [1, 0, 0, 1]}),
        ("shading_smooth", {}), ("object_transform", {"location": [0, 0, 0]}),
    ]:
        assert evaluate(name, state, params).status == "fail"
    assert evaluate("object_transform", state, {"location": [0, 0, 0],
                                               "tolerance": 0.01}).status == "pass"
    with pytest.raises(ValueError):
        evaluate("arbitrary", state, {})
    with pytest.raises(ValueError):
        evaluate("object_transform", state, {"tolerance": -1})


def test_scene_deltas_selection_mode_and_staleness():
    state = snapshot([{"id": "a", "type": "MESH", "primitive_provenance": "torus",
                       "mesh": {"verts": 576, "edges": 1152, "polys": 576}}])
    params = {"type": "MESH", "primitive": "torus"}
    before = progress_signature("object_exists", state, params)
    assert evaluate("selection", state, params).status == "unknown"
    state.apply({"type": "selection.changed", "scene_revision": 1,
                 "payload": {"selected_ids": ["a"], "active": "a"}})
    assert evaluate("selection", state, params).status == "pass"
    assert evaluate("selection", state, {**params, "active": True}).status == "pass"
    assert before == progress_signature("object_exists", state, params)
    state.apply({"type": "mode.changed", "scene_revision": 1,
                 "payload": {"current": "EDIT_MESH"}})
    assert evaluate("mode_is", state, {"mode": "EDIT_MESH"}).status == "pass"
    state.apply({"type": "scene.changed", "scene_revision": 2,
                 "payload": {"changed_ids": ["a"], "objects": []}})
    assert evaluate("object_exists", state, params).status == "fail"
    state.apply({"type": "scene.changed", "scene_revision": 4,
                 "payload": {"changed_ids": [], "objects": []}})
    assert not state.recent
    state.apply({"type": "snapshot", "scene_revision": 3,
                 "payload": {"mode": "OBJECT", "active": None, "objects": []}})
    assert state.revision == 4
    assert evaluate("object_exists", state, params).status == "unknown"


def test_latest_event_revision_requires_updated_state():
    state = snapshot()
    state.apply({"type": "heartbeat", "scene_revision": 2, "payload": {}})
    assert not state.recent
    assert evaluate("mode_is", state, {"mode": "OBJECT"}).status == "unknown"


def test_incomplete_objects_and_selection_empty():
    state = snapshot([{}])
    assert not state.recent
    state = snapshot()
    state.apply({"type": "selection.changed", "scene_revision": 1,
                 "payload": {"selected_ids": [], "active": None}})
    assert evaluate("selection", state, {"type": "MESH"}).status == "fail"
    assert evaluate("selection", state, {"active": True}).status == "fail"
    state.apply({"type": "mode.changed", "scene_revision": 10,
                 "payload": {"current": "OBJECT"}})
    assert not state.recent


@pytest.mark.parametrize("mesh,expected", [
    (None, "unknown"),
    ([], "unknown"),
    ({"verts": 8, "polys": 6}, "unknown"),
    ({"verts": 8, "edges": 12, "polys": 6}, "fail"),
    ({"verts": 576, "polys": 576}, "unknown"),
    ({"verts": 576, "edges": 1153, "polys": 576}, "fail"),
    ({"verts": 576, "edges": 1152, "polys": 576}, "pass"),
    ({"verts": 9, "edges": 18, "polys": 9}, "pass"),
    ({"verts": True, "edges": 2, "polys": 1}, "unknown"),
])
def test_primitive_requires_provenance_and_geometry(mesh, expected):
    obj = {"id": "a", "type": "MESH", "primitive_provenance": "torus", "mesh": mesh}
    assert evaluate("object_exists", snapshot([obj]), {"primitive": "torus"}).status == expected
    obj.pop("primitive_provenance")
    assert evaluate("object_exists", snapshot([obj]), {"primitive": "torus"}).status == "unknown"
