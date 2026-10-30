# SPDX-License-Identifier: GPL-3.0-or-later
"""The portable window's controller (gamepad.py): the window's actions, a held direction that repeats, the stick's
dead zone, every control as it is for a controller test, and no controller at all."""

from __future__ import annotations

from bc250_core.gamepad import DEADZONE, FIRST_REPEAT, REPEAT, Gamepad, stick_direction


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class FakePad:
    def __init__(self):
        self.queue: list[tuple[str, str, float | bool]] = []
        self.closed = False

    def names(self) -> list[str]:
        return ["ASUSTeK Computer Inc."]

    def events(self):
        found, self.queue = self.queue, []
        return found

    def close(self) -> None:
        self.closed = True


def started(qapp, pad: FakePad, clock: Clock) -> tuple[Gamepad, list[str], list[tuple]]:
    gamepad = Gamepad(source_factory=lambda: pad, clock=clock)
    actions: list[str] = []
    raw: list[tuple] = []
    gamepad.action.connect(actions.append)
    gamepad.raw.connect(lambda *event: raw.append(event))
    assert gamepad.start() and gamepad.names() == ["ASUSTeK Computer Inc."]
    return gamepad, actions, raw


def test_the_buttons_the_window_acts_on(qapp):
    pad, clock = FakePad(), Clock()
    gamepad, actions, _ = started(qapp, pad, clock)
    for name in ("a", "b", "x", "y", "leftshoulder", "rightshoulder", "start", "back", "guide", "leftstick"):
        pad.queue += [("button", name, True), ("button", name, False)]
    gamepad.poll()
    assert actions == ["accept", "back", "x", "y", "previous", "next", "menu", "view"]   # guide, stick: no action
    gamepad.stop()
    assert pad.closed


def test_a_held_direction_repeats(qapp):
    pad, clock = FakePad(), Clock()
    gamepad, actions, _ = started(qapp, pad, clock)
    pad.queue.append(("button", "dpad_down", True))
    gamepad.poll()
    assert actions == ["down"]
    clock.now = FIRST_REPEAT - 0.01
    gamepad.poll()
    assert actions == ["down"]
    clock.now = FIRST_REPEAT + 0.01
    gamepad.poll()
    clock.now += REPEAT
    gamepad.poll()
    assert actions == ["down"] * 3
    pad.queue.append(("button", "dpad_down", False))
    clock.now += 5
    gamepad.poll()
    assert actions == ["down"] * 3
    gamepad.stop()


def test_the_left_stick_moves_the_right_stick_does_not(qapp):
    pad, clock = FakePad(), Clock()
    gamepad, actions, raw = started(qapp, pad, clock)
    pad.queue += [("axis", "leftx", 0.9), ("axis", "leftx", 0.0), ("axis", "rightx", 0.9), ("axis", "lefty", -0.2)]
    gamepad.poll()
    assert actions == ["right"]
    assert [event[1] for event in raw] == ["leftx", "leftx", "rightx", "lefty"]
    gamepad.stop()


def test_every_control_as_it_is(qapp):
    """For the controller test: buttons pressed and let go, the sticks from -1 to 1, the triggers from 0 to 1."""
    pad, clock = FakePad(), Clock()
    gamepad, _, raw = started(qapp, pad, clock)
    pad.queue += [("button", "guide", True), ("axis", "righty", -0.5), ("axis", "lefttrigger", 1.0),
                  ("axis", "righttrigger", -0.2), ("removed", "", False), ("added", "", True)]
    gamepad.poll()
    assert raw == [("button", "guide", True), ("axis", "righty", -0.5), ("axis", "lefttrigger", 1.0),
                   ("axis", "righttrigger", 0.0), ("removed", "", False), ("added", "", True)]
    gamepad.stop()


def test_rt_pulled_is_one_press(qapp):
    """RT is the portal's Steam (owner, 30-10-2026): past halfway it is pressed, once, until it is let go (under 0.3);
    LT does nothing yet."""
    pad, clock = FakePad(), Clock()
    gamepad, actions, _ = started(qapp, pad, clock)
    pad.queue += [("axis", "righttrigger", 0.4), ("axis", "righttrigger", 0.6), ("axis", "righttrigger", 1.0),
                  ("axis", "righttrigger", 0.4), ("axis", "righttrigger", 0.9), ("axis", "lefttrigger", 1.0)]
    gamepad.poll()
    assert actions == ["rt"]                            # 0.4 on the way back is not a release
    pad.queue += [("axis", "righttrigger", 0.1), ("axis", "righttrigger", 0.7)]
    gamepad.poll()
    assert actions == ["rt", "rt"]
    pad.queue += [("removed", "", False), ("axis", "righttrigger", 0.8)]
    gamepad.poll()
    assert actions == ["rt", "rt", "rt"]               # a pad unplugged with RT held: the next pull counts
    gamepad.stop()


def test_an_unplugged_pad_stops_a_held_direction(qapp):
    pad, clock = FakePad(), Clock()
    gamepad, actions, _ = started(qapp, pad, clock)
    pad.queue += [("button", "dpad_up", True), ("removed", "", False)]
    gamepad.poll()
    clock.now = 5
    gamepad.poll()
    assert actions == ["up"]
    gamepad.stop()


def test_stick_direction():
    assert stick_direction(0.0, 0.0) is None and stick_direction(DEADZONE - 0.01, 0.0) is None
    assert stick_direction(0.9, 0.3) == "right" and stick_direction(-0.9, 0.3) == "left"
    assert stick_direction(0.3, 0.9) == "down" and stick_direction(0.3, -0.9) == "up"


def test_without_pygame_or_a_controller(qapp):
    def missing():
        raise ImportError("No module named 'pygame'")
    gamepad = Gamepad(source_factory=missing)
    assert not gamepad.start() and gamepad.names() == []
    gamepad.poll()                                              # nothing happens
    gamepad.stop()
