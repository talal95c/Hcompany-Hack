import io
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

STATES = ("FOCUSED", "SELECTED", "CHECKED", "ENABLED", "EXPANDED", "SHOWING",
          "EDITABLE", "PRESSED", "BUSY")


@pytest.fixture
def bridge(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyatspi", SimpleNamespace(**{
        "STATE_" + name: i for i, name in enumerate(STATES)}))
    monkeypatch.setattr(sys, "stdin", io.StringIO())
    monkeypatch.setattr(subprocess, "check_output", lambda *a, **kw: "LibreOffice 7.3.7.2")
    namespace = {}
    path = Path(__file__).with_name("calc_a11y_bridge.py")
    exec(compile(path.read_text(), str(path), "exec"), namespace)
    namespace["frame"] = lambda _: SimpleNamespace(name="Calc")
    namespace["focused"] = lambda _: True
    namespace["node"] = lambda *_: {"bounds": {"x": 10, "y": 20, "w": 400, "h": 300}}
    return namespace


@pytest.mark.parametrize("point", [(0, 500), (1001, 500), (500, -1)])
def test_bridge_input_rejects_out_of_window_point(bridge, point, monkeypatch):
    sent = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: sent.append(a))
    bridge["handle"]({"app": "soffice", "op": "consent", "token": "confirmed"})
    bridge["handle"]({"app": "soffice", "op": "capture", "capture_id": "c"})
    with pytest.raises(ValueError):
        bridge["handle"]({"app": "soffice", "op": "input", "consent_token": "confirmed",
                          "capture_id": "c", "action": {
                              "type": "click", "button": "left", "x": point[0], "y": point[1]}})
    assert not sent


def test_bridge_input_consumes_capture_and_stop_revokes_consent(bridge, monkeypatch):
    sent = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: sent.append(args))
    bridge["handle"]({"app": "soffice", "op": "consent", "token": "confirmed"})
    bridge["handle"]({"app": "soffice", "op": "capture", "capture_id": "c"})
    request = {"app": "soffice", "op": "input", "consent_token": "confirmed",
               "capture_id": "c", "action": {
                   "type": "click", "button": "left", "x": 500, "y": 500}}
    assert bridge["handle"](request)["status"] == "ok"
    assert sent == [["xdotool", "mousemove", "210", "170", "click", "1"]]
    with pytest.raises(KeyError):
        bridge["handle"](request)
    bridge["handle"]({"app": "soffice", "op": "stop"})
    with pytest.raises(ValueError):
        bridge["handle"](request)


def test_bridge_a11y_set_value_uses_real_interface_and_validates_consent(bridge):
    values = []

    class Value:
        @property
        def currentValue(self):
            return values[-1]

        @currentValue.setter
        def currentValue(self, value):
            values.append(value)

    def no_editable():
        raise NotImplementedError

    accessible = SimpleNamespace(getRoleName=lambda: "table cell", queryEditableText=no_editable,
                                 queryValue=Value)
    bridge["refs"]["r"] = (accessible, "Calc")
    request = {"app": "soffice", "op": "action", "ref": "r", "action": "set_value",
               "value": "73", "consent_token": "confirmed"}
    with pytest.raises(ValueError):
        bridge["handle"](request)
    bridge["handle"]({"app": "soffice", "op": "consent", "token": "confirmed"})
    assert bridge["handle"](request)["complete"]
    assert values == [73]
    bridge["refs"]["r"] = (accessible, "Other document")
    with pytest.raises(ValueError):
        bridge["handle"](request)
