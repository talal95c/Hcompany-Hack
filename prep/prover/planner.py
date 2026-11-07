"""Transitions explicites du planificateur de préparation."""

from enum import StrEnum


class Mode(StrEnum):
    EXECUTE = "EXECUTE"
    REPLAY = "REPLAY"
    EXPLORE = "EXPLORE"
    OBSERVE = "OBSERVE"
    CONSOLIDATE = "CONSOLIDATE"
    HANDOFF = "HANDOFF"


TRANSITIONS = {
    (Mode.EXECUTE, "success"): Mode.CONSOLIDATE,
    (Mode.EXECUTE, "divergence"): Mode.EXPLORE,
    (Mode.REPLAY, "success"): Mode.CONSOLIDATE,
    (Mode.REPLAY, "failure"): Mode.EXPLORE,
    (Mode.EXPLORE, "success"): Mode.CONSOLIDATE,
    (Mode.EXPLORE, "stuck"): Mode.OBSERVE,
    (Mode.OBSERVE, "candidate"): Mode.EXECUTE,
    (Mode.OBSERVE, "no_check"): Mode.HANDOFF,
    (Mode.CONSOLIDATE, "next_replay"): Mode.REPLAY,
    (Mode.CONSOLIDATE, "next_execute"): Mode.EXECUTE,
    (Mode.HANDOFF, "reviewed_and_tested"): Mode.EXECUTE,
}


def next_mode(mode: Mode, event: str) -> Mode:
    try:
        return TRANSITIONS[mode, event]
    except KeyError:
        raise ValueError(f"Transition interdite : {mode} / {event}") from None
