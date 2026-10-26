# SPDX-License-Identifier: GPL-3.0-or-later
"""The controller test (controller.py): buttons held and answered, the sticks and triggers, and the ways out:
holding B, the Finish pill."""

from __future__ import annotations

from bc250_core.portable import AMBER
from portable_test.controller import BUTTONS, HOLD, ControllerPane


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_buttons_light_while_held_and_stay_answered(qapp):
    pane = ControllerPane(clock=Clock())
    pane.start()
    pane.feed("button", "x", True)
    assert pane.chips["x"].held and f"background: {AMBER}" in pane.chips["x"].styleSheet()
    pane.feed("button", "x", False)
    assert not pane.chips["x"].held and pane.chips["x"].seen and f"color: {AMBER}" in pane.chips["x"].styleSheet()
    pane.feed("button", "a", True)
    assert pane.seen() == ["x", "a"] or pane.seen() == ["a", "x"]
    assert pane.count.text() == f"2 of {len(BUTTONS)} buttons answered"


def test_sticks_and_triggers(qapp):
    pane = ControllerPane(clock=Clock())
    pane.start()
    pane.feed("axis", "leftx", 0.5)
    pane.feed("axis", "righty", -1.0)
    pane.feed("axis", "lefttrigger", 0.25)
    pane.feed("button", "rightstick", True)
    assert (pane.sticks["left"].x, pane.sticks["right"].y) == (0.5, -1.0) and pane.sticks["right"].pressed
    assert pane.triggers["lefttrigger"].value == 0.25


def test_nothing_counts_before_the_start_and_a_new_start_resets(qapp):
    pane = ControllerPane(clock=Clock())
    pane.feed("button", "a", True)
    assert pane.seen() == []
    pane.start()
    pane.feed("button", "a", True)
    pane.start()
    assert pane.seen() == []


def test_holding_b_finishes(qapp):
    clock = Clock()
    pane = ControllerPane(clock=clock)
    finished = []
    pane.finished.connect(lambda: finished.append(True))
    pane.start()
    pane.feed("button", "b", True)
    clock.now = HOLD - 0.1
    pane.check_hold()
    assert finished == [] and pane.running
    pane.feed("button", "b", False)                         # let go too soon: B was only tested
    clock.now = 10
    pane.check_hold()
    assert finished == [] and pane.chips["b"].seen
    pane.feed("button", "b", True)
    clock.now = 10 + HOLD
    pane.check_hold()
    assert finished == [True] and not pane.running


def test_the_finish_pill_and_the_pads_name(qapp):
    pane = ControllerPane(clock=Clock())
    finished = []
    pane.finished.connect(lambda: finished.append(True))
    pane.finish()                                           # not running: nothing
    pane.start()
    pane.finish_pill.click()
    assert finished == [True]
    pane.set_pads([])
    assert "No controller found" in pane.name.text()
    pane.set_pads(["ASUSTeK Computer Inc."])
    assert pane.name.text() == "ASUSTeK Computer Inc."
