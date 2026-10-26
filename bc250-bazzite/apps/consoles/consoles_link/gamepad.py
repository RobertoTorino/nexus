# SPDX-License-Identifier: AGPL-3.0-or-later
"""The controllers on the board, read with SDL3 (the system's libSDL3, through ctypes) and passed to the stream as
the console's controller state.

SDL names the buttons by position (south, east, ...) for every kind of gamepad, so a DualShock 4, a DualSense, an
Xbox pad or a Steam Deck's controls all map the same way: south is cross, east circle, west square, north triangle,
back is Share, start Options, guide the PS button, as in the reference. The triggers go from 0 to 255, the sticks
as they are, the touchpad's fingers scaled to the console's touchpad (1920 × 942 on a PS4, 1919 × 1079 on a PS5;
the reference scales a gamepad's fingers to 1920 × 1079 for both). With several controllers connected, their
states are combined as the reference combines them: buttons together, the larger trigger, the stick further from the
center, the motion of the first one that moves.

The motion: SDL switches on each controller's gyro and accelerometer where it has them and delivers every sample as
an event with the controller's own clock. Each sample goes to that controller's orientation tracker (the native
core's port of the reference's), which the console gets as gyro, accelerometer (in g) and orientation, as the
reference's GUI feeds it. One difference: the reference's GUI times the samples in whole milliseconds, here they are
timed to the microsecond.

The other way, from the console (output()): the rumble goes to every controller's motors (SDL's rumble, 0 to 255
scaled to 16 bits, for 5 s unless the console renews or stops it, as in the reference), the light bar's color and
the player number to every controller that has them, including one connected later, and a motion reset makes the
controller's current position the new rest position.

In Game Mode Steam starts the app (its shortcut) with SDL told to ignore the controllers Steam handles, and gives it
Steam's virtual controller instead, which has no touchpad or motion sensors. So the reader undoes that: SDL sees the
real controllers, and Steam's virtual one is left out while a real one is there (still used where it is the only
one, as a Steam Deck's own controls are).

Reader runs SDL on a thread of its own: it opens the controllers that are connected or come later, reads them every
4 ms and hands each new state to the stream."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import queue
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

POLL_INTERVAL = 0.004                    # a DualShock 4 reports every 4 ms over USB
RUMBLE_MS = 5000                         # the reference's: the console renews or stops the rumble before
SCAN_INTERVAL = 1.0                      # how often to look for controllers that came or went

# SDL3's numbers (SDL_gamepad.h).
SOUTH, EAST, WEST, NORTH, BACK, GUIDE, START = 0, 1, 2, 3, 4, 5, 6
LEFT_STICK, RIGHT_STICK, LEFT_SHOULDER, RIGHT_SHOULDER = 7, 8, 9, 10
DPAD_UP, DPAD_DOWN, DPAD_LEFT, DPAD_RIGHT = 11, 12, 13, 14
TOUCHPAD = 20
BUTTON_COUNT = 26
LEFT_X, LEFT_Y, RIGHT_X, RIGHT_Y, LEFT_TRIGGER, RIGHT_TRIGGER = range(6)
INIT_GAMEPAD = 0x00002000
SENSOR_ACCEL, SENSOR_GYRO = 1, 2
EVENT_GAMEPAD_SENSOR_UPDATE = 0x659
EVENT_SIZE = 128
STANDARD_GRAVITY = struct.unpack("f", struct.pack("f", 9.80665))[0]       # SDL's, as a float
IDLE_GYRO, IDLE_ACCEL = (0.0, 0.0, 0.0), (0.0, 1.0, 0.0)

# The console's buttons (feedback.rs, as the reference numbers them).
CROSS, MOON, BOX, PYRAMID = 1 << 0, 1 << 1, 1 << 2, 1 << 3
PAD_LEFT, PAD_RIGHT, PAD_UP, PAD_DOWN = 1 << 4, 1 << 5, 1 << 6, 1 << 7
L1, R1, L3, R3, OPTIONS, SHARE, TOUCHPAD_CLICK, PS = (1 << n for n in range(8, 16))

BUTTONS = {
    SOUTH: CROSS, EAST: MOON, WEST: BOX, NORTH: PYRAMID,
    DPAD_LEFT: PAD_LEFT, DPAD_RIGHT: PAD_RIGHT, DPAD_UP: PAD_UP, DPAD_DOWN: PAD_DOWN,
    LEFT_SHOULDER: L1, RIGHT_SHOULDER: R1, LEFT_STICK: L3, RIGHT_STICK: R3,
    START: OPTIONS, BACK: SHARE, GUIDE: PS, TOUCHPAD: TOUCHPAD_CLICK,
}

TOUCHPAD_PS4 = (1920.0, 942.0)
TOUCHPAD_PS5 = (1919.0, 1079.0)
TOUCHES_MAX = 2
TOUCH_ID_MASK = 0x7f


class GamepadError(Exception):
    pass


@dataclass
class Reading:
    """One controller as SDL reports it: the SDL buttons held, the six axes, and the fingers on its touchpads as
    (touchpad, finger) -> (x, y) from 0 to 1. motion: (gyro, accel, orientation) from its tracker, once its sensors
    sent something."""
    buttons: frozenset[int] = frozenset()
    axes: tuple[int, ...] = (0,) * 6
    fingers: dict[tuple[int, int], tuple[float, float]] = field(default_factory=dict)
    motion: tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]] | None = None


@dataclass
class PadInfo:
    """What SDL says about a controller: for the controller test."""
    name: str
    vendor: int = 0
    product: int = 0
    firmware: int = 0
    path: str = ""
    connection: str = "unknown"             # "cable", "wireless" or "unknown"
    sensors: tuple[int, ...] = ()
    touchpads: int = 0
    rumble: bool = False
    light_bar: bool = False

    @property
    def model(self) -> str:
        """The Sony model by its USB ID (DualShock 4 v1 or v2, DualSense), else SDL's name. A copy can carry a Sony
        ID too: the controller test's genuine check looks further."""
        from .genuine import DUALSENSE, DUALSHOCK4, SONY
        if self.vendor == SONY:
            return DUALSHOCK4.get(self.product) or DUALSENSE.get(self.product) or self.name
        return self.name

    @property
    def steam_virtual(self) -> bool:
        """Steam's virtual controller (Steam Input), which stands in for a real one in a game Steam starts."""
        return (self.vendor, self.product) == STEAM_VIRTUAL

    def describe(self) -> str:
        return self.model + (f", {self.connection}" if self.connection != "unknown" else "")


CONNECTIONS = {1: "cable", 2: "wireless"}
STEAM_VIRTUAL = (0x28DE, 0x11FF)
STEAM_IGNORE = ("SDL_GAMECONTROLLER_IGNORE_DEVICES", "SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT")
POWER = {1: "on battery", 2: "no battery", 3: "charging", 4: "charged"}


@dataclass
class Sample:
    """One sensor reading: the controller's id, SENSOR_ACCEL (m/s²) or SENSOR_GYRO (rad/s), the three values and
    the controller's clock in nanoseconds."""
    pad_id: int
    sensor: int
    data: tuple[float, float, float]
    timestamp_ns: int


class Touches:
    """The fingers' touch ids, as the reference's controller state gives them out: two slots, ids counting up to 127
    and around."""

    def __init__(self):
        self.slots: list[tuple[object, int] | None] = [None] * TOUCHES_MAX
        self.next_id = 0

    def update(self, fingers: dict[object, tuple[int, int]]) -> list[tuple[int, int, int]]:
        """fingers: key -> (x, y) on the console's touchpad; the touches as (id, x, y), by slot."""
        for i, slot in enumerate(self.slots):
            if slot is not None and slot[0] not in fingers:
                self.slots[i] = None
        held = {slot[0] for slot in self.slots if slot is not None}
        for key in fingers:
            if key in held or None not in self.slots:
                continue
            self.slots[self.slots.index(None)] = (key, self.next_id)
            self.next_id = (self.next_id + 1) & TOUCH_ID_MASK
        return [(slot[1], *fingers[slot[0]]) for slot in self.slots if slot is not None]


def _max_abs(a: int, b: int) -> int:
    return a if abs(a) > abs(b) else b


def controller_state(readings: dict[object, Reading], touches: Touches, ps5: bool) -> dict:
    """The console's controller state (the keywords of StreamConnection.set_controller) from every controller."""
    buttons = l2 = r2 = 0
    sticks = [0, 0, 0, 0]
    width, height = TOUCHPAD_PS5 if ps5 else TOUCHPAD_PS4
    fingers = {}
    motion = None
    for pad, reading in readings.items():
        # The reference keeps the first controller's motion that is not at rest, else takes the next one's.
        if reading.motion is not None and (motion is None or (motion[0], motion[1]) == (IDLE_GYRO, IDLE_ACCEL)):
            motion = reading.motion
        for button in reading.buttons:
            buttons |= BUTTONS.get(button, 0)
        axes = reading.axes
        l2 = max(l2, max(0, axes[LEFT_TRIGGER]) >> 7)
        r2 = max(r2, max(0, axes[RIGHT_TRIGGER]) >> 7)
        sticks = [_max_abs(a, b) for a, b in zip(sticks, axes[:4])]
        for key, (x, y) in reading.fingers.items():
            fingers[(pad, key)] = (int(min(max(x, 0.0), 1.0) * width), int(min(max(y, 0.0), 1.0) * height))
    state = {"buttons": buttons, "l2": l2, "r2": r2, "left": (sticks[0], sticks[1]), "right": (sticks[2], sticks[3]),
             "touches": touches.update(fingers)}
    if motion is not None:
        state["gyro"], state["accel"], state["orient"] = motion
    return state


class Motion:
    """One controller's orientation tracker, fed as the reference's GUI feeds it: an accelerometer sample with the
    last gyro values, a gyro sample with the last accelerometer values. reset() is the reference's motion reset: the
    accelerometer as it is now becomes the zero (less gravity), and the tracker starts again from there."""

    def __init__(self, trackers: Callable[[], object]):
        self.trackers = trackers
        self.tracker = trackers()
        self.samples = 0
        self.zero = (0.0, 0.0, 0.0)
        self.real_accel = IDLE_ACCEL               # the last accelerometer sample in g, before the zero
        self.timestamp_us = 0

    def add(self, sample: Sample) -> None:
        timestamp_us = (sample.timestamp_ns // 1000) & 0xffffffff
        if sample.sensor == SENSOR_ACCEL:
            accel = tuple(_float(value / STANDARD_GRAVITY) for value in sample.data)
            self.real_accel = accel
            self.tracker.update(self.tracker.gyro, accel, timestamp_us, accel_zero=self.zero)
        elif sample.sensor == SENSOR_GYRO:
            self.tracker.update(sample.data, self.tracker.accel, timestamp_us, accel_zero_applied=True)
        else:
            return
        self.timestamp_us = timestamp_us
        self.samples += 1

    def reset(self) -> None:
        ax, ay, az = self.real_accel
        self.zero = (ax, _float(ay - 1.0), az)
        gyro = self.tracker.gyro
        self.tracker = self.trackers()
        self.tracker.update(gyro, self.real_accel, self.timestamp_us, accel_zero=self.zero)

    def value(self):
        if not self.samples:
            return None
        return self.tracker.gyro, self.tracker.accel, self.tracker.orientation


def _float(value: float) -> float:
    """Rounded to a float, as the reference's float division is."""
    return struct.unpack("f", struct.pack("f", value))[0]


def _trackers():
    """The native core's orientation tracker class, or None without the core."""
    try:
        from bc250_console_link_core import OrientationTracker
    except ImportError:
        return None
    return OrientationTracker


class Sdl:
    """The few SDL3 calls the reader needs. Every call from one thread, the reader's."""

    def __init__(self, path: str | None = None):
        path = path or ctypes.util.find_library("SDL3") or "libSDL3.so.0"
        try:
            lib = ctypes.CDLL(path)
        except OSError as error:
            raise GamepadError("SDL3 (libSDL3) is not installed, so controllers cannot be read.") from error
        c = ctypes
        for name, result, args in [
            ("SDL_SetHint", c.c_bool, [c.c_char_p, c.c_char_p]),
            ("SDL_Init", c.c_bool, [c.c_uint32]),
            ("SDL_QuitSubSystem", None, [c.c_uint32]),
            ("SDL_GetError", c.c_char_p, []),
            ("SDL_SetGamepadEventsEnabled", None, [c.c_bool]),
            ("SDL_PollEvent", c.c_bool, [c.c_void_p]),
            ("SDL_GamepadHasSensor", c.c_bool, [c.c_void_p, c.c_int]),
            ("SDL_SetGamepadSensorEnabled", c.c_bool, [c.c_void_p, c.c_int, c.c_bool]),
            ("SDL_RumbleGamepad", c.c_bool, [c.c_void_p, c.c_uint16, c.c_uint16, c.c_uint32]),
            ("SDL_SetGamepadLED", c.c_bool, [c.c_void_p, c.c_uint8, c.c_uint8, c.c_uint8]),
            ("SDL_SetGamepadPlayerIndex", c.c_bool, [c.c_void_p, c.c_int]),
            ("SDL_GetGamepadVendor", c.c_uint16, [c.c_void_p]),
            ("SDL_GetGamepadProduct", c.c_uint16, [c.c_void_p]),
            ("SDL_GetGamepadFirmwareVersion", c.c_uint16, [c.c_void_p]),
            ("SDL_GetGamepadPath", c.c_char_p, [c.c_void_p]),
            ("SDL_GetGamepadConnectionState", c.c_int, [c.c_void_p]),
            ("SDL_GetGamepadPowerInfo", c.c_int, [c.c_void_p, c.POINTER(c.c_int)]),
            ("SDL_GetGamepadProperties", c.c_uint32, [c.c_void_p]),
            ("SDL_GetBooleanProperty", c.c_bool, [c.c_uint32, c.c_char_p, c.c_bool]),
            ("SDL_GetGamepads", c.POINTER(c.c_uint32), [c.POINTER(c.c_int)]),
            ("SDL_free", None, [c.c_void_p]),
            ("SDL_OpenGamepad", c.c_void_p, [c.c_uint32]),
            ("SDL_CloseGamepad", None, [c.c_void_p]),
            ("SDL_GamepadConnected", c.c_bool, [c.c_void_p]),
            ("SDL_GetGamepadName", c.c_char_p, [c.c_void_p]),
            ("SDL_GetGamepadButton", c.c_bool, [c.c_void_p, c.c_int]),
            ("SDL_GetGamepadAxis", c.c_int16, [c.c_void_p, c.c_int]),
            ("SDL_GetNumGamepadTouchpads", c.c_int, [c.c_void_p]),
            ("SDL_GetNumGamepadTouchpadFingers", c.c_int, [c.c_void_p, c.c_int]),
            ("SDL_GetGamepadTouchpadFinger", c.c_bool,
             [c.c_void_p, c.c_int, c.c_int, c.POINTER(c.c_bool), c.POINTER(c.c_float), c.POINTER(c.c_float),
              c.POINTER(c.c_float)]),
        ]:
            try:
                function = getattr(lib, name)
            except AttributeError as error:
                raise GamepadError(f"The installed SDL3 has no {name}.") from error
            function.restype, function.argtypes = result, args
        self.lib = lib
        self.event = ctypes.create_string_buffer(EVENT_SIZE)

    def init(self) -> None:
        for name in STEAM_IGNORE:                    # Steam's list of controllers to leave to it (Game Mode)
            os.environ.pop(name, None)
        # Qt handles the signals; no window of ours has the focus SDL would wait for.
        self.lib.SDL_SetHint(b"SDL_NO_SIGNAL_HANDLERS", b"1")
        self.lib.SDL_SetHint(b"SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", b"1")
        if not self.lib.SDL_Init(INIT_GAMEPAD):
            error = self.lib.SDL_GetError().decode(errors="replace")
            raise GamepadError(f"SDL could not open the controllers: {error}.")
        self.lib.SDL_SetGamepadEventsEnabled(True)          # the sensors' samples come as events

    def quit(self) -> None:
        self.lib.SDL_QuitSubSystem(INIT_GAMEPAD)

    def update(self) -> list[Sample]:
        """Takes in what the controllers sent (the buttons and axes read() gives) and returns the sensors' samples
        since the last call; every other event is dropped."""
        samples = []
        event = self.event
        while self.lib.SDL_PollEvent(event):
            kind, = struct.unpack_from("<I", event, 0)
            if kind != EVENT_GAMEPAD_SENSOR_UPDATE:
                continue
            # SDL_GamepadSensorEvent: type, reserved, timestamp (ns), which, sensor, data[3], sensor_timestamp (ns).
            _type, _reserved, timestamp, which, sensor, x, y, z, sensor_timestamp = struct.unpack_from(
                "<IIQIi3f4xQ", event, 0)
            samples.append(Sample(which, sensor, (x, y, z), sensor_timestamp or timestamp))
        return samples

    def gamepad_ids(self) -> list[int]:
        count = ctypes.c_int(0)
        ids = self.lib.SDL_GetGamepads(ctypes.byref(count))
        if not ids:
            return []
        try:
            return [ids[i] for i in range(count.value)]
        finally:
            self.lib.SDL_free(ids)

    def open(self, pad_id: int):
        pad = self.lib.SDL_OpenGamepad(pad_id) or None
        if pad is not None:
            for sensor in (SENSOR_ACCEL, SENSOR_GYRO):
                if self.lib.SDL_GamepadHasSensor(pad, sensor):
                    self.lib.SDL_SetGamepadSensorEnabled(pad, sensor, True)
        return pad

    def close(self, pad) -> None:
        self.lib.SDL_CloseGamepad(pad)

    def connected(self, pad) -> bool:
        return bool(self.lib.SDL_GamepadConnected(pad))

    def name(self, pad) -> str:
        name = self.lib.SDL_GetGamepadName(pad)
        return name.decode(errors="replace") if name else "a controller"

    def rumble(self, pad, low: int, high: int, milliseconds: int) -> str | None:
        """None when SDL sent it, else SDL's reason."""
        if self.lib.SDL_RumbleGamepad(pad, low, high, milliseconds):
            return None
        return self.lib.SDL_GetError().decode(errors="replace") or "no reason given"

    def led(self, pad, rgb: tuple[int, int, int]) -> None:
        self.lib.SDL_SetGamepadLED(pad, *rgb)

    def player(self, pad, index: int) -> None:
        self.lib.SDL_SetGamepadPlayerIndex(pad, index)

    def info(self, pad) -> PadInfo:
        lib = self.lib
        path = lib.SDL_GetGamepadPath(pad)
        properties = lib.SDL_GetGamepadProperties(pad)
        return PadInfo(
            name=self.name(pad), vendor=lib.SDL_GetGamepadVendor(pad), product=lib.SDL_GetGamepadProduct(pad),
            firmware=lib.SDL_GetGamepadFirmwareVersion(pad), path=path.decode(errors="replace") if path else "",
            connection=CONNECTIONS.get(lib.SDL_GetGamepadConnectionState(pad), "unknown"),
            sensors=tuple(s for s in (SENSOR_ACCEL, SENSOR_GYRO) if lib.SDL_GamepadHasSensor(pad, s)),
            touchpads=lib.SDL_GetNumGamepadTouchpads(pad),
            rumble=bool(properties) and lib.SDL_GetBooleanProperty(properties, b"SDL.joystick.cap.rumble", False),
            light_bar=bool(properties) and lib.SDL_GetBooleanProperty(properties, b"SDL.joystick.cap.rgb_led", False))

    def battery(self, pad) -> tuple[str, int]:
        """The power state and the charge in percent (-1 when unknown)."""
        percent = ctypes.c_int(-1)
        state = self.lib.SDL_GetGamepadPowerInfo(pad, ctypes.byref(percent))
        return POWER.get(state, "unknown"), percent.value

    def read(self, pad) -> Reading:
        lib = self.lib
        buttons = frozenset(b for b in range(BUTTON_COUNT) if lib.SDL_GetGamepadButton(pad, b))
        axes = tuple(lib.SDL_GetGamepadAxis(pad, a) for a in range(6))
        fingers = {}
        down, x, y, pressure = ctypes.c_bool(), ctypes.c_float(), ctypes.c_float(), ctypes.c_float()
        for touchpad in range(lib.SDL_GetNumGamepadTouchpads(pad)):
            for finger in range(lib.SDL_GetNumGamepadTouchpadFingers(pad, touchpad)):
                if lib.SDL_GetGamepadTouchpadFinger(pad, touchpad, finger, ctypes.byref(down), ctypes.byref(x),
                                                    ctypes.byref(y), ctypes.byref(pressure)) and down.value:
                    fingers[(touchpad, finger)] = (x.value, y.value)
        return Reading(buttons, axes, fingers)


class Reader:
    """Reads the controllers on a thread of its own until stop(), and calls *send* with each new controller state
    (the keywords of StreamConnection.set_controller). *note* gets the log lines: which controllers came and went,
    or why none can be read. *trackers* makes a controller's orientation tracker (the native core's by default; None:
    no motion). The state goes out once per poll with all the samples since the last one taken in; the reference
    sends one after every sample."""

    def __init__(self, send: Callable[..., None], ps5: bool, note: Callable[[str], None],
                 backend: Callable[[], object] = Sdl, poll_interval: float = POLL_INTERVAL,
                 scan_interval: float = SCAN_INTERVAL, trackers: Callable[[], object] | None = _trackers(),
                 watch: Callable[[dict], None] | None = None, send_second: Callable[..., None] | None = None):
        self.send, self.ps5, self.note, self.watch = send, ps5, note, watch
        # The several-players experiment: the first controller goes to send, the second to send_second, the rest
        # nowhere. Without it every controller acts as one.
        self.send_second = send_second
        self.infos: dict[int, PadInfo] = {}
        self.batteries: dict[int, tuple[str, int]] = {}
        self.backend, self.poll_interval, self.scan_interval = backend, poll_interval, scan_interval
        self.trackers = trackers
        self.outputs: queue.SimpleQueue = queue.SimpleQueue()
        self.led: tuple[int, int, int] | None = None
        self.player_index: int | None = None
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, name="gamepad", daemon=True)
        self.states_sent = 0
        self.polls = 0
        self.gap_max = 0.0                      # the longest time between two reads since figures() last read it

    def start(self) -> Reader:
        self.thread.start()
        return self

    def output(self, kind: str, *values) -> None:
        """From the console, any thread (StreamConnection.drive_controllers): ("rumble", left, right),
        ("led", (r, g, b)), ("player", index) or ("motion_reset",); for one controller (the controller test):
        ("rumble_pad", pad id, left, right, milliseconds) or ("led_pad", pad id, (r, g, b)). The reader's thread
        applies it."""
        self.outputs.put((kind, *values))

    def stop(self) -> None:
        self.stopping.set()
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def figures(self) -> dict:
        """For the statistics file: the reads so far and the longest gap between two since the last call."""
        figures = {"polls": self.polls, "gap_max": self.gap_max}
        self.gap_max = 0.0
        return figures

    def _run(self) -> None:
        try:
            sdl = self.backend()
            sdl.init()
        except GamepadError as error:
            self.note(f"{error} The console sees a controller lying still.")
            return
        if self.trackers is None:
            self.note("Without the app's native core the controllers' motion is not passed on.")
        pads: dict[int, object] = {}
        motions: dict[int, Motion] = {}
        touches, touches_second = Touches(), Touches()
        last = last_second = None
        try:
            next_scan = time.monotonic()
            previous = None
            while not self.stopping.is_set():
                began = time.monotonic()
                if previous is not None:
                    self.gap_max = max(self.gap_max, began - previous)
                previous = began
                self.polls += 1
                samples = sdl.update()
                if time.monotonic() >= next_scan:
                    self._scan(sdl, pads)
                    if self.watch is not None:
                        self.batteries = {pad_id: sdl.battery(pad) for pad_id, pad in pads.items()}
                    next_scan = time.monotonic() + self.scan_interval
                if self.trackers is not None:
                    for sample in samples:
                        if sample.pad_id in pads:
                            motions.setdefault(sample.pad_id, Motion(self.trackers)).add(sample)
                self._apply_outputs(sdl, pads, motions)
                readings = {}
                for pad_id, pad in list(pads.items()):
                    if not sdl.connected(pad):
                        gone = self.infos[pad_id].model if pad_id in self.infos else sdl.name(pad)
                        self.note(f"Controller gone: {gone}.")
                        sdl.close(pad)
                        del pads[pad_id]
                        motions.pop(pad_id, None)
                        self.infos.pop(pad_id, None)
                        continue
                    readings[pad_id] = sdl.read(pad)
                    if pad_id in motions:
                        readings[pad_id].motion = motions[pad_id].value()
                real = [p for p in readings if p in self.infos and not self.infos[p].steam_virtual]
                if real:                                # Steam's virtual controller only when nothing else is there
                    readings = {p: r for p, r in readings.items() if p not in self.infos
                                or not self.infos[p].steam_virtual}
                if self.watch is not None:
                    self.watch({pad_id: (self.infos[pad_id], reading, self.batteries.get(pad_id, ("unknown", -1)))
                                for pad_id, reading in readings.items() if pad_id in self.infos})
                if self.send_second is not None:
                    order = sorted(readings)
                    second = {p: readings[p] for p in order[1:2]}
                    readings = {p: readings[p] for p in order[:1]}
                    state_second = controller_state(second, touches_second, self.ps5)
                    if state_second != last_second:
                        self.send_second(**state_second)
                        last_second = state_second
                state = controller_state(readings, touches, self.ps5)
                if state != last:
                    self.send(**state)
                    self.states_sent += 1
                    last = state
                self.stopping.wait(self.poll_interval)
        finally:
            for pad in pads.values():
                sdl.rumble(pad, 0, 0, 0)               # no motor left running after the stream
                sdl.close(pad)
            sdl.quit()

    def _apply_outputs(self, sdl, pads: dict[int, object], motions: dict[int, Motion]) -> None:
        while True:
            try:
                kind, *values = self.outputs.get_nowait()
            except queue.Empty:
                return
            if kind == "rumble":
                left, right = values
                for pad in pads.values():
                    sdl.rumble(pad, left << 8, right << 8, RUMBLE_MS)
            elif kind == "led":
                self.led = values[0]
                for pad in pads.values():
                    sdl.led(pad, self.led)
            elif kind == "player":
                self.player_index = values[0]
                for pad in pads.values():
                    sdl.player(pad, self.player_index)
            elif kind == "motion_reset":
                for motion in motions.values():
                    motion.reset()
            elif kind == "rumble_pad" and values[0] in pads:       # the controller test: one controller
                pad_id, left, right, milliseconds = values
                error = sdl.rumble(pads[pad_id], left << 8, right << 8, milliseconds)
                self.note(f"Rumble sent ({milliseconds / 1000:g} s)." if error is None else
                          f"SDL did not send the rumble: {error}.")
            elif kind == "led_pad" and values[0] in pads:
                sdl.led(pads[values[0]], values[1])

    def _scan(self, sdl, pads: dict[int, object]) -> None:
        for pad_id in sdl.gamepad_ids():
            if pad_id in pads:
                continue
            pad = sdl.open(pad_id)
            if pad is not None:
                pads[pad_id] = pad
                self.infos[pad_id] = sdl.info(pad)
                self.note(f"Controller: {self.infos[pad_id].describe()}.")
                if self.led is not None:
                    sdl.led(pad, self.led)
                if self.player_index is not None:
                    sdl.player(pad, self.player_index)
