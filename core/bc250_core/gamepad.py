# SPDX-License-Identifier: GPL-3.0-or-later
"""A game controller for the portable window (the Windows Portable Suite, owner 26-10-2026: a handheld is used with
its controller, often without a keyboard), read with pygame-ce: SDL's game controller layer gives every pad the same
button names, the Ally's built-in pad as an Xbox controller.

Gamepad turns what the pads do into actions for the window: the d-pad and left stick move (a held direction repeats),
A accepts, B goes back, X and Y are the page's own (Details, Update), LB and RB change the tab, Start and View are the
menu and the view. It also reports every button, stick and trigger as it is (raw), for a controller test. Without
pygame-ce, or without a controller, nothing happens and the window has the keyboard and touch.

After the BC250 portal's gamepad.py (Suite Big Picture Mode), which stays as it is: this one reads every control."""

from __future__ import annotations

import os
import time
from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

POLL_MS = 16
DEADZONE = 0.55                 # of the stick's travel: beyond it the stick counts as pushed
FIRST_REPEAT = 0.4              # s before a held direction repeats, then every REPEAT s
REPEAT = 0.12
DIRECTIONS = ("up", "down", "left", "right")

# SDL's button names (pygame's CONTROLLER_BUTTON_*, in lower case): every button pygame-ce reports
BUTTON_NAMES = ("a", "b", "x", "y", "back", "guide", "start", "leftstick", "rightstick", "leftshoulder",
                "rightshoulder", "dpad_up", "dpad_down", "dpad_left", "dpad_right")
# pygame's CONTROLLER_AXIS_* names to SDL's
AXIS_NAMES = {"LEFTX": "leftx", "LEFTY": "lefty", "RIGHTX": "rightx", "RIGHTY": "righty",
              "TRIGGERLEFT": "lefttrigger", "TRIGGERRIGHT": "righttrigger"}
TRIGGERS = ("lefttrigger", "righttrigger")      # 0 to 1; the sticks' axes go from -1 to 1, y down

ACTIONS = {                     # the buttons the window acts on
    "dpad_up": "up", "dpad_down": "down", "dpad_left": "left", "dpad_right": "right",
    "a": "accept", "b": "back", "x": "x", "y": "y",
    "leftshoulder": "previous", "rightshoulder": "next", "start": "menu", "back": "view",
}


def stick_direction(x: float, y: float) -> str | None:
    """The direction a stick (each axis -1 to 1, y down) is pushed, along its stronger axis; None in the dead zone."""
    if max(abs(x), abs(y)) < DEADZONE:
        return None
    if abs(x) >= abs(y):
        return "right" if x > 0 else "left"
    return "down" if y > 0 else "up"


class PygameSource:
    """The controllers' events, as ("button", name, pressed), ("axis", name, value) and ("removed", name, False)."""

    def __init__(self):
        # SDL needs no window or sound: a dummy video driver gives it the event queue. The events of a pad come
        # also when nothing of ours has the focus; the window itself only acts while it is active.
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
        os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame
        from pygame._sdl2 import controller
        self.pygame, self.controller = pygame, controller
        pygame.display.init()
        controller.init()
        self.pads: dict[int, object] = {}               # SDL's instance id: the open controller
        for index in range(controller.get_count()):
            self._open(index)
        self.buttons = {getattr(pygame, f"CONTROLLER_BUTTON_{name.upper()}"): name for name in BUTTON_NAMES}
        self.axes = {getattr(pygame, f"CONTROLLER_AXIS_{axis}"): name for axis, name in AXIS_NAMES.items()}

    def _open(self, index: int) -> None:
        try:
            if self.controller.is_controller(index):
                pad = self.controller.Controller(index)
                self.pads[pad.id] = pad
        except Exception:  # noqa: BLE001  (a pad that cannot be opened is left alone)
            pass

    def names(self) -> list[str]:
        """The open controllers' names, as SDL knows them."""
        return [str(getattr(pad, "name", "")) for pad in self.pads.values()]

    def events(self) -> list[tuple[str, str, float | bool]]:
        pygame = self.pygame
        found: list[tuple[str, str, float | bool]] = []
        for event in pygame.event.get():
            if event.type == pygame.CONTROLLERDEVICEADDED:
                self._open(event.device_index)
                found.append(("added", "", True))
            elif event.type == pygame.CONTROLLERDEVICEREMOVED:
                self.pads.pop(event.instance_id, None)
                found.append(("removed", "", False))
            elif event.type in (pygame.CONTROLLERBUTTONDOWN, pygame.CONTROLLERBUTTONUP):
                name = self.buttons.get(event.button)
                if name:
                    found.append(("button", name, event.type == pygame.CONTROLLERBUTTONDOWN))
            elif event.type == pygame.CONTROLLERAXISMOTION:
                name = self.axes.get(event.axis)
                if name:
                    found.append(("axis", name, max(-1.0, min(1.0, event.value / 32767))))
        return found

    def close(self) -> None:
        self.pads.clear()
        try:
            self.controller.quit()
            self.pygame.display.quit()
        except Exception:  # noqa: BLE001  (closing never fails the app)
            pass


class Gamepad(QObject):
    """action(name): up, down, left, right (a held direction repeats), accept, back, x, y, previous, next, menu,
    view. raw(kind, name, value): every button ("button", name, pressed) and axis ("axis", name, value) as it is,
    and ("added"/"removed", "", ...) when a pad comes or goes."""

    action = pyqtSignal(str)
    raw = pyqtSignal(str, str, object)

    def __init__(self, parent: QObject | None = None, source_factory: Callable[[], object] = PygameSource,
                 clock: Callable[[], float] = time.monotonic):
        super().__init__(parent)
        self.source_factory = source_factory
        self.clock = clock
        self.source = None
        self.held: dict[str, tuple[str, float]] = {}    # a d-pad button or the stick: its direction, its next repeat
        self.stick = [0.0, 0.0]
        self.timer = QTimer(self)
        self.timer.setInterval(POLL_MS)
        self.timer.timeout.connect(self.poll)

    def start(self) -> bool:
        """Start listening; False when pygame-ce is missing or SDL cannot start (the window then has the keyboard)."""
        if self.source is None:
            try:
                self.source = self.source_factory()
            except Exception:  # noqa: BLE001  (no pygame-ce, or no SDL: no controller support, no message)
                return False
        self.timer.start()
        return True

    def stop(self) -> None:
        self.timer.stop()
        self.held.clear()
        self.stick = [0.0, 0.0]
        if self.source is not None:
            self.source.close()
            self.source = None

    def names(self) -> list[str]:
        """The connected controllers' names; empty without a controller or before start()."""
        return self.source.names() if self.source is not None and hasattr(self.source, "names") else []

    def poll(self) -> None:
        if self.source is None:
            return
        for kind, name, value in self.source.events():
            self.handle(kind, name, value)
        now = self.clock()
        for source, (direction, due) in list(self.held.items()):
            if now >= due:
                self.held[source] = (direction, now + REPEAT)
                self.action.emit(direction)

    def handle(self, kind: str, name: str, value: float | bool) -> None:
        if kind == "axis" and name in TRIGGERS:
            value = max(0.0, float(value))
        self.raw.emit(kind, name, value)
        if kind == "removed":                           # a pad was unplugged with a direction held
            self.held.clear()
            return
        if kind == "axis":
            if name in ("leftx", "lefty"):
                self.stick[0 if name == "leftx" else 1] = float(value)
                self._push("stick", stick_direction(*self.stick))
            return
        action = ACTIONS.get(name) if kind == "button" else None
        if action is None:
            return
        if action in DIRECTIONS:
            self._push(name, action if value else None)
        elif value:
            self.action.emit(action)

    def _push(self, source: str, direction: str | None) -> None:
        """A direction pressed or released by *source* (a d-pad button or the stick): a new one acts at once."""
        if direction is None:
            self.held.pop(source, None)
        elif source not in self.held or self.held[source][0] != direction:
            self.held[source] = (direction, self.clock() + FIRST_REPEAT)
            self.action.emit(direction)
