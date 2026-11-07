# SPDX-License-Identifier: AGPL-3.0-or-later
"""The controllers on the board: SDL's buttons, axes and touchpad fingers as the console's controller state (the
reference's mapping), several controllers combined, the motion fed to each controller's orientation tracker, and
the reader thread against a stand-in for SDL (fake_gamepad.py). One test opens the real SDL3 where it is installed;
the tracker itself is tested against the reference's vectors in test_native.py."""

from __future__ import annotations

import ctypes.util
import threading
import time

import pytest

from consoles_link import gamepad
from consoles_link.gamepad import Reading, Touches, controller_state
from fake_gamepad import FakePad, FakeSdl, FakeTracker


def state(*readings: Reading, ps5: bool = False, touches: Touches | None = None) -> dict:
    return controller_state(dict(enumerate(readings)), touches or Touches(), ps5)


def test_idle():
    assert state(Reading()) == {"buttons": 0, "l2": 0, "r2": 0, "left": (0, 0), "right": (0, 0), "touches": []}
    assert state() == state(Reading())


@pytest.mark.parametrize("button, expected", [
    (gamepad.SOUTH, 1 << 0), (gamepad.EAST, 1 << 1), (gamepad.WEST, 1 << 2), (gamepad.NORTH, 1 << 3),
    (gamepad.DPAD_LEFT, 1 << 4), (gamepad.DPAD_RIGHT, 1 << 5), (gamepad.DPAD_UP, 1 << 6), (gamepad.DPAD_DOWN, 1 << 7),
    (gamepad.LEFT_SHOULDER, 1 << 8), (gamepad.RIGHT_SHOULDER, 1 << 9), (gamepad.LEFT_STICK, 1 << 10),
    (gamepad.RIGHT_STICK, 1 << 11), (gamepad.START, 1 << 12), (gamepad.BACK, 1 << 13), (gamepad.TOUCHPAD, 1 << 14),
    (gamepad.GUIDE, 1 << 15),
    (15, 0), (16, 0), (19, 0),                          # misc (a microphone button) and paddles: not used
])
def test_buttons_as_the_reference_maps_them(button, expected):
    assert state(Reading(buttons=frozenset({button})))["buttons"] == expected


def test_axes():
    s = state(Reading(axes=(-32768, 32767, 100, -100, 32767, 128)))
    assert (s["left"], s["right"], s["l2"], s["r2"]) == ((-32768, 32767), (100, -100), 255, 1)


def test_several_controllers_combine():
    a = Reading(buttons=frozenset({gamepad.SOUTH}), axes=(1000, -50, 0, 0, 200 << 7, 0))
    b = Reading(buttons=frozenset({gamepad.EAST}), axes=(-2000, 20, 0, 5, 100 << 7, 9 << 7))
    s = state(a, b)
    assert (s["buttons"], s["left"], s["right"], s["l2"], s["r2"]) == (0b11, (-2000, -50), (0, 5), 200, 9)


@pytest.mark.parametrize("ps5, size", [(False, (1920, 942)), (True, (1919, 1079))])
def test_touchpad_scaled_to_the_console(ps5, size):
    s = state(Reading(fingers={(0, 0): (0.5, 0.5), (0, 1): (1.0, 1.5)}), ps5=ps5)
    assert s["touches"] == [(0, size[0] // 2, size[1] // 2), (1, size[0], size[1])]


def test_touch_ids_as_the_reference_gives_them():
    touches = Touches()
    one, two, three = {"a": (1, 1)}, {"a": (2, 2), "b": (3, 3)}, {"a": (2, 2), "b": (3, 3), "c": (4, 4)}
    assert touches.update(one) == [(0, 1, 1)]
    assert touches.update(two) == [(0, 2, 2), (1, 3, 3)]
    assert touches.update(three) == [(0, 2, 2), (1, 3, 3)]          # two slots: a third finger waits
    assert touches.update({"b": (3, 3), "c": (4, 4)}) == [(2, 4, 4), (1, 3, 3)]     # c takes the free slot
    assert touches.update({}) == []
    touches.next_id = 127
    assert touches.update(one) == [(127, 1, 1)] and touches.next_id == 0


def _reader(sdl: FakeSdl, sent: list, notes: list, ps5: bool = False, trackers=FakeTracker) -> gamepad.Reader:
    return gamepad.Reader(lambda **s: sent.append(s), ps5, notes.append, sdl, poll_interval=0.001,
                          scan_interval=0.01, trackers=trackers).start()


def _wait(condition, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.002)
    return True


def test_reader_sends_each_change_once():
    pad = FakePad("PS4 Controller")
    sdl = FakeSdl({7: pad})
    sent, notes = [], []
    reader = _reader(sdl, sent, notes)
    try:
        assert _wait(lambda: sent) and _wait(lambda: sdl.updates > 20)
        assert sent == [state(Reading())] and notes == ["Controller: PS4 Controller."]
        with sdl.lock:
            pad.reading = Reading(buttons=frozenset({gamepad.SOUTH}))
        assert _wait(lambda: len(sent) == 2) and sent[1]["buttons"] == 1
        with sdl.lock:
            pad.reading = Reading()
        assert _wait(lambda: len(sent) == 3) and sent[2] == sent[0]
        # Gone: the console gets an idle controller (here already idle, so nothing new).
        pad.connected = False
        assert _wait(lambda: "Controller gone: PS4 Controller." in notes) and pad.closed
    finally:
        reader.stop()
    assert sdl.quit_called and len(sent) == 3 and reader.states_sent == 3


def test_a_controller_that_comes_later_and_one_that_goes_while_held():
    sdl = FakeSdl()
    sent, notes = [], []
    reader = _reader(sdl, sent, notes, ps5=True)
    try:
        held = FakePad("DualSense Wireless Controller", Reading(buttons=frozenset({gamepad.NORTH}),
                                                                fingers={(0, 0): (0.0, 1.0)}))
        with sdl.lock:
            sdl.pads[1] = held
        assert _wait(lambda: any(s["buttons"] == 8 for s in sent))
        assert sent[-1]["touches"] == [(0, 0, 1079)]
        held.connected = False                       # pulled out with triangle held: released for the console
        assert _wait(lambda: sent[-1]["buttons"] == 0 and sent[-1]["touches"] == [])
    finally:
        reader.stop()
    assert notes == ["Controller: DualSense Wireless Controller.", "Controller gone: DualSense Wireless Controller."]


def test_without_sdl_the_log_says_so():
    notes = []
    reader = _reader(FakeSdl(init_error="SDL3 (libSDL3) is not installed, so controllers cannot be read."),
                     [], notes)
    reader.thread.join(timeout=2)
    assert notes == ["SDL3 (libSDL3) is not installed, so controllers cannot be read. The console sees a controller "
                     "lying still."]
    reader.stop()


def test_motion_as_the_reference_feeds_it():
    tracker = FakeTracker()
    motion = gamepad.Motion(lambda: tracker)
    assert motion.value() is None
    # An accelerometer sample in m/s² becomes g, with the last gyro values; a gyro sample keeps the last
    # accelerometer values, already zeroed. The clock: microseconds, 32 bits.
    motion.add(gamepad.Sample(1, gamepad.SENSOR_ACCEL, (0.0, 9.80665, -4.903325), (1 << 32) * 1000 + 5_000_999))
    motion.add(gamepad.Sample(1, gamepad.SENSOR_GYRO, (0.5, -0.25, 1.0), 9_000_000))
    motion.add(gamepad.Sample(1, 99, (1.0, 1.0, 1.0), 10_000_000))          # another sensor: not motion
    assert tracker.updates == [((0.0, 0.0, 0.0), (0.0, 1.0, -0.5), 5000, False),
                               ((0.5, -0.25, 1.0), (0.0, 1.0, -0.5), 9000, True)]
    assert motion.value() == ((0.5, -0.25, 1.0), (0.0, 1.0, -0.5), (0.0, 0.0, 2.0, 1.0))


def test_motion_of_the_first_controller_that_moves():
    still = Reading(motion=((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
    moving = Reading(motion=((0.1, 0.0, 0.0), (0.0, 0.9, 0.1), (0.1, 0.0, 0.0, 0.99)))
    other = Reading(motion=((0.2, 0.0, 0.0), (0.0, 0.8, 0.2), (0.2, 0.0, 0.0, 0.98)))
    assert "gyro" not in state(Reading())
    assert state(still, moving, other)["gyro"] == (0.1, 0.0, 0.0)
    assert state(moving, still)["orient"] == (0.1, 0.0, 0.0, 0.99)
    assert state(Reading(), still)["accel"] == (0.0, 1.0, 0.0)


def test_reader_passes_the_motion_on():
    sdl = FakeSdl({3: FakePad("DualSense Wireless Controller")})
    sent, notes = [], []
    reader = _reader(sdl, sent, notes)
    try:
        assert _wait(lambda: sent)
        assert "gyro" not in sent[-1]                         # no sample yet: the console's idle motion
        with sdl.lock:
            sdl.samples = [gamepad.Sample(3, gamepad.SENSOR_GYRO, (0.0, 2.0, 0.0), 1000),
                           gamepad.Sample(7, gamepad.SENSOR_GYRO, (9.0, 9.0, 9.0), 1000)]     # not open: dropped
        assert _wait(lambda: sent[-1].get("gyro") == (0.0, 2.0, 0.0))
        assert sent[-1]["orient"] == (0.0, 0.0, 1.0, 1.0)
    finally:
        reader.stop()


def test_without_the_core_no_motion():
    sdl = FakeSdl({3: FakePad("PS4 Controller")})
    sent, notes = [], []
    sdl.samples = [gamepad.Sample(3, gamepad.SENSOR_GYRO, (0.0, 2.0, 0.0), 1000)]
    reader = _reader(sdl, sent, notes, trackers=None)
    try:
        assert _wait(lambda: sent and sdl.updates > 5)
    finally:
        reader.stop()
    assert notes[0] == "Without the app's native core the controllers' motion is not passed on."
    assert all("gyro" not in s for s in sent)


def test_motion_reset_makes_the_current_position_the_rest():
    trackers = []

    def make():
        trackers.append(FakeTracker())
        return trackers[-1]
    motion = gamepad.Motion(make)
    g = gamepad.STANDARD_GRAVITY
    motion.add(gamepad.Sample(1, gamepad.SENSOR_ACCEL, (0.0, 0.5 * g, 0.25 * g), 7_000_000))
    motion.reset()
    # The reference's motion reset: the zero is the accelerometer less gravity, and a new tracker starts with it.
    assert motion.zero == (0.0, -0.5, 0.25) and len(trackers) == 2
    assert trackers[1].updates == [((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), 7000, False)]
    motion.add(gamepad.Sample(1, gamepad.SENSOR_ACCEL, (0.0, 0.5 * g, 0.25 * g), 8_000_000))
    assert trackers[1].accel == (0.0, 1.0, 0.0)                 # the same position: at rest


def test_reader_drives_the_controllers():
    sdl = FakeSdl({1: FakePad("PS4 Controller")})
    sent, notes = [], []
    reader = _reader(sdl, sent, notes)
    try:
        assert _wait(lambda: sent)
        reader.output("rumble", 0x80, 0xff)
        reader.output("led", (0, 0, 64))
        reader.output("player", 2)
        assert _wait(lambda: len(sdl.outputs) == 3)
        assert sdl.outputs == [("rumble", "PS4 Controller", (0x8000, 0xff00, 5000)),
                               ("led", "PS4 Controller", (0, 0, 64)), ("player", "PS4 Controller", 2)]
        # One connected later gets the color and the player number at once.
        with sdl.lock:
            sdl.pads[2] = FakePad("DualSense Wireless Controller")
        assert _wait(lambda: len(sdl.outputs) == 5)
        assert sdl.outputs[3:] == [("led", "DualSense Wireless Controller", (0, 0, 64)),
                                   ("player", "DualSense Wireless Controller", 2)]
    finally:
        reader.stop()
    # No motor left running.
    assert sorted(sdl.outputs[5:]) == [("rumble", "DualSense Wireless Controller", (0, 0, 0)),
                                       ("rumble", "PS4 Controller", (0, 0, 0))]


def test_reader_resets_the_motion():
    sdl = FakeSdl({1: FakePad("PS4 Controller")})
    sent, notes = [], []
    reader = _reader(sdl, sent, notes)
    try:
        assert _wait(lambda: sent)
        with sdl.lock:
            sdl.samples = [gamepad.Sample(1, gamepad.SENSOR_ACCEL, (0.0, 0.0, gamepad.STANDARD_GRAVITY), 1000)]
        assert _wait(lambda: sent[-1].get("accel") == (0.0, 0.0, 1.0))
        reader.output("motion_reset")
        assert _wait(lambda: sent[-1].get("accel") == (0.0, 1.0, 0.0))
    finally:
        reader.stop()


def test_steams_virtual_controller_only_when_alone():
    virtual = FakePad("Steam Virtual Gamepad", Reading(buttons=frozenset({gamepad.SOUTH})))
    virtual.info = gamepad.PadInfo("Steam Virtual Gamepad", 0x28DE, 0x11FF)
    real = FakePad("PS4 Controller", Reading(buttons=frozenset({gamepad.EAST})))
    real.info = gamepad.PadInfo("PS4 Controller", 0x054C, 0x05C4)
    sdl = FakeSdl({1: virtual})
    sent, notes = [], []
    reader = _reader(sdl, sent, notes)
    try:
        assert _wait(lambda: sent and sent[-1]["buttons"] == 1)               # alone: it plays (a Steam Deck)
        with sdl.lock:
            sdl.pads[2] = real
        assert _wait(lambda: sent[-1]["buttons"] == 2)                        # with a real one: left out
    finally:
        reader.stop()


def test_steams_ignore_list_is_undone(monkeypatch):
    monkeypatch.setenv("SDL_GAMECONTROLLER_IGNORE_DEVICES", "0x054c/0x05c4")
    monkeypatch.setenv("SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT", "0x28de/0x11ff")

    class Lib:
        def __getattr__(self, name):
            return lambda *args: True
    sdl = gamepad.Sdl.__new__(gamepad.Sdl)
    sdl.lib = Lib()
    sdl.init()
    import os
    assert "SDL_GAMECONTROLLER_IGNORE_DEVICES" not in os.environ
    assert "SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT" not in os.environ


def test_a_missing_library_is_a_gamepad_error():
    with pytest.raises(gamepad.GamepadError, match="SDL3 .* not installed"):
        gamepad.Sdl("/nonexistent/libSDL3.so.0")


@pytest.mark.skipif(not ctypes.util.find_library("SDL3"), reason="SDL3 is not installed")
def test_real_sdl_opens_and_closes():
    sdl = gamepad.Sdl()
    done = threading.Event()
    result = {}

    def run():
        sdl.init()
        try:
            sdl.update()
            result["ids"] = sdl.gamepad_ids()
        finally:
            sdl.quit()
            done.set()
    threading.Thread(target=run).start()
    assert done.wait(5) and isinstance(result["ids"], list)


def test_player_experiment_keeps_the_second_controller_apart():
    first = FakePad("PS4 Controller", Reading(buttons=frozenset({gamepad.SOUTH})))
    second = FakePad("PS4 Controller", Reading(buttons=frozenset({gamepad.EAST})))
    third = FakePad("PS4 Controller", Reading(buttons=frozenset({gamepad.NORTH})))
    sdl = FakeSdl({3: first, 5: second, 9: third})
    sent, sent_second, notes = [], [], []
    reader = gamepad.Reader(lambda **s: sent.append(s), False, notes.append, sdl, poll_interval=0.001,
                            scan_interval=0.01, trackers=FakeTracker,
                            send_second=lambda **s: sent_second.append(s)).start()
    try:
        assert _wait(lambda: sent and sent_second)
    finally:
        reader.stop()
    # By connection order: the first controller to send, the second to send_second, the third nowhere.
    assert sent[-1]["buttons"] == 1 and sent_second[-1]["buttons"] == 2
