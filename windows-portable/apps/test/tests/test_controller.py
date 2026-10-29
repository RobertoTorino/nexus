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
    assert pane.count.text() == f"2 of {len(BUTTONS) - 1} buttons answered"       # no M1/M2 without the ASUS channel


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


def test_it_says_where_the_back_buttons_come_from(qapp):
    pane = ControllerPane(clock=Clock())
    assert pane.back_buttons.title == "The back buttons M1 and M2" and "reports none" in pane.back_buttons.info
    pane.set_back_buttons(True)
    assert "Armoury Crate" in pane.back_buttons.info and pane.count.text() == f"0 of {len(BUTTONS)} buttons answered"
    pane.start()
    assert pane.back_buttons.isHidden()                         # every button is the test's: no popup meanwhile
    pane.finish()
    assert not pane.back_buttons.isHidden()


def test_finish_and_the_pads_name(qapp):
    """finish() ends a running test (B held, Escape, or a tap on the legend's "B Hold to finish"); the pane has no
    pill of its own (owner, 29-10-2026: every action in the row at the bottom)."""
    pane = ControllerPane(clock=Clock())
    finished = []
    pane.finished.connect(lambda: finished.append(True))
    pane.finish()                                           # not running: nothing
    pane.start()
    pane.finish()
    assert finished == [True] and not hasattr(pane, "finish_pill")
    pane.set_pads([])
    assert "No controller found" in pane.name.text()
    pane.set_pads(["ASUSTeK Computer Inc."])
    assert pane.name.text() == "ASUSTeK Computer Inc."
