# SPDX-License-Identifier: GPL-3.0-or-later
"""A controller's touchpad as the mouse (owner, 05-11-2026), the virtual mouse it moves, and an app that runs
brought to the front through KWin."""

from __future__ import annotations

import json
import struct

from bc250_portal import kwin, pointer
from bc250_portal.gamepad import TOUCH_ASPECT, TOUCH_SPEED, Gamepad


class FakePad:
    def __init__(self):
        self.queue = []

    def events(self):
        out, self.queue = self.queue, []
        return out

    def close(self):
        pass


def test_a_finger_moves_the_pointer_and_a_press_clicks(qapp):
    pad = FakePad()
    gamepad = Gamepad(source_factory=lambda: pad, clock=lambda: 0.0)
    moves, presses, actions = [], [], []
    gamepad.pointer_moved.connect(lambda dx, dy: moves.append((round(dx, 3), round(dy, 3))))
    gamepad.pointer_pressed.connect(lambda right, down: presses.append((right, down)))
    gamepad.action.connect(actions.append)
    assert gamepad.start()
    pad.queue = [("touch", "down", (0, 0.5, 0.5))]
    gamepad.poll()
    assert moves == []                                  # a finger put down does not move the pointer
    pad.queue = [("touch", "motion", (0, 0.6, 0.5)), ("touch", "motion", (0, 0.6, 0.4))]
    gamepad.poll()
    assert moves == [(round(0.1 * TOUCH_SPEED, 3), round(-0.1 * TOUCH_SPEED * TOUCH_ASPECT, 3))]   # once a poll
    pad.queue = [("button", "touchpad", True), ("button", "touchpad", False)]
    gamepad.poll()
    assert presses == [(False, True), (False, False)]
    pad.queue = [("touch", "down", (1, 0.2, 0.2)), ("touch", "motion", (1, 0.3, 0.2)),   # a second finger: no move,
                 ("button", "touchpad", True), ("touch", "up", (1, 0.3, 0.2)),        # and a right click, released
                 ("button", "touchpad", False)]                                      # as right
    gamepad.poll()
    assert len(moves) == 1 and presses[2:] == [(True, True), (True, False)]
    assert actions == []                                # the touchpad is no action of the view
    gamepad.stop()


def test_the_virtual_mouse_sends_whole_pixels_and_fails_quietly(tmp_path):
    mouse = pointer.VirtualMouse(str(tmp_path / "no-uinput"))
    mouse.move(5, 0)                                    # no device: nothing happens, no error
    assert mouse.failed and mouse.fd is None
    sent = []
    mouse._send = lambda *events: sent.append(events)
    mouse.move(0.6, 0.0)
    mouse.move(0.6, -1.5)
    assert sent == [((pointer.EV_REL, pointer.REL_X, 1), (pointer.EV_REL, pointer.REL_Y, -1))]
    mouse.press(pointer.BTN_LEFT, True)
    assert sent[-1] == ((pointer.EV_KEY, pointer.BTN_LEFT, 1),)
    mouse.close()
    assert struct.calcsize("HHHH80sI") == 92 and pointer.UI_DEV_SETUP >> 16 & 0x3FFF == 92    # uinput_setup's size


def test_kwin_is_asked_to_bring_the_apps_window_forward(tmp_path):
    calls = []

    def call(path, interface, method, arguments):
        calls.append((path, method, arguments))
        return [7] if method == "loadScript" else []
    file = tmp_path / "raise.js"
    assert kwin.Raiser(call, file).bring_to_front(["bc250-governor-manager"], [4242])
    assert [(path, method) for path, method, _ in calls] == [
        ("/Scripting", "unloadScript"), ("/Scripting", "loadScript"), ("/Scripting/Script7", "run")]
    assert calls[1][2] == [str(file), kwin.PLUGIN]
    script = file.read_text()
    assert f"const ids = {json.dumps(['bc250-governor-manager'])}, pids = [4242];" in script
    assert "workspace.activeWindow = w" in script and "w.minimized = false" in script


def test_without_kwin_nothing_happens(tmp_path):
    def refuse(*_args):
        raise kwin.KWinError("org.freedesktop.DBus.Error.ServiceUnknown")
    assert not kwin.Raiser(refuse, tmp_path / "raise.js").bring_to_front(["x"])
    assert not kwin.Raiser(lambda *a: [-1] if a[2] == "loadScript" else [], tmp_path / "r.js").bring_to_front(["x"])
    kwin.Raiser(refuse).close()


def test_pygame_ces_touch_events_are_read_with_their_finger_id(qapp):
    """pygame-ce names the finger finger_id (a DualShock 4 on the owner's board, 05-11-2026: 'finger' crashed the
    reader at the first touch); the touchpad's press is SDL's button 20."""
    from types import SimpleNamespace

    from bc250_portal.gamepad import TOUCHPAD_BUTTON, PygameSource
    kinds = SimpleNamespace(CONTROLLERDEVICEADDED=1, CONTROLLERDEVICEREMOVED=2, CONTROLLERBUTTONDOWN=3,
                            CONTROLLERBUTTONUP=4, CONTROLLERAXISMOTION=5, CONTROLLERTOUCHPADDOWN=6,
                            CONTROLLERTOUCHPADMOTION=7, CONTROLLERTOUCHPADUP=8)
    queue = [SimpleNamespace(type=6, instance_id=0, touch_id=0, finger_id=0, x=0.6, y=0.9, pressure=1.0),
             SimpleNamespace(type=7, instance_id=0, touch_id=0, finger_id=1, x=0.5, y=0.5, pressure=1.0),
             SimpleNamespace(type=3, button=TOUCHPAD_BUTTON)]
    kinds.event = SimpleNamespace(get=lambda: queue)
    source = PygameSource.__new__(PygameSource)
    source.pygame, source.buttons, source.axes = kinds, {TOUCHPAD_BUTTON: "touchpad"}, {}
    source.touches = {6: "down", 7: "motion", 8: "up"}
    assert source.events() == [("touch", "down", (0, 0.6, 0.9)), ("touch", "motion", (1, 0.5, 0.5)),
                               ("button", "touchpad", True)]
